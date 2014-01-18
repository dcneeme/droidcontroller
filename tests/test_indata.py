import time
import unittest

from droidcontroller.indata import InData

class InDataTests(unittest.TestCase):
    def setUp(self):
        self.buf = InData()

    def testReadMissingKey(self):
        self.assertRaises(Exception, lambda: self.buf.read('missingkey'))

    def testWriteAndReadKey(self):
        self.buf.write('testreg', 10)
        val = self.buf.read('testreg')
        self.assertEqual(val['value'], 10)

    def testRewrite(self):
        self.buf.write('testreg1', 11)
        self.buf.write('testreg1', 12)
        val = self.buf.read('testreg1')
        self.assertEqual(val['value'], 12)

    def testTimestamp(self):
        ts = time.time()
        self.buf.write('testreg2', 20)
        val = self.buf.read('testreg2')
        self.assertGreaterEqual(val['timestamp'], ts)
        self.assertLessEqual(val['timestamp'], ts+1)

    def testMultipleBuffers(self):
        buf2 = InData()
        self.buf.write('testreg3', 30)
        buf2.write('testreg3', 33)
        val = self.buf.read('testreg3')
        self.assertEqual(val['value'], 30)
        val = buf2.read('testreg3')
        self.assertEqual(val['value'], 33)

    def testCopy(self):
        buf = InData()
        buf.write('testreg4', 44)
        buf2 = buf.copy()
        buf.write('testreg5', 55)
        self.assertEqual(buf2.read('testreg4')['value'], 44)
        self.assertRaises(Exception, lambda: self.buf2.read('testreg5'))
