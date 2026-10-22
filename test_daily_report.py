import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from engine import summarize,summarize_daily

TZ=ZoneInfo('America/New_York')
def ts(value):return datetime.fromisoformat(value).replace(tzinfo=TZ).timestamp()

class DailyReportTests(unittest.TestCase):
    def setUp(self):
        self.start=ts('2026-10-19T00:00:00');self.end=ts('2026-10-26T00:00:00')
        self.cards={'c':{'name':'Task','idList':'done','completedAt':ts('2026-10-22T15:00:00')}}
    def daily(self,sessions,confirmations=None,verified_only=True,now=None):
        return summarize_daily(sessions,confirmations or {},self.cards,'evan',self.start,self.end,now or self.end,TZ,verified_only)
    def test_48_minutes_and_6_minutes_keep_exact_hours_on_work_dates(self):
        sessions=[{'id':str(minutes),'card':'c','member':'evan','start':ts(day+'T12:00:00'),'end':ts(day+'T12:00:00')+minutes*60} for minutes,day in [(48,'2026-10-20'),(6,'2026-10-21')]]
        rows=self.daily(sessions,{'48':2880,'6':360})
        self.assertEqual([r['workDate'] for r in rows],['2026-10-20','2026-10-21'])
        self.assertEqual([r['seconds']/3600 for r in rows],[0.8,0.1])
        self.assertTrue(all(r['completedAt']==self.cards['c']['completedAt'] for r in rows))
    def test_adjustment_splits_at_midnight_without_changing_week_total(self):
        sessions=[{'id':'s','card':'c','member':'evan','start':ts('2026-10-20T23:30:00'),'end':ts('2026-10-21T01:00:00')}]
        rows=self.daily(sessions,{'s':3600})
        self.assertEqual([r['seconds'] for r in rows],[1200,2400])
        self.assertEqual(sum(r['seconds'] for r in rows),summarize(sessions,{'s':3600},self.cards,'evan',self.start,self.end,self.end)[0]['seconds'])
    def test_multiple_intervals_on_one_day_do_not_count_breaks(self):
        sessions=[{'id':str(i),'card':'c','member':'evan','start':ts('2026-10-20T10:00:00')+i*3600,'end':ts('2026-10-20T10:20:00')+i*3600} for i in range(2)]
        rows=self.daily(sessions,{'0':1200,'1':1200})
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['seconds'],2400)
    def test_active_work_stops_at_now_and_keeps_students_separate(self):
        sessions=[{'id':m,'card':'c','member':m,'start':ts('2026-10-20T23:00:00'),'end':None} for m in ('evan','an','brendan')]
        rows=self.daily(sessions,verified_only=False,now=ts('2026-10-21T00:30:00'))
        self.assertEqual([r['seconds'] for r in rows],[3600,1800]);self.assertTrue(all(not r['verified'] for r in rows))
        self.assertEqual(self.daily(sessions,now=ts('2026-10-21T00:30:00')),[])
    def test_week_boundaries_clip_work_rather_than_completion_date(self):
        sessions=[{'id':'s','card':'c','member':'evan','start':self.start-1800,'end':self.start+1800}]
        rows=self.daily(sessions,{'s':3600})
        self.assertEqual(rows[0]['workDate'],'2026-10-19');self.assertEqual(rows[0]['seconds'],1800)
    def test_daylight_saving_days_have_correct_elapsed_hours(self):
        for date,hours in [('2026-03-08',23),('2026-11-01',25)]:
            start=ts(date+'T00:00:00');end=(datetime.fromtimestamp(start,TZ)+timedelta(days=1)).timestamp()
            sessions=[{'id':'s','card':'c','member':'evan','start':start,'end':end}]
            rows=summarize_daily(sessions,{'s':end-start},self.cards,'evan',start,end,end,TZ)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['workDate'],date);self.assertEqual(rows[0]['seconds']/3600,hours)
    def test_missing_completion_date_is_not_invented(self):
        self.cards['c'].pop('completedAt')
        sessions=[{'id':'s','card':'c','member':'evan','start':self.start,'end':self.start+60}]
        self.assertIsNone(self.daily(sessions,{'s':60})[0]['completedAt'])

if __name__=='__main__':unittest.main()
