# room heating control with possibly several water heating loops in the room. neeme 2015
#  class Cooler may be added....  using msgbus from controller_app! no dc, sc!

from droidcontroller.util_n import UN # for val2int()
from droidcontroller.pid import PID
from droidcontroller.it5888pwm import *

import traceback, logging, time
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

###############
class FloorTemperature(object): # one instance per floor loop. no d or ac needed, just msgbus!
    def __init__(self, msgbus, act_svc, set_svc, out_svc,
        name = 'undefined', period = 1000, phasedelay = 0, lolim = 150, hilim = 350): # time units s, temp ddegC
        ''' floor loops with slow pid and pwm period 1h, use shifted phase to load pump more evenly.
            The loops know their service and d member to get the setpoint and actuals.
            Limits are generally the same for the floor loops.
            when output() executed, new values for loop controls are calculated.
        '''
        # messagebus? several loops in the same room have to listen the same setpoint
        self.name = name
        self.msgbus = msgbus
        self.msgbus.subscribe('flooract', act_svc[0], 'flooract', self.set_actual) # token, subject, message
        self.msgbus.subscribe('floorset', set_svc[0], 'floorset', self.set_setpoint) # token, subject, message

        self.lolim = lolim
        self.hilim = hilim
        self.period = period # s
        self.phasedelay = phasedelay
        self.act_svc = act_svc if 'list' in str(type(act_svc)) else None # ['svc', member]
        self.set_svc = set_svc if 'list' in str(type(set_svc)) else None # ['svc', member]
        self.actual = None
        self.setpoint = None
        self.pid = PID(P = 1.0, I = 0.01, D = 0, min = 10, max = 990, outmode = 'nolist', name = name, dead_time = 0)
        self.out = 0 # do


    def set_actual(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.info('setting actual by member '+str(self.act_svc[1])+' %s, message %s', subject, str(message))
        actual = message['values'][self.act_svc[1] - 1] # svc members start from 1
        if actual == None:
            log.warning('INVALID actual '+str(actual)+' for '+self.name+' extracted from msgbus message '+str(message))
        else:
            log.info(self.name+' actual '+str(actual)+' from '+subject+'.'+str(self.act_svc[1])+', self.actual '+str(self.actual)) ##
            if self.actual != actual:
                log.info('set new actual to '+self.name+': '+str(self.actual)+' from '+subject+'.'+str(self.act_svc[1]))
                self.actual = actual
                

    def set_setpoint(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.info('setting setpoint by member '+str(self.set_svc[1])+' from %s, message %s', subject, str(message))
        setpoint = message['values'][self.set_svc[1] - 1] # svc members start from 1
        if setpoint == None:
            log.warning('INVALID setpoint '+str(setpoint)+' for '+self.name+' extracted from msgbus message '+str(message))
        else:
            log.info(self.name+' setpoint '+str(setpoint)+' from '+subject+'.'+str(self.set_svc[1])+', self.setpoint '+str(self.setpoint)) ##
            if self.setpoint != setpoint:
                log.info('set new setpoint to '+self.name+': '+str(self.setpoint)+' from '+subject+'.'+str(self.set_svc[1]))
                self.setpoint = setpoint
        

    def output(self): #  actual and setpoint are coming from msgbus and stored in self.actual, self.setpoint
        ''' Use PID to decide what the slow pwm output should be. '''
        len = 0 # without pid output
        if self.actual != None and self.setpoint != None:
            len = self.pid.output(self.setpoint, self.actual) # niipidi et oleks neg ts
            ptime = (time.time() + self.phasedelay) % self.period
            log.info('ptime for '+self.name+': '+str(int(ptime))) ##
            if ptime < len:
                out = 1
            else:
                out = 0
        else:
            log.warning('INVALID variable in '+self.name+' (actual,setpoint): '+str((self.actual, self.setpoint))+', (act_svc, set_svc) '+str((self.act_svc, self.set_svc)))
            out = None
            
        if out != self.out:
            self.out = out
            log.info('floor loop '+self.name+' valve state changed to '+str(self.out))

        return out, int(round((100.0 * len) / self.period, 1)) # the second member is pwm% with 1 decimal



###################
class RoomTemperature(object):
    ''' Controls room air temperature using floor loops with shared setpoint temperature '''
    def __init__(self, d, ac, msgbus, act_svc, set_svc, floorloops, name='undefined'): # floorloops is list of tuples [(in_ret_temp_svc, mbi, mba, reg, bit)]
        #self.act_svc = act_svc if 'list' in str(type(act_svc)) else None # ['svc', member]
        #self.set_svc = set_svc if 'list' in str(type(set_svc)) else None # ['svc', member]
        self.pid2floor = pid(PID(P=1.0, I=0.01, min=100, max=350, outmode='nolist', name='room '+name, dead_time=0))
        self.f = [] # floor loops
        for i in len(floorloops):
            self.f.append(FloorLoop(floorloops[i][0]))

    def doall(self, roomsetpoint):
        ''' Tries to set shared setpoint to floor loops in order to maintain the temperature in the room '''
        setfloor = self.pid2floor(ac.get(act_svc), ac.get(act_svc)) # ddeg


