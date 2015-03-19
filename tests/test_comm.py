import time
import unittest

from droidcontroller.comm import Comm

class CommTests(unittest.TestCase):
    def setUp(self):
        self.comm = Comm()
