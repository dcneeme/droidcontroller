#
# Copyright 2014 droid4control
#

''' Class and methods to control sauna. Should be enabled or disabled externally.
    If enabled, the temperature must be controlled according to the setpoint.
    Can be controlled just by shifting the setpoint too...
    If the temperature reaches the upper limit first time after enabling,
    a message should be sent out with "sauna ready"-kind of information.
    Voice feedback? In case of Android remote control panel app, sure!
    If sauna does not get reach the set temperature in 1 hour, alarm!

    Related services.
      1) SEW:0 1 0  # cal_enable man_enable, critalarm(ready)
      2) SRW:0 1 0  # state, heater, critalarm(malfunction)
         problems could be too cold or too hot or not stopping in time.

    nagios services are stacked from bottom to up , keep heater the last!

    usage:
    from droidcontroller.sauna import *
    sa = Sauna() # default maxLen 120 min, hardcoded limit 4h,
          setTemp 85, (maxTemp is the 120 hardcoded limit)
    sa.heater(1)
    sa.setTemp(87)
    sa.setLen(180)
    Enabling signal can be manual (button or app) or from calendar

'''

import time
import logging
log = logging.getLogger(__name__)

class Sauna:
    ''' Class to control electric sauna and it's heater. '''
    def __init__(self, temp=85, time=120, hyst=2):
        self.set_temp(temp) # degC, to keep during enabled state
        self.set_time(time)
        self.state = 0
        self.set_state(0) # test for off
        self.startTS = 0 # ts of start if not 0
        self.heater = 0
        self.ready = 0
        self.alarm = 0
        self.maxTemp = 120 # absolute limit degC
        self.maxTime = 360 # absolute limit minutes
        self.hyst = hyst
        self.enabled_time = 0
        log.info('Sauna init')

    def set_temp(self, input):
        ''' Sets temperature setpoint '''
        self.setTemp = input
        log.info('sauna setup temperature changed to '+str(self.setTemp))

    def get_temp(self):
        ''' Returns the sauna temperature setpoint '''
        return self.setTemp

    def set_state(self, input): # 0 off, 1 on
        '''Switches sauna on or off (enables or disables heating too) '''
        if self.state == 0 and (1&input) == 1: # so far disabled, starting
            self.startTS = time.time()
            log.info('sauna on')
        else: # must be stopping
            self.startTS = 0 # or should we keep the last start ts?
            log.info('sauna off')
        self.state = (1&input) # 0 or 1 allowed

    def get_state(self):
        ''' Returns the current state of sauna '''
        return self.state

    def set_time(self, input):
        ''' If this time of state being enabled is elapsed, sauna will be autodisabled '''
        self.setTime = input
        log.info('sauna working time changed to '+str(self.setTime)+' minutes')

    def get_time(self):
        ''' Returns the working time length set for sauna '''
        return self.setTime

    def output(self, actTemp):
        ''' Outputs self.state, self.heater, self.alarm, self.ready as a list of int values.  '''
        now = time.time()
        if actTemp == 256: # temp sensor error
            self.heater = 0
            self.ready = 0
            self.alarm = 1
            log.warning('invalid temperature', actTemp, 'missing or faulty sensor?')
            return self.state, self.heater, self.alarm, self.ready

        if now > self.startTS + 60*self.setTime or now > self.startTS + 60*self.maxTime:
            self.set_state(0) # switch off
            self.heater = 0
            log.info('sauna off')

        if actTemp < self.setTemp - 10:
            self.ready = 0

        if self.state == 1:
            if actTemp > self.setTemp + self.hyst:
                self.heater = 0
                self.ready = 1
                log.info('heater off')
            elif actTemp < self.setTemp - self.hyst:
                self.heater = 1
                log.info('heater on')
        else:
            self.heater = 0

        if self.alarm == 0 and (actTemp > self.maxTemp or \
                (actTemp < self.setTemp/2.0 and (now > self.startTS + 60*self.maxTime/3) and self.state == 1)): # not in alarm previosly
            self.set_state(0)
            self.heater = 0
            self.alarm = 1 # alarm too cold, heater failure
            self.ready = 0
            log.warning('abnormal sauna temperature '+str(actTemp)+' degC - either too high or too low. ')

        return self.state, self.heater, self.alarm, self.ready