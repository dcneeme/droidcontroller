# This Python file uses the following encoding: utf-8

'''  control pwm based on temp difference '''

#from codecs import encode # for encode to work in py3
import time
import traceback
#import struct  # struct.unpack for float from hex
from droidcontroller.pid import PID
#from droidcontroller.pid import it5888pwm.py

import sys, logging
log = logging.getLogger(__name__)

class Diff2Pwm(object):
    ''' Read or listen from msgbus temperatures, write to pwm register, use PID
    '''

    def __init__(self, mb, mbi=0, mba=1, inreg1=600, inreg2=601, bit=15, diff=30, min=0, max=999, period=1000):
        ''' keep the diff if possible '''
        self.pwm = 0
        self.mb = mb # CommModbus instance
        self.mbi = mbi # modbus channel, the same for input and output!
        self.mba = mba # slave address for do
        self.bit = bit # pwm channel 8...15
        self.diff = diff # setpoint for difference keeping
        self.inreg1 = inreg1

        # d, mbi=0, mba=1, name='IT5888', period=1000, bits=[8], phases=[0], periodics=[], per_reg=150):
        #self.pwm = IT5888pwm(d, mbi=mbi, mba=mba, period = period, bits=[8], phases=[0], periodics=[True])

        # setpoint = 0, P = 1.0, I = 0.01, D = 0.0, min = None, max = None, outmode = 'nolist', name='undefined', dead_time = 0, inv=False):
        self.pid = PID(P=0.1, I=0.01, min=min, max=max) # for pwm control
        log.info('Diff2Pwm instance created')


    def output(self, value):
        fullvalue = int(value + 0x8000 + 0x4000) # phase lock needed for periodic...
        res = self.mb[self.mbi].write(self.mba, 100 + bit, value=fullvalue) # write to pwm register of it5888
        return res # 0 is ok

    def doall(self):
        invalues = self.mb[self.mbi].read(self.mba, self.inreg1, 2)
        self.pid.setSetpoint(invalues[0]+self.diff)
        self.pid.set_actual(invalues[1])
        value = pid.output()
        log.info('in '+srt(invalues)+', pwm '+str(value))
        #res = self.output(value)
        return res # 0 is ok


