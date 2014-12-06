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
         problems to output alarm could be too cold or too hot or not stopping in time.

    These external enable signals as levels are converted to start/stop pulses,
    to enable stopping from another source than the start came. Action via set_state.
    Local buttons or special calendar commands included via set_state command directly.

    Nagios services are stacked from bottom to up , keep heater the last!

    usage:
    from droidcontroller.sauna import *
    sa = Sauna() # default maxLen 120 min, hardcoded limit 4h,
          setTemp 85, (maxTemp is the 120 hardcoded limit)
    sa.heater(1)
    sa.setTemp(87)
    sa.setLen(180)
    Enabling signal can be manual (button or app) or from calendar.
    To stop sauna from remote if started by calendar, start and stop remotely.
    Local button stops immediately, also uptime reaching timeout.
'''

import time, sys
import logging
#log = logging.getLogger(__name__)
#log.addHandler(logging.NullHandler())

# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

class Sauna:
    ''' Class to control electric sauna and it's heater. Keeps the temperature using setpoint 
        temperature compared to actual with hysteresis, switches off on timeout or by command.  
        To switch off with stalled actual temperature (possible temperature sensor failure)
        use 0 as temperature to output() instead of repeating the last known.
    '''

    def __init__(self, temp=85, time=60*120, hyst=2):
        self.set_temp(temp) # degC, to keep during enabled state
        self.set_time(time) # timeout in seconds, to switch off
        self.state = 0
        self.sens_errorcount = 0 # temperature sensor missing if 256 degC
        self.set_state(0) # test for off
        self.startTS = 0 # ts of start if not 0
        self.alarmTS = 0 # to keep temperature alarm up for 5 minutes at least
        self.heater = 0
        self.ready = 0
        self.alarm = 0
        self.alarm_desc = ''
        self.maxTemp = 120 # absolute limit degC
        self.maxTime = 60*360 # absolute limit seconds
        self.hyst = hyst
        self.uptime = 0 # sauna uptime, counting from start
        self.cal_enable = 0 # control from calendar, keeping the current state
        self.rem_enable = 0  # control from remote panel, keeping the current state
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
        elif self.state == 1 and (1&input) == 0: # stopping
            #self.startTS = 0 # or should we keep the last start ts?
            log.info('sauna off')
        self.state = (1&input) # 0 or 1 allowed

    def get_state(self):
        ''' Returns the current state of sauna '''
        return self.state

    def set_time(self, input):
        ''' If this time of state being enabled is elapsed, sauna will be autodisabled '''
        self.setTime = input
        log.info('sauna working time changed to '+str(self.setTime)+' seconds')

    def get_time(self):
        ''' Returns the working time length set for sauna in seconds '''
        return self.setTime

    def get_uptime(self):
        ''' Returns the working time from sauna start in seconds '''
        return self.uptime


    def set_cal(self,input):
        ''' Sets the level signal to enable sauna from calendar, to catch the changes '''
        if (1&input) != self.cal_enable:
            log.info('sauna control signal change from calendar detected, new level '+str(1&input))
            self.cal_enable = (1&input)
            if self.cal_enable == 1: # only starts from calendar, stop by timeout or remote panel or local button
                self.set_state(1)
                
    def get_cal(self):
        ''' Returns the calendar_enable status '''
        return self.cal_enable

    def set_rem(self,input):
        ''' Sets the level signal to enable sauna from remote panel, to catch the changes '''
        if (1&input) != self.rem_enable:
            log.info('sauna control signal change from remote panel detected, new level '+str(1&input))
            self.set_state(1&input)
            self.rem_enable = (1&input)


    def get_rem(self):
        ''' Returns the calendar_enable status '''
        return self.cal_enable

    def set_alarm(self,input):
        ''' Sets or resets the alarm '''
        if (1&input) != self.alarm:
            log.info('alarm state changed to '+str(1&input))
            self.alarm = (1&input)
            self.alarm_desc = 'alarm level external change to '+str(self.alarm)+' at '+str(int(time.time()))

    def get_alarm(self):
        ''' Returns the alarm status and description '''
        return self.alarm, self.alarm_desc # int, string


    def output(self, actTemp):
        ''' Returns state, heater, alarm, ready as a list of int values.  '''
        now = time.time()
        if self.alarm == 0:
            if actTemp == 256: # temp sensor error
                self.sens_errorcount += 1
                if self.sens_errorcount  > 5:
                    self.alarm_desc = 'temperature sensor disconnected or faulty!'
                    self.alarm = 1
            elif actTemp < 10: # degC
                self.alarm_desc = 'temperature sensor must be faulty, temperature too low:'+str(actTemp)
                self.alarm = 1

            elif actTemp > self.maxTemp:
                self.alarm = 1
                self.alarm_desc = 'Sauna temperature '+str(actTemp)+' degC too high!'

            elif actTemp < self.setTemp/2.0 and self.uptime > self.maxTime/2 and self.state == 1: # too slow heating
                self.alarm = 1 # heater failure?

            if self.alarm > 0:
                alarmTS = now
                self.heater = 0
                self.ready = 0
                self.set_state(0)
                self.heater = 0
                log.warning(self.alarm_desc)
                return self.state, self.heater, self.alarm, self.ready
        else:
            if actTemp > 10 and actTemp < self.setTemp and now > self.alarmTS + 300: # alarm length at least 5 minutes
                self.alarm = 0
                self.alarm_desc = 'sauna temperature alarm was reset at '+str(now)
                log.warning(self.alarm_desc)
            # other alarms to be reset via external process, using set_alarm(0), time will be recorded

        if actTemp < self.setTemp - 10:
            self.ready = 0 # can be ready even if sauna off

        if self.state == 1:
            self.uptime = now - self.startTS # seconds from sauna start
            if self.uptime > self.setTime or self.uptime > self.maxTime:
                self.set_state(0)
                self.heater = 0
                log.info('sauna stopped due to timeout reached')

            if actTemp > self.setTemp + self.hyst and self.heater == 1: # so far on
                self.heater = 0
                self.ready = 1
                log.info('heater off')
            elif actTemp < self.setTemp - self.hyst and self.heater == 0: # so far off
                self.heater = 1
                log.info('heater on')
        else:
            self.heater = 0
            self.uptime = 0

        return self.state, self.heater, self.alarm, self.ready


