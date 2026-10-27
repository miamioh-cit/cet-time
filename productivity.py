"""Forgotten timers, weekly readiness, protected CSV downloads, and backup controls."""
import csv
import io
import math
import time
from datetime import datetime
import backups

def timer_settings(db):
    import server as s
    return s.get(db,'timer_settings',{'hours':8.0})

def timer_reminders(db,sessions,user,now):
    import server as s
    threshold=timer_settings(db)['hours']*3600
    grouped={}
    for x in sessions:
        if x['start']>now:continue
        if user['admin'] or x['member']==user['member']:
            grouped.setdefault((x['card'],x['member']),[]).append(x)
    result=[]
    for (card,member),items in grouped.items():
        streak=None;active=False
        for x in sorted(items,key=lambda x:x['start']):
            end=x['end'] if x['end'] is not None else now
            if streak is None or x['start']>streak[1]:streak=[x['start'],end];active=x['end'] is None
            else:streak[1]=max(streak[1],end);active|=x['end'] is None
        if active and now-streak[0]>=threshold:
            snooze=s.get(db,'timer_snooze:'+card+':'+member,{})
            result.append({'card':card,'member':member,'started':streak[0],'seconds':now-streak[0],
                           'thresholdHours':threshold/3600,'snoozed':snooze.get('started')==streak[0] and snooze.get('until',0)>now})
    return result

def students(db,user,member=None):
    if not user['admin']:return [user]
    rows=db.execute('SELECT id,name,member FROM users WHERE admin=0 AND member IS NOT NULL ORDER BY name COLLATE NOCASE,id').fetchall()
    if member:
        rows=[r for r in rows if r['member']==member]
        if not rows:raise ValueError('Choose a registered student.')
    return rows

def week_overlaps(item,start,end,now):
    return item['start']<end and (item['end'] if item['end'] is not None else now)>start

def checklist(db,user,data,cards,sessions,now):
    import server as s
    import improvements
    start,end=s.report_week(data['week']);a,b=start.timestamp(),end.timestamp()
    roster=students(db,user,data.get('member'));mids={r['member'] for r in roster}
    selected=[x for x in sessions if x['member'] in mids]
    current=[x for x in selected if week_overlaps(x,a,b,now)]
    cf={r['session']:r['seconds'] for r in db.execute('SELECT * FROM confirmations')}
    pending=[x for x in current if x['id'] not in cf]
    requests=[]
    for r in db.execute("SELECT member,payload FROM corrections WHERE status='pending'"):
        import json
        p=json.loads(r['payload'])
        if r['member'] in mids and p.get('start',0)<b and p.get('end',now)>a:requests.append(p)
    reminders=[x for x in timer_reminders(db,selected,user,now) if x['started']<b and now>a]
    overlap=[x for x in improvements.overlaps(selected,now) if x['start']<b and x['end']>a]
    health=improvements.health(db);configured=bool(s.get(db,'config'))
    items=[{'label':'Tracking is configured','ok':configured,'count':0 if configured else 1,'blocking':True},
           {'label':'Trello history is up to date','ok':not health['possiblyIncomplete'],'count':int(health['possiblyIncomplete']),'blocking':True},
           {'label':'Recorded hours are confirmed','ok':not pending,'count':len(pending),'blocking':True},
           {'label':'Correction requests are resolved','ok':not requests,'count':len(requests),'blocking':True},
           {'label':'Long-running timers are reviewed','ok':not reminders,'count':len(reminders),'blocking':True},
           {'label':'Overlapping intervals to review','ok':not overlap,'count':len(overlap),'blocking':False}]
    totals=[];cardmap={c['id']:c for c in cards}
    for student in roster:
        verified=s.weekly_report(db,sessions,cardmap,student['member'],start,end,False,now)['total']
        recorded=s.weekly_report(db,sessions,cardmap,student['member'],start,end,True,now)['total']
        totals.append({'name':student['name'],'member':student['member'],'verified':verified,'recorded':recorded})
    return {'week':data['week'],'timezone':str(s.TZ),'ready':bool(roster) and all(x['ok'] for x in items if x['blocking']),
            'items':items,'students':totals,'unverified':pending,'forgottenTimers':reminders,'health':health}

def safe_cell(value):
    text=str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text

