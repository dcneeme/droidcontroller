''' average stream of values without sliding window 

usage:
$ python
Python 2.7.4 (default, Apr  6 2013, 19:54:46) [MSC v.1500 32 bit (Intel)] on win32
Type "help", "copyright", "credits" or "license" for more information.
>>> from avg import AVG
>>> avg=AVG() # algvaartusteks vaikimisi 50 ja 500
>>> avg.output(0) # vigane crc
4500
>>> avg.output(1000) # korras crc
5050
>>> avg.output(1000) # korras crc
5545
'''

import time
import logging
log = logging.getLogger(__name__)  
#log.addHandler(logging.NullHandler())

class AVG():
    def __init__(self, avg_coeff=50, avg_value=500, int=False):
        ''' if int === True then simulates pic calculations (with no decimal point) '''
        self.avg_value = avg_value # initial value
        self.avg_coeff = avg_coeff
        if int:
            self.div_coeff = 1
        else:
            self.div_coeff = 1.0
        
    def output(self, invalue):
        ''' calculate new avg_value '''
        self.avg_value = ((self.avg_coeff - 1) * self.avg_value + invalue) / self.avg_coeff * self.div_coeff
        return self.avg_value
        
    def test(self, invalue):
        ''' find the averaging limit depending on invalue '''
        for i in range(100):
            print(str(self.output(invalue)))
            time.sleep(0.05)
            