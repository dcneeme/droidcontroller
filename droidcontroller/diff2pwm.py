# This Python file uses the following encoding: utf-8

'''  control pwm based on values difference using pid and io it5888 '''

#from codecs import encode # for encode to work in py3
import time
import traceback
#import struct  # struct.unpack for float from hex
from droidcontroller.pid import PID
#from droidcontroller.pid import it5888pwm.py

import sys, logging
log = logging.getLogger(__name__)

class Diff2Pwm(object):
    ''' React on invalues difference using PID, write to pwm register. period register 150 (IT5888).  '''

    def __init__(self, mb, name='undefined', out_ch=[0,1,115], min=0, max=499, period=500, P=1, I=1): # period ms
        ''' try to use the resact() input values pair for pwm on one output periodic channel.  '''
        res = 1 # initially not ok
        self.pwm = 0
        self.mb = mb # CommModbus instance
        self.name = name
        self.mbi = out_ch[0] # modbus channel, the same for input and output!
        self.mba = out_ch[1] # slave address for do
        self.reg = out_ch[2] # register for pwm channel
        self.min = min
        self.max = max
                
        try:
            res = self.mb[self.mbi].write(self.mba, 150, value=period)
        except:
            log.error('FAILED to write period into register 150 at mbi.mba '+str(self.mbi)+'.'+str(self.mba))
            
        # setpoint = 0, P = 1.0, I = 0.01, D = 0.0, min = None, max = None, outmode = 'nolist', name='undefined', dead_time = 0, inv=False):
        self.pid = PID(name=name, P=P, I=I, min=min, max=max, outmode='list') # for fast pwm control
        if res == 0:
            log.info('Diff2Pwm instance created and ready') # pwm higher if the first in_svc member is higher than the second
        else:
            log.error('PROBLEM with Diff2Pwm instance! res '+str(res))
            time.sleep(3)
            
            
    def react(self, invalues, min=None): 
        if min != None:
            if min != self.min:
                self.min = min
                self.pid.setMin(self.min)
                log.info('set new pid min '+str(self.min))
        if len(invalues) == 2: # ok
            self.pid.setSetpoint(invalues[0])
            self.pid.set_actual(invalues[1])
            pidout = self.pid.output()
            pwm = int(pidout[0])
            pidcomp = pidout[1:4]
            if pwm > self.max:
                log.warning('fixing pid output '+str(pwm)+' to max '+str(self.max))
                pwm = self.max
            if pwm < self.min:
                log.warning('fixing pid output '+str(pwm)+' to min '+str(self.min))
                pwm = self.min
            if pwm != self.pwm:
                self.pwm = pwm
                res = self.output(pwm)
                if res == 0:
                    log.info(self.name+' new pwm value '+str(pwm)+' sent, pidcomp '+str(pidcomp))
                else:
                    log.info(self.name+' pwm value unchanged, '+str(pwm)+', pidcomp '+str(pidcomp))
                    
            return self.pwm
            
            
    def output(self, pwm):
        fullvalue = int(pwm + 0x8000 + 0x4000) # phase lock needed for periodic...
        res = self.mb[self.mbi].write(self.mba, self.reg, value=fullvalue) # write to pwm register of it5888
        if res == 0:
            log.info('sent pwm value '+str(pwm)+', fullvalue '+str(fullvalue)+' to '+str(self.mbi)+'.'+str(self.mba)+'.'+str(self.reg))
        else:
            log.error('FAILURE to send pwm fullvalue '+str(fullvalue)+' to '+str(self.mbi)+'.'+str(self.mba)+'.'+str(self.reg))
        return res

    def test(self, invalues = [0, 0]):
        self.pid.setSetpoint(invalues[0]+self.diff)
        self.pid.set_actual(invalues[1])
        value = int(self.pid.output())
        log.info('testing in '+str(invalues)+', pwm '+str(value))
   

