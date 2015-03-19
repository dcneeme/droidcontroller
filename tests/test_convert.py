import time
import unittest

from droidcontroller.convert import Convert

class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.conv = Convert()

    def testDummyConverter(self):
        indata = 1234
        outdata = self.conv.convert("test", indata)
        self.assertEqual(indata, outdata)
