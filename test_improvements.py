import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime,timedelta,timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import test_api
import improvements


class ImprovementTests(unittest.TestCase):
    request=test_api.ApiTests.request
    login=test_api.ApiTests.login

    def setUp(self):
        import server
        self.s=server;self.tmp=tempfile.TemporaryDirectory();self.old_db=server.DB;self.old_origin=server.ORIGIN
        server.DB=str(Path(self.tmp.name)/'db.sqlite')
        with patch.dict(os.environ,{'ADMIN_PASSWORD':'test-admin-only-12345'}):server.init()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.origin=f'http://127.0.0.1:{self.http.server_port}';server.ORIGIN=self.origin
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.n=time.time();self.session={'id':'recorded','card':'c','member':'alice','start':self.n-7200,'end':self.n-3600}
        with server.connect() as db:
            server.put(db,'config',{'board':'b','lists':{'active':'working','done':'done','backlog':'todo','blocked':'paused'}})
            server.put(db,'baseline',{'started':self.n-10000,'cards':[{'id':'c','name':'Task','idList':'done','idMembers':['alice']}]})
            server.put(db,'members',[{'id':'alice','fullName':'Alice'},{'id':'bob','fullName':'Bob'}])
            for mid in ('alice','bob'):db.execute('INSERT INTO users VALUES(?,?,?,?,0)',(mid,mid,server.password('test-student-only-12345'),mid))
        self.real_state=server.state
        self.patcher=patch.object(server,'state',return_value=([{'id':'c','name':'Task','idList':'done','idMembers':['alice']}],[self.session]))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop();self.http.shutdown();self.http.server_close();self.thread.join()
        self.s.DB=self.old_db;self.s.ORIGIN=self.old_origin;self.tmp.cleanup()

    def submit(self,cookie=None,**changes):
        data={'session':'recorded','hours':.5,'note':'Time away from the task','member':'bob',**changes}
        return self.request('/api/correction-request',data,cookie or self.login())

    def request_id(self):
        with self.s.connect() as db:return db.execute('SELECT id FROM corrections').fetchone()[0]

    def review(self,rid,decision='approved',cookie=None):
        return self.request('/api/correction-review',{'id':rid,'decision':decision,'note':'Reviewed with student'},cookie or self.login('admin'))

    def test_correction_permissions_approval_and_report_totals(self):
        alice=self.login();self.assertEqual(self.submit(alice)[0],200)
        rid=self.request_id()
        self.assertEqual(self.review(rid,cookie=alice)[0],403)
        self.assertEqual(self.request('/api/review',{},alice)[0],403)
        self.assertEqual(self.request('/api/corrections',{},self.login('bob'))[1]['requests'],[])
        self.assertEqual(self.review(rid)[0],200)
        self.assertEqual(self.review(rid)[0],400)
        d=datetime.fromtimestamp(self.n,self.s.TZ);week=(d-timedelta(days=d.weekday())).strftime('%Y-%m-%d')
        self.assertAlmostEqual(self.request('/api/report',{'week':week},alice)[1]['total'],.5)
        with self.s.connect() as db:
            self.assertEqual(db.execute('SELECT member FROM confirmations').fetchone()[0],'alice')
            self.assertEqual(db.execute('SELECT count(*) FROM audit').fetchone()[0],2)

    def test_changed_confirmation_rejects_stale_approval(self):
        self.submit();rid=self.request_id()
        with self.s.connect() as db:db.execute('INSERT INTO confirmations VALUES(?,?,?,?,?,?)',('recorded',2000,'alice','alice','Updated',self.n))
        self.assertEqual(self.review(rid)[0],400)
        self.assertEqual(self.review(rid,'rejected')[0],200)

    def test_manual_work_survives_replay_and_appears_in_reports(self):
        alice=self.login();data={'session':'','card':'c','member':'bob','hours':.5,'note':'Forgot to move task',
            'start':datetime.fromtimestamp(self.n-7200,timezone.utc).isoformat(),'end':datetime.fromtimestamp(self.n-3600,timezone.utc).isoformat()}
        self.assertEqual(self.request('/api/correction-request',data,alice)[0],200)
        self.assertEqual(self.review(self.request_id())[0],200)
        with self.s.connect() as db:
            cards,sessions=self.real_state(db);self.assertEqual(len(sessions),1);self.assertEqual(sessions[0]['member'],'alice')
            d=datetime.fromtimestamp(self.n,self.s.TZ);start,end=self.s.report_week((d-timedelta(days=d.weekday())).strftime('%Y-%m-%d'))
            self.assertAlmostEqual(self.s.weekly_report(db,sessions,{c['id']:c for c in cards},'alice',start,end,False,self.n)['total'],.5)

    def test_request_validation_and_duplicate_submission(self):
        for fields in ({'hours':'NaN'},{'hours':25},{'note':''},{'session':'other'},{'session':'','card':'missing'}):
            self.assertEqual(self.submit(**fields)[0],400)
        self.assertEqual(self.submit()[0],200);self.assertEqual(self.submit()[0],400)

    def test_reset_disable_enable_and_revocation(self):
        alice=self.login();admin=self.login('admin')
        self.assertEqual(self.request('/api/accounts',{},alice)[0],403)
        self.assertEqual(self.request('/api/account-action',{'user':'bob','action':'disable'},alice)[0],403)
        for action in ('disable','enable'):
            self.assertEqual(self.request('/api/account-action',{'user':'alice','action':action},admin)[0],200)
            self.assertEqual(self.request('/api/state',{},alice)[0],401)
            if action=='disable':self.assertEqual(self.request('/api/login',{'username':'alice','password':'test-student-only-12345'})[0],401)
        alice=self.login()
        self.assertEqual(self.request('/api/account-action',{'user':'alice','action':'reset','password':'replacement-password-123'},admin)[0],200)
        self.assertEqual(self.request('/api/state',{},alice)[0],401)
        status,_,h=self.request('/api/login',{'username':'alice','password':'replacement-password-123'});self.assertEqual(status,200)
        new=h['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('/api/account-action',{'user':'alice','action':'revoke'},admin)[0],200)
        self.assertEqual(self.request('/api/state',{},new)[0],401)
        self.assertEqual(self.request('/api/account-action',{'user':'admin','action':'disable'},admin)[0],400)

    def test_password_change_checks_current_and_revokes_every_session(self):
        alice=self.login();second=self.login()
        self.assertEqual(self.request('/api/password',{'current':'wrong','password':'replacement-password-123'},alice)[0],400)
        self.assertEqual(self.request('/api/password',{'current':'test-student-only-12345','password':'replacement-password-123'},alice)[0],200)
        for cookie in (alice,second):self.assertEqual(self.request('/api/state',{},cookie)[0],401)

    def test_health_error_recovery_and_review_queue(self):
        with self.s.connect() as db:
            with patch.object(self.s,'trello',side_effect=ValueError('offline')):
                with self.assertRaises(ValueError):self.s.sync(db)
            self.assertTrue(improvements.health(db)['possiblyIncomplete'])
            self.assertIsNotNone(improvements.health(db)['error'])
            with patch.object(self.s,'trello',return_value=[]):self.s.sync(db)
            self.assertFalse(improvements.health(db)['possiblyIncomplete'])
        r=self.request('/api/review',{},self.login('admin'))[1]
        self.assertEqual(len(r['pending']),1);self.assertIsNone(r['health']['error'])

    def test_overlap_boundaries_and_student_privacy(self):
        sessions=[self.session,dict(self.session,id='second',card='other',start=self.n-5400),
                  dict(self.session,id='touching',card='third',start=self.n-3600,end=self.n)]
        overlaps=improvements.overlaps(sessions,self.n)
        self.assertEqual(len(overlaps),1);self.assertEqual(overlaps[0]['seconds'],1800)
        with patch.object(self.s,'state',return_value=([],sessions)):
            self.assertEqual(self.request('/api/state',{},self.login('bob'))[1]['overlaps'],[])

    def test_background_reconciliation_retries_after_failure(self):
        class Stop:
            count=0
            waits=[]
            def is_set(self):return self.count>=2
            def wait(self,seconds):self.waits.append(seconds);self.count+=1
        stop=Stop()
        with patch.object(self.s,'sync',side_effect=[ValueError('offline'),None]) as sync:
            self.s.reconcile_loop(stop)
        self.assertEqual(sync.call_count,2);self.assertEqual(stop.waits,[300,300])

    def test_additive_schema_preserves_accounts_and_confirmed_records(self):
        with self.s.connect() as db:
            db.execute('INSERT INTO confirmations VALUES(?,?,?,?,?,?)',('existing',1800,'alice','alice','Original note',self.n))
        self.s.init()
        with self.s.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],3)
            self.assertEqual(db.execute("SELECT note FROM confirmations WHERE session='existing'").fetchone()[0],'Original note')
