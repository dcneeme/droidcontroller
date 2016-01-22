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

    def __init__(self, msgbus, mb, name='undefined', in_svc=['TKW', 1, 3], out_ch=[0,1,115], min=0, max=999, period=1000): # period ms
        ''' try to use the input svc members equal using pwm on one output periodic channel. include diff in svc member config! '''
        self.pwm = 0
        self.mb = mb # CommModbus instance
        self.msgbus = msgbus # CommModbus instance
        self.name = name
        self.mbi = out_ch[0] # modbus channel, the same for input and output!
        self.mba = out_ch[1] # slave address for do
        self.reg = out_ch[2] # register for pwm channel
        self.msgbus.subscribe(self.name, in_svc[0], self.name, self.react)
        self.diffmembers = in_svc[1:3]

        # setpoint = 0, P = 1.0, I = 0.01, D = 0.0, min = None, max = None, outmode = 'nolist', name='undefined', dead_time = 0, inv=False):
        self.pid = PID(P=0.3, I=0.1, min=min, max=max) # for pwm control
        log.info('Diff2Pwm instance created') # pwm higher if the first in_svc member is higher than the second

    def react(self,token, subject, message): # listens to TKW svc
        ''' listens to the svc TKW, getting input values to compare '''
        log.info('from msgbus token %s, subject %s, message %s', token, subject, str(message))
        values = message['values']
        invalues = [values[self.diffmembers[0] - 1], values[self.diffmembers[1] - 1]]
        if len(invalues) == 2: # ok
            self.pid.setSetpoint(invalues[0])
            self.pid.set_actual(invalues[1])
            outvalue = int(self.pid.output())
            res = self.output(outvalue)
            return 0
        else:
            log.error('INVALID svc members from '+self.in_svc+': values '+str(values)+', invalues '+str(invalues))
            return 1
            
    def output(self, value):
        fullvalue = int(value + 0x8000 + 0x4000) # phase lock needed for periodic...
        res = self.mb[self.mbi].write(self.mba, self.reg, value=fullvalue) # write to pwm register of it5888
        return res # 0 is ok

    def test(self, invalues = [0, 0]):
        self.pid.setSetpoint(invalues[0]+self.diff)
        self.pid.set_actual(invalues[1])
        value = int(self.pid.output())
        log.info('testing in '+str(invalues)+', pwm '+str(value))
   

