import time
import unittest

from droidcontroller.convert_ds18b20 import ConvertDS18B20

class ConvertDS18B20Tests(unittest.TestCase):
    def setUp(self):
        self.conv = ConvertDS18B20()

    def testMissingData(self):
        outdata = self.conv.convert("test", [ 0b0001000000000000 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "N/A")

    def testError(self):
        # +85deg is usually error condition
        outdata = self.conv.convert("test", [ 0b0000010101010000 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "ERR")

    def testTemps(self):
        # Test values from DS18B20 datasheet
        outdata = self.conv.convert("test", [ 0b0000011111010000 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "125.0")
        # outdata = self.conv.convert("test", [ 0b0000010101010000 ])
        # self.assertEqual(len(outdata), 1)
        # self.assertEqual(outdata[0], "85.0")
        outdata = self.conv.convert("test", [ 0b0000000110010001 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "25.1")
        outdata = self.conv.convert("test", [ 0b0000000010100010 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "10.1")
        outdata = self.conv.convert("test", [ 0b0000000000001000 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "0.5")
        outdata = self.conv.convert("test", [ 0b0000000000000000 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "0.0")
        outdata = self.conv.convert("test", [ 0b1111111111111000 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "-0.5")
        outdata = self.conv.convert("test", [ 0b1111111101011110 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "-10.1")
        outdata = self.conv.convert("test", [ 0b1111111001101111 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "-25.1")
        outdata = self.conv.convert("test", [ 0b1111110010010000 ])
        self.assertEqual(len(outdata), 1)
        self.assertEqual(outdata[0], "-55.0")

