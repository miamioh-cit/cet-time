"""Deterministic, replayable Trello timing; no network or database dependencies."""
from datetime import datetime

def stamp(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()

def replay(baseline, events, lists, now):
    cards = {c['id']: dict(c, idMembers=list(c.get('idMembers', []))) for c in baseline['cards']}
    running, sessions = {}, []
    start = baseline['started']
    def enter(c, t, event):
        if c.get('idList') == lists['active'] and not c.get('closed'):
            for m in c.get('idMembers', []):
                running[(c['id'], m)] = (t, event)
    def stop(c, t):
        for k in list(running):
            if k[0] == c['id']:
                begin, eid = running.pop(k)
                if t > begin:
                    sessions.append(dict(id=f'{eid}:{k[0]}:{k[1]}:{t}', card=k[0], member=k[1], start=begin, end=t))
    for c in cards.values(): enter(c, start, 'baseline')
    for e in sorted(events, key=lambda x: (stamp(x['date']), x['id'])):
        t = stamp(e['date'])
        if t < start: continue
        d, typ = e.get('data', {}), e['type']
        cid = d.get('card', {}).get('id')
        if not cid: continue
        c = cards.setdefault(cid, dict(id=cid, name=d['card'].get('name', 'Task'), idMembers=[], idList=None, closed=False))
        # Every state-affecting change splits sessions so attribution is stable.
        if typ in ('createCard', 'copyCard', 'moveCardToBoard'):
            stop(c,t)
            c.update(idList=d.get('list',{}).get('id'), closed=False)
        elif typ == 'updateCard' and ('idList' in d.get('old',{}) or 'closed' in d.get('old',{})):
            stop(c,t)
            if 'idList' in d.get('old',{}): c['idList']=d.get('listAfter',{}).get('id',d['card'].get('idList'))
            if 'closed' in d.get('old',{}): c['closed']=d['card'].get('closed',False)
        elif typ in ('addMemberToCard','removeMemberFromCard'):
            stop(c,t)
            m=d.get('idMember') or d.get('member',{}).get('id') or e.get('member',{}).get('id')
            if m and typ=='addMemberToCard' and m not in c['idMembers']: c['idMembers'].append(m)
            if m and typ=='removeMemberFromCard': c['idMembers']=[x for x in c['idMembers'] if x!=m]
        elif typ in ('deleteCard','moveCardFromBoard'):
            stop(c,t); c['closed']=True
        else:
            if d.get('card',{}).get('name'): c['name']=d['card']['name']
            continue
        if d.get('card',{}).get('name'): c['name']=d['card']['name']
        enter(c,t,e['id'])
    for (cid,m), (begin,eid) in running.items():
        sessions.append(dict(id=f'{eid}:{cid}:{m}',card=cid,member=m,start=begin,end=None))
    return list(cards.values()), sessions

def summarize(sessions, confirmations, cards, member, start, end, now, verified_only=True):
    grouped={}
    for s in sessions:
        if s['member'] != member: continue
        finish=s['end'] if s['end'] is not None else now
        overlap=max(0,min(finish,end)-max(s['start'],start))
        if not overlap: continue
        approved=confirmations.get(s['id'])
        if verified_only and approved is None: continue
        seconds=overlap if approved is None else overlap*approved/max(1,finish-s['start'])
        c=cards.get(s['card'],{})
        g=grouped.setdefault(s['card'],{'activity':c.get('name','Task'),'seconds':0,'verified':True,'list':c.get('idList')})
        g['seconds']+=seconds; g['verified'] &= approved is not None
    return list(grouped.values())


def break_reminder(sessions, member, now, threshold_hours=4, snooze=None):
    """Union a student's working intervals; only the currently active streak counts."""
    intervals=[]
    for s in sessions:
        if s['member'] != member or s['start'] > now:
            continue
        end=now if s['end'] is None else min(s['end'],now)
        if end >= s['start']:
            intervals.append((s['start'],end,s['end'] is None))
    merged=[]
    for start,end,active in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1]=max(merged[-1][1],end)
            merged[-1][2] |= active
        else:
            merged.append([start,end,active])
    current=next((x for x in reversed(merged) if x[2]),None)
    threshold=float(threshold_hours)*3600
    lead=min(15*60,threshold/4)
    start=current[0] if current else None
    elapsed=max(0,now-start) if current else 0
    status='due' if current and elapsed >= threshold else 'soon' if current and elapsed >= threshold-lead else 'working' if current else 'idle'
    snoozed=bool(current and snooze and snooze.get('streakStart')==start and snooze.get('until',0)>now)
    return {'member':member,'streakStart':start,'elapsedSeconds':elapsed,'thresholdHours':float(threshold_hours),'leadMinutes':lead/60,'remainingSeconds':max(0,threshold-elapsed),'status':status,'snoozed':snoozed,'snoozedUntil':snooze.get('until') if snoozed else None,'notify':status in ('soon','due') and not snoozed}
