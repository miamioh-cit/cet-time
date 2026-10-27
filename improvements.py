"""Review, correction, account and tracking-health workflows."""
import hashlib
import json
import math
import time
import uuid


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS account_status(user TEXT PRIMARY KEY,disabled INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS corrections(id TEXT PRIMARY KEY,member TEXT NOT NULL,requester TEXT NOT NULL,
      payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',reviewer TEXT,review_note TEXT,created REAL NOT NULL,reviewed REAL);
    CREATE TABLE IF NOT EXISTS manual_sessions(id TEXT PRIMARY KEY,card TEXT NOT NULL,member TEXT NOT NULL,start REAL NOT NULL,end REAL NOT NULL);
    ''')


def audit(db, actor, action, **details):
    db.execute('INSERT INTO audit(payload,at) VALUES(?,?)',
               (json.dumps(dict(action=action,user=actor,**details)),time.time()))


def disabled(db, uid):
    row=db.execute('SELECT disabled FROM account_status WHERE user=?',(uid,)).fetchone()
    return bool(row and row[0])


def fingerprint(session, confirmed):
    return hashlib.sha256(json.dumps([session,confirmed],sort_keys=True).encode()).hexdigest()


def overlaps(sessions, now):
    result=[]
    by_member={}
    for s in sessions:
        by_member.setdefault(s['member'],[]).append(s)
    for member, items in by_member.items():
        active=[]
        for s in sorted(items,key=lambda x:x['start']):
            active=[a for a in active if (a['end'] if a['end'] is not None else now)>s['start']]
            for a in active:
                end=min(a['end'] if a['end'] is not None else now,s['end'] if s['end'] is not None else now)
                if a['card']!=s['card'] and end>s['start']:
                    result.append(dict(member=member,cards=[a['card'],s['card']],start=s['start'],end=end,
                                       seconds=end-s['start'],running=a['end'] is None and s['end'] is None))
            active.append(s)
    return result


def account_route(handler, db, user, data):
    import server as s
    path=handler.path
    if path not in ('/api/password','/api/accounts','/api/account-action'):return False
    admin=bool(user['admin'])
    if path=='/api/password':
        if not s.valid_password(str(data.get('current','')),user['password']):raise ValueError('Current password is incorrect.')
        new=str(data.get('password',''))
        if len(new)<12:raise ValueError('Use a password of at least 12 characters.')
        db.execute('UPDATE users SET password=? WHERE id=?',(s.password(new),user['id']))
        db.execute('DELETE FROM logins WHERE user=?',(user['id'],))
        audit(db,user['id'],'password-change')
        handler.send({'ok':True,'signInAgain':True});return True
    if not admin:handler.send({'error':'Instructor access required'},403);return True
    if path=='/api/accounts':
        handler.send({'accounts':[dict(id=r['id'],name=r['name'],member=r['member'],admin=bool(r['admin']),disabled=disabled(db,r['id'])) for r in db.execute('SELECT * FROM users ORDER BY name')]});return True
    target=db.execute('SELECT * FROM users WHERE id=?',(str(data.get('user','')),)).fetchone()
    if not target:raise ValueError('Account not found.')
    action=data.get('action')
    if target['admin'] and action in ('disable','enable','reset'):raise ValueError('Instructor accounts manage their own password; student access controls apply to student accounts.')
    if action=='reset':
        new=str(data.get('password',''))
        if len(new)<12:raise ValueError('Use a password of at least 12 characters.')
        db.execute('UPDATE users SET password=? WHERE id=?',(s.password(new),target['id']))
        s.put(db,'attempt:'+target['id'],[])
    elif action in ('disable','enable'):
        db.execute('INSERT OR REPLACE INTO account_status VALUES(?,?)',(target['id'],int(action=='disable')))
    elif action!='revoke':raise ValueError('Unknown account action.')
    db.execute('DELETE FROM logins WHERE user=?',(target['id'],))
    audit(db,user['id'],'account-'+action,target=target['id'])
    handler.send({'ok':True,'signInAgain':target['id']==user['id']});return True


def health(db):
    import server as s
    last=s.get(db,'last_sync')
    error=s.get(db,'sync_error')
    return dict(lastWebhook=s.get(db,'last_webhook'),lastSync=last,lastAttempt=s.get(db,'sync_attempt'),
                error=error,possiblyIncomplete=bool(error or not last or time.time()-last>900),
                automaticSyncSeconds=300,webhookRegistered=bool(s.get(db,'webhook')))


def route(handler,db,user,data,cards,sessions):
    import server as s
    path=handler.path;admin=bool(user['admin']);mid=user['member'];now=time.time()
    if path not in ('/api/review','/api/corrections','/api/correction-request','/api/correction-review'):return False
    cf={r['session']:r['seconds'] for r in db.execute('SELECT * FROM confirmations')}
    if path in ('/api/corrections','/api/review'):
        if path=='/api/review' and not admin:handler.send({'error':'Instructor access required'},403);return True
        requests=[dict(r,payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM corrections ORDER BY created DESC') if admin or r['member']==mid]
        result={'requests':requests}
        if path=='/api/review':
            cardmap={c['id']:c for c in cards};done=s.get(db,'config',{}).get('lists',{}).get('done')
            result.update(health=health(db),overlaps=overlaps(sessions,now),
                pending=[x for x in sessions if x['end'] is not None and x['id'] not in cf and cardmap.get(x['card'],{}).get('idList')==done],
                longTimers=[x for x in sessions if (x['end'] if x['end'] is not None else now)-x['start']>12*3600],
                adjustments=[dict(r) for r in db.execute('SELECT * FROM confirmations') if any(x['id']==r['session'] and abs((x['end'] or now)-x['start']-r['seconds'])>900 for x in sessions)],
                audit=[dict(payload=json.loads(r['payload']),at=r['at']) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200')])
        handler.send(result);return True
    if path=='/api/correction-request':
        member=data.get('member') if admin else mid
        if not member or not db.execute('SELECT 1 FROM users WHERE member=?',(member,)).fetchone():raise ValueError('Choose a registered student.')
        note=str(data.get('note','')).strip()
        if not note or len(note)>2000:raise ValueError('Explain the correction (up to 2000 characters).')
        hours=float(data['hours'])
        if not math.isfinite(hours) or not 0<=hours<=24:raise ValueError('Requested hours must be between 0 and 24.')
        sid=data.get('session');existing=next((x for x in sessions if x['id']==sid and x['member']==member),None)
        if sid:
            if not existing or existing['end'] is None:raise ValueError('Choose one of the student’s finished intervals.')
            payload=dict(session=sid,card=existing['card'],start=existing['start'],end=existing['end'],
                         previousSeconds=cf.get(sid),snapshot=fingerprint(existing,cf.get(sid)),hours=hours,note=note)
        else:
            cid=str(data.get('card',''));card=next((c for c in cards if c['id']==cid),None)
            if not card or not (member in card.get('idMembers',[]) or any(x['card']==cid and x['member']==member for x in sessions)):raise ValueError('Choose a task assigned to this student.')
            start=s.stamp(str(data['start']));end=s.stamp(str(data['end']))
            if not all(math.isfinite(x) for x in (start,end)) or not 0<end-start<=86400 or end>now:raise ValueError('Choose a finished work interval of at most 24 hours.')
            if hours*3600>end-start+1:raise ValueError('Hours cannot exceed the manual interval.')
            payload=dict(card=cid,start=start,end=end,hours=hours,note=note)
        # One pending request per recorded interval prevents accidental repeated submissions.
        if sid and any(json.loads(r[0]).get('session')==sid for r in db.execute("SELECT payload FROM corrections WHERE member=? AND status='pending'",(member,))):raise ValueError('This interval already has a pending request.')
        rid=uuid.uuid4().hex
        db.execute('INSERT INTO corrections(id,member,requester,payload,created) VALUES(?,?,?,?,?)',(rid,member,user['id'],json.dumps(payload),now))
        audit(db,user['id'],'correction-request',request=rid,member=member,payload=payload)
        handler.send({'ok':True});return True
    if not admin:handler.send({'error':'Instructor access required'},403);return True
    req=db.execute('SELECT * FROM corrections WHERE id=?',(str(data.get('id','')),)).fetchone()
    if not req or req['status']!='pending':raise ValueError('Request is no longer pending.')
    decision=data.get('decision');note=str(data.get('note','')).strip()
    if decision not in ('approved','rejected') or not note or len(note)>2000:raise ValueError('Choose approve or reject and enter a review note.')
    payload=json.loads(req['payload']);sid=payload.get('session')
    if decision=='approved':
        if sid:
            existing=next((x for x in sessions if x['id']==sid and x['member']==req['member']),None)
            if not existing or fingerprint(existing,cf.get(sid))!=payload['snapshot']:raise ValueError('The interval changed. Reject this request and submit a fresh correction.')
        else:
            sid='manual:'+req['id']
            db.execute('INSERT INTO manual_sessions VALUES(?,?,?,?,?)',(sid,payload['card'],req['member'],payload['start'],payload['end']))
        db.execute('INSERT OR REPLACE INTO confirmations VALUES(?,?,?,?,?,?)',(sid,payload['hours']*3600,req['member'],user['id'],payload['note'],now))
    db.execute('UPDATE corrections SET status=?,reviewer=?,review_note=?,reviewed=? WHERE id=?',(decision,user['id'],note,now,req['id']))
    audit(db,user['id'],'correction-'+decision,request=req['id'],note=note,previousSeconds=cf.get(sid),payload=payload)
    handler.send({'ok':True});return True
