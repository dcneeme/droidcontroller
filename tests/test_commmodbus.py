import time
import unittest

from droidcontroller.comm_modbus import CommModbus

class CommModbusTests(unittest.TestCase):
    def setUp(self):
        self.comm = CommModbus()

