# This Python file uses the following encoding: utf-8
#-------------------------------------------------------------------------------
# this is a class to simplify io board it5888 pwm usage. use one instance per one ioboard!
# 2015..2016, neeme

import time, traceback
import logging
log = logging.getLogger(__name__)

class Relay(object):
    ''' Takes an ai value, compares to setpoint and generates do bit value. Based on services in sql channel tables. '''

    def __init__(self, d, ac, mbi=0, mba=1, name='none', set=['TCW',1], act=['TCW',2], out=['D1S',8], inv=False, hyst = 0):
        ''' One instance per output channel  '''
        self.d = d
        self.ac = ac
        self.mbi = mbi # modbus comm instance
        self.mba = mba # modbus address
        self.name = name
        self.set = set # setpoint service member
        self.act = act # actual value service member
        self.hyst = hyst # hysteresis
        self.out = None # initially
        if inv == True:
            invbit = 1
        else:
            invbit = 0
        log.info('Relay instance '+name+' created')
        
    def output(self):
        ''' check input and set output '''
        try:
            setval = self.ac.get_aivalue(set[0], set[1])
            actval = self.ac.get_aivalue(act[0], act[1])
            outval = self.d.get_divalue(out[0], out[1])
            
            if actval > setval + hyst:
                if outval == (0 ^ invbit):
                    self.d.set_dovalue(out[0],out[1],(1 ^ invbit)
                    log.info('Relay channel '+self.name+' change to '+str(1 ^ invbit)+' due to actual '+str(actval)+' above setpoint '+str(setval)+', hyst '+str(self.hyst))
            elif actval < setval - hyst:
                if outval == (1 ^ invbit):
                    self.d.set_dovalue(out[0],out[1],(0 ^ invbit)
                    log.info('Relay channel '+self.name+' change to '+str(1 ^ invbit)+' due to actual '+str(actval)+' below setpoint '+str(setval)+', hyst '+str(self.hyst))
            return 0
            
        except:
            log.info('Relay channel '+self.name+ ' problem!')
            traceback.print_exc()
            return 1
        