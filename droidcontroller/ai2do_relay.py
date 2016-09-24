# This Python file uses the following encoding: utf-8
#-------------------------------------------------------------------------------
# this is a class to simplify io board it5888 pwm usage. use one instance per one ioboard!
# 2015..2016, neeme

import time, traceback
import logging
log = logging.getLogger(__name__)

class Relay(object):
    ''' Takes an ai value, compares to setpoint and generates do bit value. Based on services in sql channel tables. '''

    def __init__(self, d, ac, mbi=0, mba=1, name='none', set=['C017W',2], act=['C017W',1], out=['D1W',4], inv=False, hyst = 0):
        ''' One instance per output channel  '''
        self.d = d
        self.ac = ac
        self.mbi = mbi # modbus comm instance
        self.mba = mba # modbus address
        self.name = name
        self.set = set # setpoint service member
        self.act = act # actual value service member
        self.out = out # output service member
        self.hyst = hyst # hysteresis
        self.setval = None
        self.actval = None
        self.outval = None
        if inv:
            self.invbit = 1
        else:
            self.invbit = 0
        log.info('Relay instance '+name+' created')

    def readval(self):
        ''' check input '''
        try:
            self.setval = self.ac.get_aivalue(self.set[0], self.set[1])[0] # get_aivalue() returns tuple, lo hi included!
            self.actval = self.ac.get_aivalue(self.act[0], self.act[1])[0]
            self.outval = self.d.get_divalue(self.out[0], self.out[1])
            print('set, act, out', setval, actval, outval) ##
        except:
            log.info('Relay channel '+self.name+ ' readval problem!')
            traceback.print_exc()
            return 2

    def output(self):
        ''' set output '''
        try:
            if self.setval != None and self.actval != None and self.outval != None:
                if self.actval > self.setval + self.hyst:
                    if self.outval == (0 ^ self.invbit):
                        self.d.set_dovalue(self.out[0], self.out[1],(1 ^ self.invbit))
                        log.info('Relay channel '+self.name+' change to '+str(1 ^ self.invbit)+' due to actual '+str(self.actval)+' above setpoint '+str(self.setval)+', hyst '+str(self.hyst))
                elif self.actval < self.setval - self.hyst:
                    if outval == (1 ^ self.invbit):
                        self.d.set_dovalue(self.out[0], self.out[1],(0 ^ self.invbit))
                        log.info('Relay channel '+self.name+' change to '+str(1 ^ self.invbit)+' due to actual '+str(self.actval)+' below setpoint '+str(self.setval)+', hyst '+str(self.hyst))
                return 0
            else:
                log.warning('value None from '+str(self.set)+':'+str(self.setval)+' or '+str(self.act)+':'+str(self.actval)+' or '+str(self.out)+':'+str(self.outval)) # may be ok next time
                return 1
        except:
            log.info('Relay channel '+self.name+ ' output() problem!')
            traceback.print_exc()
            return 2

    def doall(self):
        ''' do all '''
        res += self.readval()
        res += self.output()
        return res