def export_csv(db,user,data,cards,sessions,now):
    import server as s
    if data.get('scope')=='class' and not user['admin']:raise PermissionError('Instructor access required')
    member=data.get('member') if user['admin'] else user['member']
    if data.get('scope')=='class':member=None
    if user['admin'] and data.get('scope')!='class' and not member:raise ValueError('Select a student or choose class export.')
    roster=students(db,user,member);start,end=s.report_week(data['week'])
    mode=data.get('format','detail')
    if mode not in ('detail','summary'):raise ValueError('Choose daily entries or student totals.')
    include=bool(data.get('includePending',False));text=io.StringIO(newline='');writer=csv.writer(text)
    if mode=='summary':writer.writerow(['Student','Username','Week starting','Hours','Time included','Timezone'])
    else:writer.writerow(['Student','Username','Week starting','Work date','Activity','Progress','Hours','Completed on','Timezone'])
    for student in roster:
        report=s.weekly_report(db,sessions,{c['id']:c for c in cards},student['member'],start,end,include,now)
        if mode=='summary':
            writer.writerow([safe_cell(student['name']),safe_cell(student['id']),data['week'],f"{report['total']:.2f}",'Includes unverified time' if include else 'Verified only',str(s.TZ)])
        else:
            for row in report['rows'] or [None]:
                if row is None:
                    writer.writerow([safe_cell(student['name']),safe_cell(student['id']),data['week'],'','','No hours for this week','0.00','',str(s.TZ)]);continue
                completed=('Date not recorded' if row['completedAt'] is None else datetime.fromtimestamp(row['completedAt'],s.TZ).isoformat()) if row['completionStatus']=='completed' else 'Not completed'
                writer.writerow([safe_cell(student['name']),safe_cell(student['id']),data['week'],row['workDate'],safe_cell(row['activity']),safe_cell(row['progress']),f"{row['seconds']/3600:.2f}",completed,str(s.TZ)])
    name='acetime-'+('class' if data.get('scope')=='class' else 'student')+'-'+data['week']+'-'+mode+'.csv'
    return name,('\ufeff'+text.getvalue()).encode('utf-8')

def backup_route(handler,user,data):
    import server as s
    if not user['admin']:handler.send({'error':'Instructor access required'},403);return
    try:
        if handler.path=='/api/backup-now':
            name=backups.snapshot(s.DB,s.DB_LOCK)
            with s.connect() as db:
                import improvements
                improvements.audit(db,user['id'],'database-backup',file=name)
            handler.send({'ok':True,'name':name})
        elif handler.path=='/api/backup-download':
            path=backups.download_path(s.DB,data.get('name'))
            # Hold the snapshot lock until the file is opened, so retention cannot remove it.
            with backups.LOCK:
                with path.open('rb') as f:handler.file_download(f,path.name,'application/vnd.sqlite3')
        else:handler.send(backups.status(s.DB))
    except ValueError as e:handler.send({'error':str(e)},400)
    except Exception:handler.send({'error':'Backup storage is unavailable. Check server storage and retry.'},503)

def route(handler,db,user,data,cards,sessions):
    import server as s
    path=handler.path
    if path not in ('/api/timer-settings','/api/timer-snooze','/api/weekly-checklist','/api/export'):return False
    now=time.time()
    if path=='/api/timer-settings':
        if not user['admin']:handler.send({'error':'Instructor access required'},403);return True
        hours=float(data['hours'])
        if not math.isfinite(hours) or not .5<=hours<=72:raise ValueError('Choose a timer threshold from 0.5 to 72 hours.')
        s.put(db,'timer_settings',{'hours':hours})
        import improvements
        improvements.audit(db,user['id'],'timer-settings',hours=hours)
        handler.send({'ok':True});return True
    if path=='/api/timer-snooze':
        if not user['member']:raise ValueError('Student login required.')
        reminder=next((r for r in timer_reminders(db,sessions,user,now) if r['card']==data.get('card')),None)
        if not reminder:raise ValueError('No reminder for this timer.')
        s.put(db,'timer_snooze:'+reminder['card']+':'+user['member'],{'started':reminder['started'],'until':now+3600})
        handler.send({'ok':True});return True
    if path=='/api/weekly-checklist':handler.send(checklist(db,user,data,cards,sessions,now));return True
    try:name,content=export_csv(db,user,data,cards,sessions,now)
    except PermissionError:handler.send({'error':'Instructor access required'},403);return True
    handler.download(content,name,'text/csv; charset=utf-8');return True
