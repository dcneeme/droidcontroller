# This Python file uses the following encoding: utf-8

'''  control pwm based on values difference using pid and io it5888 '''

#from codecs import encode # for encode to work in py3
import time
import traceback
#import struct  # struct.unpack for float from hex
from droidcontroller.pid import PID
from droidcontroller.statekeeper import StateKeeper # state


import sys, logging
log = logging.getLogger(__name__)

class Diff2Pwm(object):
    ''' React on invalues difference using PID, write to pwm register. period register 150 (IT5888).  '''

    def __init__(self, mb, name='undefined', out_ch=[0,1,115], outMin=0, outMax=499, period=500, P=1, I=1, D=0, upspeed=None, dnspeed=None): # period ms
        ''' try to use the resact() input values pair for pwm on one output periodic channel.  '''
        res = 1 # initially not ok
        self.pwm = None
        self.mb = mb # CommModbus instance
        self.name = name
        self.state = StateKeeper()
        self.upspeed = upspeed
        self.dnspeed = dnspeed
        self.mbi = out_ch[0] # modbus channel, the same for input and output!
        self.mba = out_ch[1] # slave address for do
        self.reg = out_ch[2] # register for pwm channel
        self.outMin = outMin
        self.outMax = outMax
                
        try:
            res = self.mb[self.mbi].write(self.mba, 150, value=period)
        except:
            log.error('FAILED to write period into register 150 at mbi.mba '+str(self.mbi)+'.'+str(self.mba))
            
        # setpoint = 0, P = 1.0, I = 0.01, D = 0.0, min = None, max = None, outmode = 'nolist', name='undefined', dead_time = 0, inv=False):
        self.pid = PID(name=name, P=P, I=I, D=D, min=self.outMin, max=self.outMax, outmode='list') # for fast pwm control. D mainly for change speed!
            
            
    def react(self, invalues, outMin=None): 
        if outMin != None:
            if outMin != self.outMin:
                self.outMin = outMin
                self.pid.setMin(self.outMin)
                log.info(self.name+' new min '+str(self.outMin))
        if self.outMin != None and ('float' in str(type(self.outMin)) or 'int' in str(type(self.outMin))):
            pass
        else:
            log.error('INVALID self.outMin in '+self.name+' react(): '+str(self.outMin))
        if self.outMax != None and ('float' in str(type(self.outMax)) or 'int' in str(type(self.outMax))):
            pass
        else:
            log.error('INVALID self.outMax in '+self.name+' react(): '+str(self.outMax))
            
        if len(invalues) == 2: # ok
            if self.outMin > 0 or (invalues[0] > invalues[1]):
                self.state.up() # igal juhul lubatud
            self.pid.setSetpoint(invalues[0])
            self.pid.set_actual(invalues[1])
            pidout = self.pid.output()
            pwm = int(pidout[0])
            pidcomp = pidout[1:4]
            chgspeed = pidcomp[2] # p, i, d
            if self.upspeed != None and self.upspeed > 0:
                if chgspeed > self.upspeed: # error decreasing fast
                    self.state.up()
                    pwm = self.outMax # used for kitchen ventilation
                    log.warning('fast change up, state up, max pwm '+str(pwm)+', chgspeed '+str(chgspeed)+', upspeed '+str(self.upspeed))
            if self.dnspeed != None and self.dnspeed < 0:
                if chgspeed < self.dnspeed and self.outMin == 0:
                    self.state.dn()
                    log.warning('fast change down, state dn, chgspeed '+str(chgspeed)+', dnspeed '+str(self.dnspeed))
            if pwm > self.outMax:
                log.warning('fixing pid output '+str(pwm)+' to max '+str(self.outMax))
                pwm = self.outMax
            if pwm < self.outMin:
                log.warning('fixing pid output '+str(pwm)+' to min '+str(self.outMin))
                pwm = self.outMin
            if pwm != self.pwm:
                self.pwm = pwm
            if pwm == 0:
                self.state.dn()
                
            
            statetuple = self.state.get_state()
            if statetuple[0] != 1: # not ON
                pwm = 0 
            res = self.output(pwm)
            if pwm != self.pwm:
                self.pwm = pwm
                log.info(self.name+' new pwm value '+str(pwm)+' sent, pidcomp '+str(pidcomp))
            return self.pwm, [pidcomp], statetuple[0] # pidcom is list
            
            
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
   

