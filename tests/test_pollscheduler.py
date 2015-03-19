import time
import unittest

from droidcontroller.pollscheduler import PollScheduler

class PollSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = PollScheduler()

    def testCopy(self):
        newscheduler = self.scheduler.copy()
        self.assertEqual(str(self.scheduler), str(newscheduler))
