# used by cchannels.py, handles calculations for power one service member
# accepts input as raw counter value and returns value based on count and time increments since last execution
# 17.4.2014 started
# 21.4.2014 simplified (dict off)
# 24.4.2014 fix to power 0 when no increment in off state
# 25.4.2014 prooviks libisevat akent uuesti
# 27.04.2014 state change flag added to output

import time
import logging, sys
log = logging.getLogger(__name__)

class Counter2Power(): # returns power in W (and more)
    ''' Accepts input as raw counter value and returns value in W based on count and time in s increments since last execution.
        Missing pulse count increments will start off-state if time from last execution has been enough to detect drop below 1/3 of ON-state power.
        On-state is started if count has increased at least by one since last execution.
        When ON-state has been lasting long enough to cover at least increment of avg_inc, precision flag will be set to 1.

    '''

    def __init__(self, svc_name='undefined', svc_member=1, off_tout=100, pulses4kWh=1000):  # 100s corresponds to 36W threshold if 1000 pulses per kWh
        self.svc_name = svc_name # just for checking the identity
        self.svc_member = svc_member # just for checking the identity
        self.state = 0 # OFF
        self.power = None # initially
        
        try:
            if off_tout >0:
                self.off_tout = off_tout
            else:
                log.warning('MISSING off_tout='+str(off_tout)+' for svc '+self.svc_name+', using value 60 s instead (36W zero threshold)')
                self.off_tout = 60

            if pulses4kWh > 0:
                self.pulses4kWh = pulses4kWh
            else:
                log.warning('INVALID pulses4kWh='+str(self.pulses4kWh)+', using value 1000 instead')
                self.pulses4kWh = 1000

        except:
            log.error('init problem, counter2power may be unusable!')
            
        self.init() # clear buffer dictionary
        log.debug('Counter2Power() instance created for pwr svc '+self.svc_name+' member '+str(self.svc_member)+', off_tout '+str(self.off_tout))
        
        
    def init(self): # to be used in case of counter (re)setting, to avoid jump to power calculation
        self.ts_last = 0 # time stamp of last count increase
        self.count_last = 0 # last received count
        self.inc_dict = {} # averaging buffer to be filled with count increment only, {ts:count}


    def get_svc(self):
        ''' Reports handled svc_name and member number as a tuple '''
        return self.svc_name, self.svc_member


    def calc(self, count):  #  ts, count, ts_now = None):
        ''' Return power in W and state based on counter value increment, taking previous values into account '''
        ts = time.time() # current timestamp, calculate in real time only
        chg=0 # change flag, 1 means on, -1 means off. 0 means no change.
        
        if self.ts_last == 0: # first execution
            self.ts_last = ts # time of last change before the current one
            self.count_last = count # last count before the current
            self.timefrom = ts # earliest timestamp (as key) in self.inc_dict
            self.countfrom = count
            return None, None, None, None # no data to calculate anything yet

        ts_inc = ts - self.timefrom if ts - self.timefrom > 0 else 0
        timedelta = round(ts - self.ts_last,2) # now since last count change, for debugging data returned
        count_inc = count - self.countfrom if count > self.countfrom else 0
        dict = {} # temporary dictionary
        len_inc = len(self.inc_dict)

        # possibly reduce buffering dictionary into off_tout time window. only count changes are buffered!
        if len_inc > 1:
            for key in sorted(self.inc_dict): #
                #if key < self.ts_last - self.off_tout and len_inc>1: # at least last one must be kept
                if key < ts - self.off_tout and len_inc>1: # at least last one must be kept
                    pass
                else:
                    dict[key] = self.inc_dict[key]
                len_inc = len_inc-1
            self.inc_dict=dict # replace the dictionary with shortened version according to the count difference between the ends
            self.timefrom = min(self.inc_dict) # min ts
            self.countfrom = self.inc_dict[self.timefrom] # min count in dict, to be used in power calculation

        # add new item into dictionary
        if count > self.count_last and timedelta > 0: # both count and ts must be monothonic
            log.debug(self.svc_name+' consider_on: ts, ts_last, off_tout '+str(int(round(ts)))+', '+str(int(round(self.ts_last)))+', '+str(self.off_tout)) # debug
            self.inc_dict[round(ts,2)] = count # added new item
            ##count_inc = count - self.countfrom if count > self.countfrom else 0
            ##ts_inc = ts - self.timefrom if ts - self.timefrom > 0 else 0
            log.debug('counter: increase both in ts '+str(ts - self.ts_last)+' and count '+str(int(round(count-self.count_last)))+' since last chg, buffer span ts_inc '+str(int(round(ts_inc)))+', count_inc, '+str(count_inc))  # debug
            
            if count_inc > 1 and ts_inc > 0: # sure on
                if self.state == 0:
                    self.state = 1  # swithed ON #######################################################################
                    chg = 1
                self.power = round((3600000.0 / self.pulses4kWh)*(1.0*count_inc/ts_inc),3) # use buffer (with time-span close to off_tout) for increased precision
                log.debug(self.svc_name+' calculated power '+str(self.power)+' W')
                self.count_last = count
                self.ts_last = ts
                log.debug(self.svc_name+' sure ON')
                return self.power, self.state, chg, round(ts_inc,2), count_inc, 'sure ON'
            else:
                self.count_last = count
                self.ts_last = ts
                log.debug(self.svc_name+'no switch ON or off yet')
                return None, self.state, chg, timedelta, 0, 'no switch ON or off yet'

        elif count == self.count_last: # no count increase, no change in count_last or ts_last!
            if (timedelta > 1.01 * self.off_tout): # no new pulses, possible switch OFF with hysteresis 1%
                log.debug(self.svc_name+' consider_off: ts, ts_last, off_tout'+str(int(round(ts)))+', '+str(int(round(self.ts_last)))+', '+str(self.off_tout)) # debug
                if self.state >0:
                    self.state = 0 # swithed OFF #######################################################################
                    chg = -1
                log.debug(self.svc_name+' sure OFF')
                return 0, 0, chg, round(ts - self.ts_last,2), 0, 'sure OFF'  # definitely OFF
            elif timedelta < 0.1 * self.off_tout:
                return self.power, self.state, chg, round(ts_inc,2), count_inc, 'almost sure ON'
            else:
                log.debug(self.svc_name+' no switch OFF yet')
                return None, self.state, chg, timedelta, 0, 'no switch OFF yet'

        else:
            log.error(self.svc_name+' unexpected state: count='+str(count)+', count_last='+str(self.count_last)+', timedelta='+str(timedelta)+', initializing!')
            self.init()
            return None, self.state, chg, timedelta, 0, 'unexpected (negative?) count/time change, initialized!'  # no power can be calculated, no state change for now

