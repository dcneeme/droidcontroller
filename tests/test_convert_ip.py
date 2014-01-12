import time
import unittest

from droidcontroller.convert_ip import ConvertIP

class ConvertIPTests(unittest.TestCase):
    def setUp(self):
        self.conv = ConvertIP()

    def testConvertIP(self):
        indata = [ (127 << 8) + 0, (0 << 8) + 1 ]
        outdata = self.conv.convert("test", indata)
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "127.0.0.1")
