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

    def __init__(self, ac, name='none', set=['C02W',2], act=['C02W',1], out=['V1W',1] min=20, max=95, inv=False): # svc - name, member
        ''' One instance per pwm channel. Outpus pwm value to be used with it5888pwm  '''
        self.ac = ac
        self.name = name
        self.set = set # setpoint service member
        self.act = act # actual value service member
        self.out = out # output service member
        self.hyst = hyst # hysteresis
        self.setval = None
        self.actval = None
        self.outval = None
        self.pid = PID(min=min, max=max, name=name, inv=inv, downspeed=1)
        log.info('ai2pid_pwm instance '+name+' created')

    def readval(self):
        ''' check input '''
        try:
            self.ac.make_svc(self.set[0], send=False) # generates values based on raw, does not send (otherwise about 3 min delay in true value!)
            self.ac.make_svc(self.act[0], send=False) # no svc send to monitoring
            self.setval = self.ac.get_aivalue(self.set[0], self.set[1])[0] # get_aivalue() returns tuple, lo hi included!
            self.actval = self.ac.get_aivalue(self.act[0], self.act[1])[0]
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
                return self.pid.output(self.actval, self.setval)
        except:
            log.info(self.name+ ' output() problem!')
            traceback.print_exc()
            return None

      