import unittest
from engine import replay,summarize
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
L={'active':'working','blocked':'paused','done':'done','backlog':'todo'}
def event(id,t,kind='updateCard',**data):
    return {'id':id,'date':datetime.fromtimestamp(t,timezone.utc).isoformat(),'type':kind,'data':dict(card={'id':'c','name':'Task'},**data)}
def move(id,t,before,after):return event(id,t,old={'idList':before},listAfter={'id':after})
class TimingTests(unittest.TestCase):
    def setUp(self):self.b={'started':100,'cards':[{'id':'c','name':'Task','idMembers':['a','b'],'idList':'todo'}]}
    def test_group_pause_resume_and_complete(self):
        cards,s=replay(self.b,[move('1',200,'todo','working'),move('2',3800,'working','paused'),move('3',7400,'paused','working'),move('4',9200,'working','done')],L,10000)
        for m in ['a','b']:self.assertEqual(sum(x['end']-x['start'] for x in s if x['member']==m),5400)
        self.assertEqual(cards[0]['idList'],'done')
    def test_out_of_order_replays_identically(self):
        ev=[move('1',200,'todo','working'),move('2',300,'working','done')]
        self.assertEqual(replay(self.b,ev,L,400),replay(self.b,list(reversed(ev)),L,400))
    def test_completed_newest_first_without_working_sessions(self):
        self.b['cards']=[{'id':cid,'name':cid,'idMembers':[],'idList':'todo'} for cid in ('old','new','middle')]
        events=[]
        for cid,t in [('old',200),('new',400),('middle',300)]:
            e=move(cid,t,'todo','done');e['data']['card']['id']=cid;events.append(e)
        cards,sessions=replay(self.b,events,L,500)
        self.assertEqual([c['id'] for c in cards],['new','middle','old'])
        self.assertEqual([c['completedAt'] for c in cards],[400,300,200])
        self.assertEqual(sessions,[])
        self.assertEqual(replay(self.b,list(reversed(events)),L,500)[0],cards)
    def test_recompletion_uses_latest_entry_not_creation_order(self):
        self.b['cards'].append({'id':'other','name':'Other','idMembers':[],'idList':'todo'})
        other=move('other',300,'todo','done');other['data']['card']['id']='other'
        events=[move('first',200,'todo','done'),other,move('reopen',400,'done','paused'),move('again',500,'paused','done')]
        cards,_=replay(self.b,events,L,600)
        self.assertEqual([c['id'] for c in cards],['c','other'])
        self.assertEqual(cards[0]['completedAt'],500)
    def test_completed_metadata_changes_do_not_change_completion_time(self):
        cards,_=replay(self.b,[move('complete',200,'todo','done'),event('member',300,'addMemberToCard',idMember='new'),event('rename',400,old={'name':'Old name'})],L,500)
        self.assertEqual(cards[0]['completedAt'],200)
        cards,_=replay(self.b,[move('complete',200,'todo','done'),move('reopen',300,'done','working')],L,400)
        self.assertIsNone(cards[0]['completedAt'])
    def test_unknown_baseline_dates_and_other_columns_stay_stable(self):
        self.b['cards']=[{'id':cid,'name':cid,'idMembers':[],'idList':status} for cid,status in [('first','done'),('todo1','todo'),('second','done'),('todo2','todo'),('todo3','todo')]]
        e=move('new',200,'todo','done');e['data']['card']['id']='todo2'
        cards,_=replay(self.b,[e],L,300)
        self.assertEqual([c['id'] for c in cards if c['idList']=='done'],['todo2','first','second'])
        self.assertEqual([c['id'] for c in cards if c['idList']=='todo'],['todo1','todo3'])
        self.assertIsNone(next(c for c in cards if c['id']=='first')['completedAt'])
        self.assertTrue(all('completedAt' not in c for c in self.b['cards']))
    def test_assignment_splits_attribution(self):
        ev=[move('1',200,'todo','working'),event('2',300,'removeMemberFromCard',idMember='a'),move('3',400,'working','done')]
        _,s=replay(self.b,ev,L,500)
        self.assertEqual(sum(x['end']-x['start'] for x in s if x['member']=='a'),100)
        self.assertEqual(sum(x['end']-x['start'] for x in s if x['member']=='b'),200)
    def test_backlog_stops_running_and_unassigned_does_not_run(self):
        _,s=replay(self.b,[move('1',200,'todo','working'),move('2',300,'working','todo')],L,1000)
        self.assertTrue(all(x['end']==300 for x in s));self.b['cards'][0]['idMembers']=[]
        self.assertEqual(replay(self.b,[move('1',200,'todo','working')],L,400)[1],[])
    def test_reopening_keeps_confirmed_sessions_separate(self):
        ev=[move('1',200,'todo','working'),move('2',300,'working','done')]
        _,old=replay(self.b,ev,L,400)
        _,new=replay(self.b,ev+[move('3',500,'done','working'),move('4',600,'working','done')],L,700)
        self.assertEqual(new[:2],old);self.assertEqual(len(new),4)
    def test_late_event_invalidates_changed_confirmation(self):
        ev=[move('1',200,'todo','working'),move('3',400,'working','done')]
        _,s=replay(self.b,ev,L,500);_,late=replay(self.b,ev+[move('2',300,'working','paused')],L,500)
        self.assertNotEqual(s[0]['id'],late[0]['id'])
    def test_week_clip_and_proportional_verified_time(self):
        s=[{'id':'s','card':'c','member':'a','start':100,'end':300}]
        rows=summarize(s,{'s':100},{'c':{'name':'Task'}},'a',200,400,500)
        self.assertEqual(rows[0]['seconds'],50)
        self.assertEqual(summarize(s,{}, {},'a',200,400,500),[])
    def test_dst_calendar_week(self):
        from datetime import timedelta
        start=datetime(2026,10,26,tzinfo=ZoneInfo('America/New_York'));end=start+timedelta(days=7)
        self.assertEqual(end.timestamp()-start.timestamp(),169*3600)
    def test_baseline_working_starts_at_activation(self):
        self.b['cards'][0]['idList']='working';_,s=replay(self.b,[],L,300)
        self.assertEqual(s[0]['start'],100);self.assertIsNone(s[0]['end'])
if __name__=='__main__':unittest.main()
