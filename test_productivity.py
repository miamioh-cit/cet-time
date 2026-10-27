import csv
import io
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
import backups
import productivity
import test_improvements

class ProductivityTests(unittest.TestCase):
    request=test_improvements.ImprovementTests.request
    login=test_improvements.ImprovementTests.login
    def setUp(self):
        test_improvements.ImprovementTests.setUp(self)
        self.env=patch.dict(os.environ,{'BACKUP_DIRECTORY':str(Path(self.tmp.name)/'backups'),'BACKUP_KEEP':'2','BACKUP_INTERVAL_HOURS':'6'})
        self.env.start()
        day=datetime.fromtimestamp(self.session['start'],self.s.TZ)
        self.week=(day-timedelta(days=day.weekday())).strftime('%Y-%m-%d')
    def tearDown(self):
        self.env.stop();test_improvements.ImprovementTests.tearDown(self)
    def raw(self,path,data,cookie=None):
        headers={'Origin':self.origin,'Content-Type':'application/json'}
        if cookie:headers['Cookie']=cookie
        try:response=urllib.request.urlopen(urllib.request.Request(self.origin+path,data=json.dumps(data).encode(),headers=headers),timeout=10)
        except urllib.error.HTTPError as e:response=e
        with response:return response.status,response.read(),response.headers
    def confirm(self):
        with self.s.connect() as db:
            db.execute('INSERT INTO confirmations VALUES(?,?,?,?,?,?)',('recorded',1800,'alice','alice','Break',self.n))
            self.s.put(db,'last_sync',time.time())
    def test_weekly_checklist_readiness_and_student_scope(self):
        alice=self.login();data={'week':self.week,'member':'bob'}
        status,result,_=self.request('/api/weekly-checklist',data,alice)
        self.assertEqual(status,200);self.assertFalse(result['ready']);self.assertEqual(result['unverified'][0]['member'],'alice')
        self.confirm();_,result,_=self.request('/api/weekly-checklist',data,alice)
        self.assertTrue(result['ready']);self.assertEqual([x['member'] for x in result['students']],['alice'])
        self.assertAlmostEqual(result['students'][0]['verified'],.5)
        self.assertEqual(self.request('/api/weekly-checklist',{'week':'invalid'},alice)[0],400)
    def test_pending_corrections_block_only_the_affected_week(self):
        self.confirm();alice=self.login()
        self.assertEqual(self.request('/api/correction-request',{'session':'recorded','hours':.75,'note':'Correction'},alice)[0],200)
        _,result,_=self.request('/api/weekly-checklist',{'week':self.week},alice)
        item=next(x for x in result['items'] if 'Correction' in x['label']);self.assertFalse(item['ok']);self.assertEqual(item['count'],1)
        self.assertFalse(result['ready'])
    def test_class_csv_totals_and_formula_safe_text(self):
        self.confirm()
        with self.s.connect() as db:db.execute('UPDATE users SET name=? WHERE id=?',('=SUM(1,2)','alice'))
        cards=[{'id':'c','name':'  =HYPERLINK("bad")','idList':'done','idMembers':['alice']}]
        with patch.object(self.s,'state',return_value=(cards,[self.session])):
            status,content,headers=self.raw('/api/export',{'week':self.week,'scope':'class','format':'detail'},self.login('admin'))
        self.assertEqual(status,200);self.assertTrue(content.startswith(b'\xef\xbb\xbf'));self.assertIn('.csv',headers['Content-Disposition'])
        rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        alice=next(x for x in rows if x['Username']=='alice');bob=next(x for x in rows if x['Username']=='bob')
        self.assertTrue(alice['Student'].startswith("'="));self.assertTrue(alice['Activity'].startswith("'  ="))
        self.assertEqual(alice['Hours'],'0.50');self.assertEqual(bob['Hours'],'0.00')
        status,content,_=self.raw('/api/export',{'week':self.week,'scope':'class','format':'summary'},self.login('admin'))
        self.assertEqual(status,200);rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        self.assertEqual(sum(float(x['Hours']) for x in rows),.5)
    def test_export_authorization_and_unverified_opt_in(self):
        alice=self.login();data={'week':self.week,'scope':'class'}
        self.assertEqual(self.raw('/api/export',data)[0],401)
        self.assertEqual(self.raw('/api/export',data,alice)[0],403)
        for include,expected in [(False,'0.00'),(True,'1.00')]:
            status,content,_=self.raw('/api/export',{'week':self.week,'scope':'student','member':'bob','format':'summary','includePending':include},alice)
            self.assertEqual(status,200);rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['Username'],'alice');self.assertEqual(rows[0]['Hours'],expected)
    def test_forgotten_timer_threshold_and_private_snooze(self):
        n=time.time();sessions=[dict(self.session,start=n-9*3600,end=None),dict(self.session,id='b',member='bob',start=n-10*3600,end=None)]
        alice=self.login();admin=self.login('admin')
        with patch.object(self.s,'state',return_value=([],sessions)):
            _,result,_=self.request('/api/reminders',{},alice)
            self.assertEqual([x['member'] for x in result['timerReminders']],['alice'])
            self.assertEqual(self.request('/api/timer-snooze',{'card':'c','member':'bob'},alice)[0],200)
            _,result,_=self.request('/api/reminders',{},alice);self.assertTrue(result['timerReminders'][0]['snoozed'])
            with self.s.connect() as db:self.assertIsNone(self.s.get(db,'timer_snooze:c:bob'))
            self.assertEqual(self.request('/api/timer-settings',{'hours':12},alice)[0],403)
            for hours in (0,73,'NaN','Infinity'):self.assertEqual(self.request('/api/timer-settings',{'hours':hours},admin)[0],400)
            self.assertEqual(self.request('/api/timer-settings',{'hours':12},admin)[0],200)
            self.assertEqual(self.request('/api/reminders',{},alice)[1]['timerReminders'],[])
    def test_timer_streak_spans_touching_assignment_splits(self):
        n=time.time();sessions=[dict(self.session,start=n-9*3600,end=n-3600),dict(self.session,id='next',start=n-3600,end=None)]
        with self.s.connect() as db:
            user=db.execute("SELECT * FROM users WHERE id='alice'").fetchone()
            self.assertEqual(len(productivity.timer_reminders(db,sessions,user,n)),1)
            sessions[1]['start']+=1
            self.assertEqual(productivity.timer_reminders(db,sessions,user,n),[])
    def test_backup_api_permissions_and_download(self):
        alice=self.login();admin=self.login('admin')
        for path in ('/api/backups','/api/backup-now','/api/backup-download'):
            self.assertEqual(self.raw(path,{},alice)[0],403);self.assertEqual(self.raw(path,{})[0],401)
        status,result,_=self.request('/api/backup-now',{},admin);self.assertEqual(status,200)
        status,content,headers=self.raw('/api/backup-download',{'name':result['name']},admin)
        self.assertEqual(status,200);self.assertTrue(content.startswith(b'SQLite format 3\x00'));self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.raw('/api/backup-download',{'name':'../tracker.db'},admin)[0],400)
        self.assertEqual(len(self.request('/api/backups',{},admin)[1]['files']),1)

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.database=Path(self.tmp.name)/'live.sqlite3';self.folder=Path(self.tmp.name)/'copies'
        self.env=patch.dict(os.environ,{'BACKUP_DIRECTORY':str(self.folder),'BACKUP_KEEP':'2','BACKUP_INTERVAL_HOURS':'6'});self.env.start()
        con=sqlite3.connect(self.database);con.execute('CREATE TABLE records(value TEXT)');con.execute("INSERT INTO records VALUES('original')");con.commit();con.close()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def test_verified_snapshot_restore_and_no_overwrite(self):
        name=backups.snapshot(self.database,threading.RLock());path=backups.download_path(self.database,name)
        restored=Path(self.tmp.name)/'restored.sqlite3';backups.restore_copy(path,restored)
        con=sqlite3.connect(restored)
        try:self.assertEqual(con.execute('SELECT value FROM records').fetchone()[0],'original');self.assertEqual(con.execute('PRAGMA quick_check').fetchone()[0],'ok')
        finally:con.close()
        with self.assertRaises(FileExistsError):backups.restore_copy(path,restored)
    def test_rotation_and_failure_preserve_existing_snapshots(self):
        for _ in range(3):backups.snapshot(self.database,threading.RLock())
        self.assertEqual(len(backups.files(self.folder)),2)
        unrelated=self.folder/'unrelated.txt';unrelated.write_text('keep')
        names=[x.name for x in backups.files(self.folder)]
        with patch.object(backups.sqlite3,'connect',side_effect=sqlite3.OperationalError('offline')):
            with self.assertRaises(sqlite3.OperationalError):backups.snapshot(self.database,threading.RLock())
        self.assertEqual([x.name for x in backups.files(self.folder)],names);self.assertTrue(unrelated.exists())
        current=backups.status(self.database);self.assertIsNotNone(current['error']);self.assertIsNotNone(current['lastSuccess'])
    def test_automatic_schedule_creates_first_copy_and_waits_after_success(self):
        backups.run_due(self.database,threading.RLock());self.assertEqual(len(backups.files(self.folder)),1)
        with patch.object(backups,'snapshot') as snapshot:backups.run_due(self.database,threading.RLock());snapshot.assert_not_called()
        for value in ('../file','acetime-bad.sqlite3','status.json'):
            with self.assertRaises(ValueError):backups.download_path(self.database,value)
