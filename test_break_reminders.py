import unittest
from engine import break_reminder
class BreakReminderTests(unittest.TestCase):
    def s(self,start,end=None,member='alice',id='s'):
        return {'id':id,'card':'card','member':member,'start':start,'end':end}
    def test_warns_fifteen_minutes_before_four_hours(self):
        r=break_reminder([self.s(0)],'alice',13500)
        self.assertEqual(r['status'],'soon');self.assertTrue(r['notify']);self.assertEqual(r['remainingSeconds'],900)
        self.assertFalse(break_reminder([self.s(0)],'alice',13499)['notify'])
    def test_due_exactly_at_threshold(self):
        self.assertEqual(break_reminder([self.s(0)],'alice',14400)['status'],'due')
    def test_concurrent_cards_do_not_double_count(self):
        r=break_reminder([self.s(0),self.s(3600,id='second')],'alice',7200)
        self.assertEqual(r['elapsedSeconds'],7200);self.assertFalse(r['notify'])
    def test_all_paused_has_no_reminder_and_resume_resets_clock(self):
        s=[self.s(0,14500)]
        self.assertEqual(break_reminder(s,'alice',15000)['status'],'idle')
        s.append(self.s(15100))
        self.assertEqual(break_reminder(s,'alice',15200)['elapsedSeconds'],100)
    def test_one_paused_card_does_not_reset_other_working_card(self):
        s=[self.s(0,10000),self.s(5000)]
        r=break_reminder(s,'alice',14500)
        self.assertEqual(r['status'],'due');self.assertEqual(r['streakStart'],0)
    def test_students_have_independent_break_clocks(self):
        s=[self.s(0),self.s(14000,member='bob')]
        self.assertTrue(break_reminder(s,'alice',14500)['notify'])
        self.assertFalse(break_reminder(s,'bob',14500)['notify'])
    def test_individual_threshold(self):
        r=break_reminder([self.s(0)],'alice',7200,threshold_hours=2)
        self.assertEqual(r['status'],'due');self.assertEqual(r['thresholdHours'],2)
    def test_snooze_is_streak_specific_and_expires(self):
        s=[self.s(0)];snooze={'streakStart':0,'until':15000}
        self.assertFalse(break_reminder(s,'alice',14500,snooze=snooze)['notify'])
        self.assertTrue(break_reminder(s,'alice',15000,snooze=snooze)['notify'])
        stale={'streakStart':-100,'until':20000}
        self.assertTrue(break_reminder(s,'alice',14500,snooze=stale)['notify'])
    def test_touching_intervals_are_continuous(self):
        r=break_reminder([self.s(0,7200),self.s(7200)],'alice',14400)
        self.assertEqual(r['elapsedSeconds'],14400)
    def test_warning_window_scales_for_short_thresholds(self):
        r=break_reminder([self.s(0)],'alice',700,threshold_hours=.25)
        self.assertEqual(r['status'],'soon');self.assertEqual(r['leadMinutes'],3.75)
if __name__=='__main__':unittest.main()
