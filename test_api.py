import unittest,tempfile,os,json,threading,time,urllib.request,urllib.error,base64,hmac,hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer
from datetime import datetime,timezone
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();os.environ['DATABASE_PATH']=str(Path(cls.tmp.name)/'db.sqlite');os.environ['ADMIN_PASSWORD']='test-admin-only-12345';os.environ['TRELLO_SECRET']='test-secret'
        import server
        cls.s=server;server.init();cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.origin=f'http://127.0.0.1:{cls.http.server_port}';server.ORIGIN=cls.origin
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.n=time.time();cls.mid='alice';cls.other='bob'
        with server.connect() as db:
            server.put(db,'config',{'board':'board','lists':{'backlog':'todo','active':'working','blocked':'paused','done':'done'}})
            server.put(db,'baseline',{'started':cls.n-10000,'cards':[{'id':'c','name':'Group task','idList':'todo','idMembers':['alice','bob']}]})
            server.put(db,'members',[{'id':'alice','fullName':'Alice'},{'id':'bob','fullName':'Bob'}])
            for m in ('alice','bob'):db.execute('INSERT INTO users VALUES(?,?,?,?,0)',(m,m,server.password('test-student-only-12345'),m))
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
    def request(self,path,data=None,cookie=None,origin=True,headers=None):
        h={'Content-Type':'application/json',**(headers or {})}
        if origin:h['Origin']=self.origin
        if cookie:h['Cookie']=cookie
        raw=data if isinstance(data,bytes) else json.dumps(data or {}).encode()
        try:r=urllib.request.urlopen(urllib.request.Request(self.origin+path,data=raw,headers=h),timeout=5)
        except urllib.error.HTTPError as e:r=e
        return r.status,json.load(r),r.headers
    def login(self,uid='alice'):
        p='test-admin-only-12345' if uid=='admin' else 'test-student-only-12345'
        status,_,h=self.request('/api/login',{'username':uid,'password':p});self.assertEqual(status,200)
        return h['Set-Cookie'].split(';')[0]
    def test_01_auth_roles_and_origin(self):
        self.assertEqual(self.request('/api/state')[0],401)
        c=self.login();self.assertEqual(self.request('/api/users',{},c)[0],403)
        self.assertEqual(self.request('/api/state',{},c,False)[0],403)
    def test_02_invalid_webhook_signature(self):self.assertEqual(self.request('/webhook',{'x':'y'},origin=False)[0],401)
    def test_03_webhooks_dedup_group_verify_report(self):
        for eid,offset,before,after in [('start',-7200,'todo','working'),('pause',-3600,'working','paused'),('resume',-1800,'paused','working'),('complete',-900,'working','done')]:
            e={'model':{'id':'board'},'action':{'id':eid,'date':datetime.fromtimestamp(self.n+offset,timezone.utc).isoformat(),'type':'updateCard','data':{'card':{'id':'c','name':'Group task'},'old':{'idList':before},'listAfter':{'id':after}}}}
            raw=json.dumps(e).encode();sig=base64.b64encode(hmac.new(b'test-secret',raw+(self.origin+'/webhook').encode(),hashlib.sha1).digest()).decode()
            for _ in range(2):self.assertEqual(self.request('/webhook',raw,origin=False,headers={'X-Trello-Webhook':sig})[0],200)
        c=self.login();status,s,_=self.request('/api/state',{},c)
        self.assertEqual(len(s['sessions']),2);self.assertTrue(all(x['member']=='alice' for x in s['sessions']))
        self.assertEqual(sum(x['end']-x['start'] for x in s['sessions']),4500)
        # Supplying Bob's member ID must still confirm only Alice's time.
        status,_,_=self.request('/api/verify',{'card':'c','member':'bob','hours':1,'note':'Breaks'},c);self.assertEqual(status,200)
        with self.s.connect() as db:self.assertEqual({r['member'] for r in db.execute('SELECT * FROM confirmations')},{'alice'})
        local=datetime.fromtimestamp(self.n,self.s.TZ);from datetime import timedelta
        week=(local-timedelta(days=local.weekday())).strftime('%Y-%m-%d')
        status,report,_=self.request('/api/report',{'member':'bob','week':week},c)
        self.assertEqual(status,200);self.assertAlmostEqual(report['total'],1)
        self.assertEqual(self.request('/api/verify',{'card':'c','hours':1},c)[0],400)
    def test_04_student_cannot_fetch_other_student_report(self):
        c=self.login('bob');_,r,_=self.request('/api/state',{},c)
        self.assertTrue(all(s['member']=='bob' for s in r['sessions']))
        self.assertEqual(r['confirmations'],{})
    def test_05_break_reminders_are_private_and_snooze_is_own(self):
        from unittest.mock import patch
        n=time.time();sessions=[{'id':'a','card':'c','member':'alice','start':n-14500,'end':None},{'id':'b','card':'c','member':'bob','start':n-100,'end':None}]
        with patch.object(self.s,'state',return_value=([],sessions)):
            c=self.login('alice');status,r,_=self.request('/api/reminders',{'member':'bob'},c)
            self.assertEqual(status,200);self.assertEqual(set(r['reminders']),{'alice'});self.assertTrue(r['reminders']['alice']['notify'])
            self.assertEqual(self.request('/api/snooze-break',{'member':'bob'},c)[0],200)
            _,r,_=self.request('/api/reminders',{},c);self.assertFalse(r['reminders']['alice']['notify'])
            with self.s.connect() as db:
                self.assertIsNone(self.s.get(db,'break_snooze:bob'))
    def test_06_only_instructor_can_change_default_and_individual_thresholds(self):
        c=self.login('alice');self.assertEqual(self.request('/api/break-settings',{'hours':2},c)[0],403)
        admin=self.login('admin')
        self.assertEqual(self.request('/api/break-settings',{'hours':3},admin)[0],200)
        self.assertEqual(self.request('/api/break-settings',{'hours':2,'member':'alice'},admin)[0],200)
        _,s,_=self.request('/api/state',{},admin)
        self.assertEqual(s['breakSettings'],{'defaultHours':3,'overrides':{'alice':2}})
        for hours in (0,25,'NaN','Infinity'):
            self.assertEqual(self.request('/api/break-settings',{'hours':hours},admin)[0],400)
        self.assertEqual(self.request('/api/break-settings',{'hours':2,'member':'not-on-board'},admin)[0],400)
        self.assertEqual(self.request('/api/break-settings',{'member':'alice','reset':True},admin)[0],200)
        _,s,_=self.request('/api/state',{},admin);self.assertEqual(s['breakSettings']['overrides'],{})
if __name__=='__main__':unittest.main()
