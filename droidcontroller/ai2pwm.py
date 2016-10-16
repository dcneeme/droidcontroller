# jama!

# This Python file uses the following encoding: utf-8
#-------------------------------------------------------------------------------
# this is a class to switch it5888 do channels according to actual and setpoint ai values, defined by services
#  neeme okt 2016

import time, traceback
import logging
from droidcontroller.pid import PID
log = logging.getLogger(__name__)

class AI2pwm(object):
    ''' Takes an ai value, compares to setpoint and generates do bit value. Based on services in sql channel tables. '''

    def __init__(self, ac, name='none', set=['C004W',2], act=(['C004W',2], ['C004W',3]), out=['AV0W',1], min=20, max=95, inv=False, bias=0xc000, deadband=1): # svc - name, member. 
        ''' One instance per pwm channel. Generate pwm value to be used with it5888pwm. Based on services, no mbi mba regadd knowledge needed.
            in order to modify the pid parameters, use set...  methods in PID class. Parameter bias is for it5888pwm periodics and phase control.
            If more than one act is given (tuple), then the bigger value is used. 
        '''
        self.ac = ac
        self.name = name
        self.set = set # setpoint service member
        self.act = act # actual value service member
        self.out = out # output service member
        self.deadband = deadband # hysteresis
        self.setval = None
        self.actval = None
        self.outval = None
        self.pid = PID(min=min, max=max, name=name, inv=inv, downspeed=1)
        log.info('ai2pid_pwm instance '+name+' created')

    def readval(self):
        ''' check input '''
        try:
            self.ac.make_svc(self.set[0], send=False) # generates values based on raw, does not send (otherwise about 3 min delay in true value!)
            self.setval = self.ac.get_aivalue(self.set[0], self.set[1])[0] # get_aivalue() returns tuple, lo hi included!
            if 'list' in str(type(self.act)):  # one act channel
                self.ac.make_svc(self.act[0], send=False) # no svc send to monitoring
                self.actval = self.ac.get_aivalue(self.act[0], self.act[1])[0]
            elif 'tuple' in str(type(self.act)):  # more than one act, select the one with biggest abs value
                actval = 0; self.actval = 0
                for i in range(len(self.act)):
                    self.ac.make_svc(self.act[0][0], send=False) # no svc send to monitoring
                    actval = self.ac.get_aivalue(self.act[0], self.act[i][1])[0]
                    if abs(actval) > abs(self.actval):
                        self.actval = actval
                log.info(self.name+' selected self.actval '+str(self.actval)) ##
            else:
                log.error(self.name+' act invalid type')
                return 2
                
            self.outval = self.d.get_divalue(self.out[0], self.out[1]) # current value without bias
            log.info(self.name+' readval got setval, actval '+str(self.setval)+', '+str(self.actval)+', set '+str(self.set)+', act'+', '+str(self.act)) ##
            return 0
        except:
            log.error(self.name+ ' readval problem!')
            traceback.print_exc()
            return 2

    def output(self):
        ''' return output '''
        try:
            if self.setval != None and self.actval != None and self.outval != None:
                output = self.pid.output(self.actval, self.setval)
                if output > self.outval + self.deadband or output < self.outval + self.deadband:
                    log.info(self.name+' new pwm value '+str(output))
                    self.ac.set_aosvc(self.out[0], self.out[1], output, raw = True) # svc, member, value, raw
                    
        except:
            log.info(self.name+ ' output() problem!')
            traceback.print_exc()
            return None

    def doall(self):
        ''' do everythng to compare actual with setpoint and change the pwm value '''
        res1 = self.readval()
        res2 = self.output()
        if res1 == 0 and res2 == 0:
            return 0
        else:
            return 1

      