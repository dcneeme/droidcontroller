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
        name = 'undefined', period = 1000, phasedelay = 0, lolim = 150, hilim = 350, inv=False): # time units s, temp ddegC. inv=False for NC valves.
        ''' floor loops with slow pid and pwm period 1h, use shifted phase to load pump more evenly.
            The loops know their service and d member to get the setpoint and actuals.
            Limits are generally the same for the floor loops.
            when output() executed, new values for loop controls are calculated.

            Actual temperature for floor loop should be measured only while valve is open!
            It is impossible to measure if open time is less than 100s or so!
        '''
        # messagebus? several loops in the same room have to listen the same setpoint
        self.name = name
        self.inv = inv # False if NC valves (valves open with current). use inv=True for NO valves.
        self.vars = {} # for getvars only
        self.msgbus = msgbus
        self.msgbus.subscribe('act_'+self.name, act_svc[0], 'flooract', self.set_actual) # token, subject, message
        self.msgbus.subscribe('set_'+self.name, set_svc[0], 'floorset', self.set_setpoint) # token, subject, message

        self.lolim = lolim
        self.hilim = hilim
        self.period = period # s
        self.phasedelay = phasedelay
        self.act_svc = act_svc if 'list' in str(type(act_svc)) else None # ['svc', member]
        self.set_svc = set_svc if 'list' in str(type(set_svc)) else None # ['svc', member]
        #self.actual = None
        #self.setpoint = None
        self.pid = PID(P = 0.05, I = 0.002, D = 0, min = lolim, max = hilim, outmode = 'nolist', name = name, dead_time = 0, inv=self.inv) 
        # no inversion, hi pwm = more heating
        # 0.1 ja 0.01 oli vonkuv, periood 1,5 oopaeva... 
        self.out = 0 # do


    def set_actual(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.debug('setting '+self.name+' actual by member '+str(self.act_svc[1])+' %s, message %s', subject, str(message))
        actual = message['values'][self.act_svc[1] - 1] # svc members start from 1
        if actual == None:
            log.warning('INVALID actual '+str(actual)+' for '+self.name+' extracted from msgbus message '+str(message))
        else:
            ptime = (time.time() + self.phasedelay) % self.period
            if self.out == 1 and ptime > 30: # valve open for at least 30 s
                #log.debug('setting actual to '+self.name+' actual '+str(actual)+' from msgbus '+subject+'.'+str(self.act_svc[1])) ##
                self.pid.set_actual(actual)
            

    def set_setpoint(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.debug('setting '+self.name+' setpoint by member '+str(self.set_svc[1])+' from %s, message %s', subject, str(message))
        setpoint = message['values'][self.set_svc[1] - 1] # svc members start from 1
        if setpoint == None:
            log.error('INVALID setpoint '+str(setpoint)+' for '+self.name+' extracted from msgbus message '+str(message))
        else:
            #log.debug('setting setpoint to floor loop '+self.name+': '+str(setpoint)+' from msgbus '+subject+'.'+str(self.set_svc[1]))
            self.pid.setSetpoint(setpoint)


    def getvars(self, filter = None):
        ''' Returns internal variables as dictionary '''
        self.vars.update({'lolim' : self.lolim,
            'hilim' : self.hilim,
            'actual' : self.pid.getvars(filter='actual'),
            'setpoint' : self.pid.getvars(filter='setpoint'),
            'phasedelay' : self.phasedelay,
            'out' : self.out,
            'inv' : self.inv,
            'name': self.name
            })
        if filter is None: # return everything
            return self.vars
        else:
            if filter in self.vars:
                return self.vars.get(filter)


    def output(self): #  actual and setpoint are coming from msgbus and written to pid() before
        ''' Use PID to decide what the slow pwm output should be. '''
        len = 0 # without pid output
        #if self.actual != None and self.setpoint != None:
            #len = self.pid.output(self.setpoint, self.actual) # niipidi et oleks neg ts
        try:
            len = self.pid.output() # kasutame varem seatud muutujaid
            ptime = (time.time() + self.phasedelay) % self.period
            #log.info('ptime for '+self.name+': '+str(int(ptime))) ## pulse time
            if ptime < len:
                out = 1
            else:
                out = 0
        except:
            log.warning('FAILED PID calculation for '+self.name+', (act_svc, set_svc) '+str((self.act_svc, self.set_svc)))
            out = None
            traceback.print_exc()

        if out != self.out:
            self.out = out
            log.debug('floor loop '+self.name+' valve state changed to '+str(self.out))

        return self.out, int(round((100.0 * len) / self.period, 1)) # value and pwm% with 1 decimal



###################
class RoomTemperature(object):
    ''' Controls room air temperature using floor loops with shared setpoint temperature '''
    def __init__(self, msgbus, act_svc, set_svc, out_svc, name = 'undefined', lolim = 150, hilim = 250):
        self.name = name
        self.vars = {} # for getvars only
        self.msgbus = msgbus
        self.msgbus.subscribe('act_'+self.name, act_svc[0], 'room_act', self.set_actual) # token, subject, message
        self.msgbus.subscribe('set_'+self.name, set_svc[0], 'room_set', self.set_setpoint) # token, subject, message
        self.lolim = lolim
        self.hilim = hilim
        self.act_svc = act_svc if 'list' in str(type(act_svc)) else None # ['svc', member]
        self.set_svc = set_svc if 'list' in str(type(set_svc)) else None # ['svc', member]
        self.pid = PID(P = 0.1, I = 0.001, D = 0, min = lolim, max = hilim, outmode = 'nolist', name = name, dead_time = 0) # no inversion here


    def set_actual(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.debug('setting '+self.name+' actual by member '+str(self.act_svc[1])+' %s, message %s', subject, str(message))
        actual = message['values'][self.act_svc[1] - 1] # svc members start from 1
        if actual == None:
            log.warning('INVALID actual '+str(actual)+' for '+self.name+' extracted from msgbus message '+str(message))
        else:
            log.info('setting actual to '+self.name+' actual '+str(actual)+' from msgbus '+subject+'.'+str(self.act_svc[1])) ##
            self.pid.set_actual(actual)


    def set_setpoint(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.debug('setting '+self.name+' setpoint by member '+str(self.set_svc[1])+' from %s, message %s', subject, str(message))
        setpoint = message['values'][self.set_svc[1] - 1] # svc members start from 1
        if setpoint == None:
            log.warning('INVALID setpoint '+str(setpoint)+' for '+self.name+' extracted from msgbus message '+str(message))
        else:
            log.info('setting setpoint to air loop '+self.name+': '+str(setpoint)+' from msgbus '+subject+'.'+str(self.set_svc[1]))
            self.pid.setSetpoint(setpoint)


    def getvars(self, filter = None):
        ''' Returns internal variables as dictionary '''
        self.vars.update({'lolim' : self.lolim,
            'hilim' : self.hilim,
            'actual' : self.pid.getvars(filter='actual'),
            'setpoint' : self.pid.getvars(filter='setpoint'),
            'out' : self.out,
            'name': self.name })
        if filter is None: # return everything
            return self.vars
        else:
            if filter in self.vars:
                return self.vars.get(filter)


    def output(self): #  actual and setpoint are coming from msgbus and written to pid() before
        ''' Use PID to decide what the slow pwm output should be. '''
        try:
            out = self.pid.output() # kasutame varem seatud muutujaid
        except:
            log.warning('FAILED PID calculation for '+self.name+', (act_svc, set_svc) '+str((self.act_svc, self.set_svc)))
            out = None
            traceback.print_exc()
        return out # just value
