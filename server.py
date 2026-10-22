import os,json,sqlite3,time,secrets,hashlib,hmac,base64,urllib.request,urllib.parse,urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from engine import replay,stamp,summarize,break_reminder
ROOT=Path(__file__).parent
DB=os.getenv('DATABASE_PATH','data/tracker.db'); Path(DB).parent.mkdir(parents=True,exist_ok=True)
ORIGIN=os.getenv('PUBLIC_URL','http://localhost:8080').rstrip('/')
TZ=ZoneInfo(os.getenv('TIMEZONE','America/New_York'))
def connect():
    db=sqlite3.connect(DB,timeout=30); db.row_factory=sqlite3.Row; return db
def password(p,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),310000).hex()
def valid_password(p,stored): return hmac.compare_digest(password(p,stored.split(':')[0]),stored)
def init():
    with connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,password TEXT NOT NULL,member TEXT,admin INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS logins(token TEXT PRIMARY KEY,user TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS confirmations(session TEXT PRIMARY KEY,seconds REAL NOT NULL,member TEXT NOT NULL,by_user TEXT NOT NULL,note TEXT NOT NULL,at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,at REAL NOT NULL);''')
        if not db.execute('SELECT 1 FROM users WHERE admin=1').fetchone():
            p=os.getenv('ADMIN_PASSWORD','')
            if len(p)<12: raise RuntimeError('Set ADMIN_PASSWORD to at least 12 characters before starting.')
            db.execute('INSERT INTO users VALUES(?,?,?,?,1)',('admin','Instructor',password(p),None))
def get(db,key,default=None):
    row=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default
def put(db,key,v): db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(key,json.dumps(v)))
def trello(path,params=None,method='GET'):
    key,token=os.getenv('TRELLO_KEY'),os.getenv('TRELLO_TOKEN')
    if not key or not token: raise ValueError('Configure TRELLO_KEY and TRELLO_TOKEN on the server first.')
    q=dict(params or {},key=key,token=token)
    url='https://api.trello.com/1/'+path
    data=None
    if method=='GET': url+='?'+urllib.parse.urlencode(q)
    else: data=urllib.parse.urlencode(q).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=data,method=method),timeout=25) as r:return json.load(r)
    except urllib.error.HTTPError as e: raise ValueError(f'Trello returned HTTP {e.code}; check permissions or retry later.') from None
    except (TimeoutError,urllib.error.URLError): raise ValueError('Trello is unavailable; please retry.') from None

def state(db):
    cfg=get(db,'config'); base=get(db,'baseline')
    if not cfg or not base: return [],[]
    ev=[json.loads(r[0]) for r in db.execute('SELECT payload FROM events')]
    return replay(base,ev,cfg['lists'],time.time())
def sync(db):
    cfg=get(db,'config')
    if not cfg: raise ValueError('Choose a board and map its lists first.')
    base=get(db,'baseline'); since=datetime.fromtimestamp(base['started'],TZ).isoformat()
    before=None; actions=[]
    for _ in range(100):
        q={'since':since,'limit':1000,'filter':'all'}
        if before:q['before']=before
        batch=trello('boards/'+cfg['board']+'/actions',q)
        actions.extend(batch)
        if len(batch)<1000:break
        before=batch[-1]['id']
    else: raise ValueError('History exceeds the sync limit. No partial sync was saved.')
    for a in actions:db.execute('INSERT OR IGNORE INTO events VALUES(?,?)',(a['id'],json.dumps(a)))
    members=trello('boards/'+cfg['board']+'/members',{'fields':'fullName,username'})
    put(db,'members',members);put(db,'last_sync',time.time())


def break_settings(db):
    return get(db,'break_settings',{'defaultHours':4.0,'overrides':{}})

def reminders(db,sessions,user):
    settings=break_settings(db)
    mids={s['member'] for s in sessions} | {m['id'] for m in get(db,'members',[])} if user['admin'] else {user['member']}
    return {m:break_reminder(sessions,m,time.time(),settings['overrides'].get(m,settings['defaultHours']),get(db,'break_snooze:'+m)) for m in mids if m}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass # Avoid logging URLs, passwords, webhook bodies or tokens.
    def send(self,data,status=200,headers=None):
        raw=json.dumps(data).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def body(self):
        n=int(self.headers.get('Content-Length','0'))
        if n>1048576:raise ValueError('Request too large.')
        return self.rfile.read(n)
    def user(self,db):
        c=SimpleCookie(self.headers.get('Cookie','')); token=c.get('session')
        if not token:return None
        return db.execute('SELECT users.* FROM logins JOIN users ON users.id=logins.user WHERE token=? AND expires>?',(hashlib.sha256(token.value.encode()).hexdigest(),time.time())).fetchone()
    def do_HEAD(self):
        self.send_response(200 if self.path=='/webhook' else 404);self.end_headers()
    def do_GET(self):
        if self.path in ('/','/app.js','/break-reminders.js','/style.css'):
            path=ROOT/'static'/({'/':'index.html'}.get(self.path,self.path[1:]))
            raw=path.read_bytes();self.send_response(200)
            self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript','css':'text/css'}[path.suffix[1:]])
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw);return
        if self.path=='/health':self.send({'ok':True});return
        self.send({'error':'Not found'},404)
    def do_POST(self):
        try:
            raw=self.body()
            if self.path=='/webhook':return self.webhook(raw)
            if self.headers.get('Origin')!=ORIGIN:return self.send({'error':'Origin not allowed'},403)
            data=json.loads(raw or b'{}')
            with connect() as db:
                user=self.user(db)
                if self.path=='/api/login':
                    # Bounded persisted rate limit by account; invalid users share a bucket.
                    uid=str(data.get('username',''))[:100]; target=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                    bucket='attempt:'+ (uid if target else 'unknown'); attempts=get(db,bucket,[])
                    attempts=[t for t in attempts if t>time.time()-900]
                    if len(attempts)>=10:return self.send({'error':'Too many attempts. Try again in 15 minutes.'},429)
                    if not target or not valid_password(str(data.get('password','')),target['password']):
                        attempts.append(time.time());put(db,bucket,attempts);db.commit();return self.send({'error':'Invalid login'},401)
                    put(db,bucket,[]);token=secrets.token_urlsafe(32)
                    db.execute('INSERT INTO logins VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+43200))
                    return self.send({'ok':True},headers={'Set-Cookie':f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'+('; Secure' if ORIGIN.startswith('https:') else '')})
                if not user:return self.send({'error':'Please sign in.'},401)
                if self.path=='/api/logout':
                    db.execute('DELETE FROM logins WHERE user=?',(user['id'],));return self.send({'ok':True},headers={'Set-Cookie':'session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})
                admin=bool(user['admin'])
                if self.path in ('/api/boards','/api/inspect','/api/config','/api/users','/api/webhook','/api/break-settings') and not admin:return self.send({'error':'Instructor access required'},403)
                if self.path=='/api/boards':return self.send(trello('members/me/boards',{'fields':'name,url','filter':'open'}))
                if self.path=='/api/inspect':
                    bid=str(data['board'])
                    if not bid.isalnum():raise ValueError('Invalid board ID')
                    return self.send({'lists':trello('boards/'+bid+'/lists',{'fields':'name'}),'members':trello('boards/'+bid+'/members',{'fields':'fullName,username'})})
                if self.path=='/api/config':
                    if get(db,'config'):raise ValueError('Tracking is already configured. List mapping is immutable to preserve recorded time; use a new database for another board.')
                    bid=str(data['board']); lists=data['lists']
                    available={l['id'] for l in trello('boards/'+bid+'/lists',{'fields':'name'})}
                    if set(lists)!= {'backlog','active','blocked','done'} or len(set(lists.values()))!=4 or not set(lists.values())<=available:raise ValueError('Choose four distinct lists on the selected board.')
                    cards=trello('boards/'+bid+'/cards',{'fields':'name,idList,idMembers,closed,url','filter':'all'})
                    members=trello('boards/'+bid+'/members',{'fields':'fullName,username'})
                    started=time.time();put(db,'baseline',{'cards':cards,'started':started});put(db,'members',members)
                    put(db,'config',{'board':bid,'lists':lists});return self.send({'ok':True})
                if self.path=='/api/users':
                    uid=str(data.get('username','')).strip();p=str(data.get('password',''));mid=data.get('member')
                    members={m['id'] for m in get(db,'members',[])}
                    if not uid or len(uid)>80 or len(p)<12 or mid not in members:raise ValueError('Use a username, password of at least 12 characters, and a board member.')
                    if db.execute('SELECT 1 FROM users WHERE id=? OR member=?',(uid,mid)).fetchone():raise ValueError('Username or Trello member already has an account.')
                    db.execute('INSERT INTO users VALUES(?,?,?,?,0)',(uid,str(data.get('name') or uid)[:100],password(p),mid));return self.send({'ok':True})
                if self.path=='/api/webhook':
                    if not os.getenv('TRELLO_SECRET'):raise ValueError('Configure TRELLO_SECRET (the API application secret) before enabling webhooks.')
                    if not ORIGIN.startswith('https://') and not (ORIGIN.startswith('http://') and os.getenv('ALLOW_HTTP','false').lower()=='true'):raise ValueError('Webhooks require HTTPS, or explicit ALLOW_HTTP=true for an HTTP pilot. The callback must be reachable by Trello.')
                    cfg=get(db,'config')
                    if not cfg:raise ValueError('Configure the board first.')
                    old=get(db,'webhook')
                    if old:return self.send({'ok':True,'alreadyRegistered':True})
                    r=trello('webhooks',{'idModel':cfg['board'],'callbackURL':ORIGIN+'/webhook','description':'ACETime student time tracker'},'POST');put(db,'webhook',{'id':r['id']});return self.send({'ok':True})
                if self.path=='/api/sync':
                    if not admin:return self.send({'error':'Instructor sync required'},403)
                    sync(db);return self.send({'ok':True})
                if self.path=='/api/break-settings':
                    import math
                    settings=break_settings(db);mid=data.get('member')
                    if mid and mid not in {m['id'] for m in get(db,'members',[])}:raise ValueError('Choose a member of the configured board.')
                    if mid and data.get('reset'):
                        settings['overrides'].pop(mid,None)
                    else:
                        hours=float(data['hours'])
                        if not math.isfinite(hours) or not 0.25 <= hours <= 24:raise ValueError('Break reminder hours must be between 0.25 and 24.')
                        if mid:settings['overrides'][mid]=hours
                        else:settings['defaultHours']=hours
                    put(db,'break_settings',settings)
                    db.execute('INSERT INTO audit(payload,at) VALUES(?,?)',(json.dumps({'action':'break-settings','member':mid,'settings':settings,'user':user['id']}),time.time()))
                    return self.send({'ok':True})
                cards,sessions=state(db);cardmap={c['id']:c for c in cards}
                member=user['member']
                if admin:member=data.get('member') or member
                if self.path=='/api/reminders':
                    return self.send({'reminders':reminders(db,sessions,user)})
                if self.path=='/api/snooze-break':
                    # A student can snooze only their own reminder; request member IDs are ignored.
                    mid=user['member']
                    if not mid:raise ValueError('Student login required to snooze a break reminder.')
                    r=reminders(db,sessions,user).get(mid)
                    if not r or not r['notify']:raise ValueError('No active break reminder to snooze.')
                    put(db,'break_snooze:'+mid,{'streakStart':r['streakStart'],'until':time.time()+900})
                    return self.send({'ok':True})
                if self.path=='/api/verify':
                    cid=data['card'];cfg=get(db,'config',{})
                    if not member:raise ValueError('Select a student first.')
                    if cardmap.get(cid,{}).get('idList')!=cfg.get('lists',{}).get('done'):raise ValueError('Card must be in Completed before verification.')
                    if any(s['card']==cid and s['member']==member and s['end'] is None for s in sessions):raise ValueError('The timer is still running.')
                    pending=[s for s in sessions if s['card']==cid and s['member']==member and not db.execute('SELECT 1 FROM confirmations WHERE session=?',(s['id'],)).fetchone()]
                    if not pending:raise ValueError('Time has already been verified. Refresh the page.')
                    import math
                    hours=float(data['hours']);note=str(data.get('note','')).strip()[:2000]
                    total=sum(s['end']-s['start'] for s in pending)
                    if not math.isfinite(hours) or hours<0 or hours>total/3600+0.02:raise ValueError('Confirmed hours must be between zero and elapsed time.')
                    if abs(hours*3600-total)>60 and not note:raise ValueError('Explain the time adjustment for the audit record.')
                    for s in pending:
                        db.execute('INSERT INTO confirmations VALUES(?,?,?,?,?,?)',(s['id'],hours*3600*(s['end']-s['start'])/total,member,user['id'],note,time.time()))
                    db.execute('INSERT INTO audit(payload,at) VALUES(?,?)',(json.dumps({'card':cid,'member':member,'user':user['id'],'hours':hours,'note':note,'sessions':[s['id'] for s in pending]}),time.time()))
                    return self.send({'ok':True})
                if self.path=='/api/state':
                    cf={r['session']:r['seconds'] for r in db.execute('SELECT * FROM confirmations')}
                    if not admin:sessions=[s for s in sessions if s['member']==member];cards=[c for c in cards if member in c.get('idMembers',[]) or any(s['card']==c['id'] for s in sessions)]
                    return self.send({'user':{'name':user['name'],'admin':admin,'member':user['member']},'config':get(db,'config'),'members':get(db,'members',[]) if admin else [],'cards':cards,'sessions':sessions,'confirmations':{s['id']:cf[s['id']] for s in sessions if s['id'] in cf},'breakReminders':reminders(db,sessions,user),'breakSettings':break_settings(db) if admin else None,'lastSync':get(db,'last_sync'),'webhook':bool(get(db,'webhook')),'timezone':str(TZ)})
                if self.path=='/api/report':
                    if not member:raise ValueError('Select a student.')
                    start=datetime.strptime(data['week'],'%Y-%m-%d').replace(tzinfo=TZ)
                    if start.weekday()!=0:raise ValueError('Choose a Monday for week start.')
                    end=start+timedelta(days=7)
                    cf={r['session']:r['seconds'] for r in db.execute('SELECT * FROM confirmations WHERE member=?',(member,))}
                    rows=summarize(sessions,cf,cardmap,member,start.timestamp(),end.timestamp(),time.time(),not data.get('includePending',False))
                    cfg=get(db,'config',{}).get('lists',{})
                    labels={cfg.get('active'):'In process',cfg.get('blocked'):'Blocked',cfg.get('done'):'Completed',cfg.get('backlog'):'Backlog'}
                    for r in rows:r['progress']=labels.get(r.pop('list'),'Other')+(' — verified' if r['verified'] else ' — unverified')
                    return self.send({'rows':rows,'total':sum(r['seconds'] for r in rows)/3600,'timezone':str(TZ)})
                self.send({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.send({'error':str(e)},400)
        except Exception:self.send({'error':'Server error. Check configuration and retry.'},500)
    def webhook(self,raw):
        secret=os.getenv('TRELLO_SECRET','')
        expected=base64.b64encode(hmac.new(secret.encode(),raw+(ORIGIN+'/webhook').encode(),hashlib.sha1).digest()).decode()
        if not secret or not hmac.compare_digest(expected,self.headers.get('X-Trello-Webhook','')):return self.send({'error':'Invalid signature'},401)
        payload=json.loads(raw);action=payload.get('action',{})
        with connect() as db:
            cfg=get(db,'config')
            if not cfg or payload.get('model',{}).get('id')!=cfg['board']:return self.send({'error':'Wrong board'},403)
            if action.get('id') and action.get('date') and action.get('type'):
                db.execute('INSERT OR IGNORE INTO events VALUES(?,?)',(action['id'],json.dumps(action)));put(db,'last_sync',time.time())
        self.send({'ok':True})
if __name__=='__main__':
    init();ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
