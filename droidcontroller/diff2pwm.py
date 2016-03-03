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
    ''' React on invalues difference using PID, write to pwm register. period register 150 (IT5888).
    Oriented on kitchen ventilation. Boosts on switch on for a while. '''

    def __init__(self, mb, name='undefined', out_ch=[0,1,115], outMin=0, outMax=499, period=500, P=1, I=1, D=0, upspeed=None, dnspeed=None): # period ms
        ''' try to use the resact() input values pair for pwm on one output periodic channel.  '''
        res = 1 # initially not ok
        self.pwm = None
        self.mb = mb # CommModbus instance
        self.name = name
        self.state = StateKeeper(name='vent_state')
        self.upspeed = upspeed
        self.dnspeed = dnspeed
        self.mbi = out_ch[0] # modbus channel, the same for input and output!
        self.mba = out_ch[1] # slave address for do
        self.reg = out_ch[2] # register for pwm channel
        self.outMin = outMin
        self.outMax = outMax
        self.ts_react = 0
        self.boost_time = 10 # s
        self.fullvalue = 0
        
        try:
            res = self.mb[self.mbi].write(self.mba, 150, value=period)
        except:
            log.error('FAILED to write period into register 150 at mbi.mba '+str(self.mbi)+'.'+str(self.mba))

        # setpoint = 0, P = 1.0, I = 0.01, D = 0.0, min = None, max = None, outmode = 'nolist', name='undefined', dead_time = 0, inv=False):
        self.pid = PID(name=name, P=P, I=I, D=D, min=self.outMin, max=self.outMax, outmode='list') # for fast pwm control. D mainly for change speed!


    def react(self, invalues, outMin=None, delay=5):
        ''' no need to react too often ... keep 5 s delay. returns self.pwm, [pidcomp], state '''
        ts = time.time()
        if ts < self.ts_react + 5:
            return None # not this time...

        self.ts_react = ts
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

        if len(invalues) == 2: # setpoint, actual. add ventilation if setpoint below actual
            #if self.outMin > 0 or (invalues[0] > invalues[1]):
            if self.outMin > 0 and (invalues[0] > invalues[1]): # avoid restart
                self.state.up() # igal juhul lubatud
            self.pid.setSetpoint(invalues[0])
            self.pid.set_actual(invalues[1])
            pidout = self.pid.output()
            statetuple = self.state.get_state()
            
            if pidout[0] != None:
                pwm = int(pidout[0]) ## pwm value from pid
                pidcomp = pidout[1:4]
                chgspeed = pidcomp[2] # p, i, d
                if self.upspeed != None and statetuple[0] == 0: # not yet started but could perhaps
                    #if (chgspeed > self.upspeed and self.outMin > 0): # error decreasing fast
                    #if (chgspeed > self.upspeed and pwm > self.outMin): # lylitame varem sisse kiire temp tousu korral
                    if chgspeed > self.upspeed: # lylitame sisse kiire temp tousu korral
                        self.state.up()
                        pwm = self.outMax # used for kitchen ventilation
                        log.warning(self.name+' state up due to speed, pwm '+str(pwm)+', chgspeed '+str(chgspeed)+', upspeed '+str(self.upspeed))
                
                if self.dnspeed != None and statetuple[0] == 1:
                    #if chgspeed < self.dnspeed and self.outMin == 0:
                    if chgspeed < self.dnspeed and self.outMin < 250:
                        self.state.dn()
                        log.warning(self.name+' state down due to speed, pwm '+str(pwm)+', chgspeed '+str(chgspeed)+', dnspeed '+str(self.dnspeed))
                
                if pwm > self.outMax:
                    log.warning('fixing pid output for pwm '+str(pwm)+' to max '+str(self.outMax))
                    pwm = self.outMax
                if pwm < self.outMin:
                    log.warning('fixing pid output for pwm '+str(pwm)+' to min '+str(self.outMin))
                    pwm = self.outMin
                
                if pwm == 0:
                    self.state.dn()
                    log.warning(self.name+' state down due to pwm value '+str(pwm))


                statetuple = self.state.get_state() # once again

                if statetuple[0] == 1 and statetuple[1] < self.boost_time: # on for less than
                    pwm = self.outMax
                    log.warning('pwm temporarely boosted to '+str(self.outMax)+' due to state just turned ON')

                if statetuple[0] == 0: # state off
                    pwm = 0

                res = self.output(pwm) # send to output
            else:
                pwm = None # due to pid output None 
                
            if pwm != self.pwm:
                log.info(self.name+' new pwm value '+str(pwm)+' replacing the old '+str(self.pwm))
                self.pwm = pwm
                
            
            if self.pwm != None:
                return self.pwm, [pidcomp], statetuple[0] # pidcom is list
            else:
                log.warning('pwm None due to some reason. invalues '+str(invalues)+', pidout '+str(pidout))
                return None
                

    def output(self, pwm):
        fullvalue = int(pwm + 0x8000 + 0x4000) # phase lock needed for periodic...
        if fullvalue != self.fullvalue:
            res = self.mb[self.mbi].write(self.mba, self.reg, value=fullvalue) # write to pwm register of it5888
            if res == 0:
                log.info('sent pwm value '+str(pwm)+', fullvalue '+str(fullvalue)+' to '+str(self.mbi)+'.'+str(self.mba)+'.'+str(self.reg))
                self.fullvalue = fullvalue
            else:
                log.error('FAILURE to send pwm fullvalue '+str(fullvalue)+' to '+str(self.mbi)+'.'+str(self.mba)+'.'+str(self.reg))
            return res
        else: # no change needed to be sent (assuming there was no power break, regular testing?)
            return 0

    def test(self, invalues = [0, 0]):
        self.pid.setSetpoint(invalues[0]+self.diff)
        self.pid.set_actual(invalues[1])
        value = int(self.pid.output())
        log.info('testing in '+str(invalues)+', pwm '+str(value))


