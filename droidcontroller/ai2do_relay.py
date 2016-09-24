# This Python file uses the following encoding: utf-8
#-------------------------------------------------------------------------------
# this is a class to switch it5888 do channels according to actual and setpoint ai values, defined by services
#  neeme sep 2016

import time, traceback
import logging
log = logging.getLogger(__name__)

class Relay(object):
    ''' Takes an ai value, compares to setpoint and generates do bit value. Based on services in sql channel tables. '''

    def __init__(self, d, ac, name='none', set=['C017W',2], act=['C017W',1], out=['D1W',4], inv=False, hyst = 0):
        ''' One instance per output channel  '''
        self.d = d
        self.ac = ac
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
            self.ac.make_svc(self.set[0], send=False) # generates values based on raw, otherwise about 3 min delay in true value!
            self.ac.make_svc(self.act[0], send=False) # no svc send to monitoring
            self.setval = self.ac.get_aivalue(self.set[0], self.set[1])[0] # get_aivalue() returns tuple, lo hi included!
            self.actval = self.ac.get_aivalue(self.act[0], self.act[1])[0]
            self.outval = self.d.get_divalue(self.out[0], self.out[1])
            if self.actval == None:
                log.error('ai2do_relay readval got setval, actval, outval '+str(self.setval)+', '+self.actval+', '+self.outval+', set '+self.set+', act'+', '+self.act) ##
                return 1
            else:
                return 0
        except:
            log.info('relay channel '+self.name+ ' readval problem!')
            traceback.print_exc()
            return 2

    def output(self):
        ''' set output '''
        try:
            if self.setval != None and self.actval != None and self.outval != None:
                if self.actval > self.setval + self.hyst:
                    outval = (0 ^ self.invbit)
                    if outval != self.outval:
                        self.d.set_dovalue(self.out[0], self.out[1], outval)
                        self.outval = outval
                        log.info('Relay channel '+self.name+' change from '+str(self.outval)+' to '+str(outval)+' due to actual '+str(self.actval)+' above setpoint '+str(self.setval)+', hyst '+str(self.hyst)+', inv '+str(self.invbit))
                    #else: ##
                    #    log.info('outval while act hi already '+str(self.outval)+' as calculated new value '+str(outval)) ##
                elif self.actval < self.setval - self.hyst:
                    outval = (1 ^ self.invbit)
                    if outval != self.outval:
                        self.d.set_dovalue(self.out[0], self.out[1], outval)
                        self.outval = outval
                        log.info('Relay channel '+self.name+' change from '+str(self.outval)+' to '+str(outval)+' due to actual '+str(self.actval)+' below setpoint '+str(self.setval)+', hyst '+str(self.hyst)+', inv '+str(self.invbit))
                    #else: ##
                    #    log.info('outval while act low already '+str(self.outval)+' as calculated new value '+str(outval)) ##
                #else: ##
                #    log.info('no outval change needed, still '+str(self.outval)) ##
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
        res1 = self.readval()
        res2 = self.output()
        if res1 == 0 and res2 == 0:
            return 0
        else:
            return 1
        