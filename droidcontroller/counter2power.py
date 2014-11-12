# used by cchannels.py, handles calculations for power one service member
# accepts input as raw counter value and returns value based on count and time increments since last execution
# 17.4.2014 started
# 21.4.2014 simplified (dict off)
# 24.4.2014 fix to power 0 when no increment in off state
# 25.4.2014 prooviks libisevat akent uuesti
# 27.04.2014 state change flag added to output

import time
import logging
log = logging.getLogger(__name__)

class Counter2Power():
    ''' Accepts input as raw counter value and returns value in W based on count and time in s increments since last execution.
        Missing pulse count increments will start off-state if time from last execution has been enough to detect drop below 1/3 of ON-state power.
        On-state is started if count has increased at least by one since last execution.
        When ON-state has been lasting long enough to cover at least increment of avg_inc, precision flag will be set to 1.

    '''

    def __init__(self, svc_name='', svc_member=1, off_tout=100, pulses4kWh=1000):  # 100s corresponds to 36W threshold if 1000 pulses per kWh
        self.svc_name = svc_name
        self.svc_member=svc_member
        self.state = 0 # OFF
        self.off_tout = off_tout
        self.pulses4kWh = pulses4kWh
        self.init() # clear buffer dictionary

    def init(self): # to be used in case of counter (re)setting, to avoid jump to power calculation
        self.ts_last = 0 # time stamp of last count increase
        self.count_last = 0 # last received count
        self.inc_dict = {} # averaging buffer to be filled with count increment only, {ts:count}

    def get_svc(self):
        ''' Reports handled svc_name and member number as a tuple '''
        return self.svc_name, self.svc_member


    def calc(self, ts, count, ts_now = None):
        ''' Try to output a sane value based on count and time increments.
            If count increment is small, the precision is heavily affected. Use sliding window averaging
            and remember the maximum values, avoiding spikes during startup of the input pulse flow.
            What happens if decrease is negative? Ignore, output None, do not change inc_dict!
        '''

        chg=0 # change flag, 1 means on, -1 means off. 0 means no change.
        if self.ts_last == 0: # first execution
            self.ts_last = ts # time of last change before the current one
            self.count_last = count # last count before the current
            self.timefrom = ts # earliest timestamp (as key) in self.inc_dict
            self.countfrom = count
            return None, None, None, None # no data to calculate anything yet

        if ts_now == None:
            ts_now = time.time() # current time if not given
        timedelta = round(ts_now - self.ts_last,2) # now since last count change, for debugging data returned

        dict = {} # temporary dictionary
        len_inc = len(self.inc_dict)

        # possibly reduce buffering dictionary into off_tout time window. only count changes are buffered!
        if len_inc > 1:
            for key in sorted(self.inc_dict): #
                #if key < self.ts_last - self.off_tout and len_inc>1: # at least last one must be kept
                if key < ts_now - self.off_tout and len_inc>1: # at least last one must be kept
                    pass
                else:
                    dict[key] = self.inc_dict[key]
                len_inc = len_inc-1
            self.inc_dict=dict # replace the dictionary with shortened version according to the count difference between the ends
            #print('modified inc_dict:',self.inc_dict) # debug
            #self.timefrom=min(self.inc_dict, key=self.inc_dict.get) # ts with least count
            self.timefrom = min(self.inc_dict) # min ts
            self.countfrom = self.inc_dict[self.timefrom] # min count in dict, to be used in power calculation

        # add new item into dictonary
        if count > self.count_last and (ts - self.ts_last) > 0: # both count and ts must be monothonic
            log.debug('consider_on: ts_now, ts_last, off_tout',int(round(ts_now)), int(round(self.ts_last)), self.off_tout) # debug
            self.inc_dict[round(ts,2)] = count # added new item
            count_inc = count - self.countfrom if count > self.countfrom else 0
            ts_inc = ts - self.timefrom if ts - self.timefrom > 0 else 0
            log.debug('counter: increase both in ts '+str(ts - self.ts_last)+' and count '+str(int(round(count-self.count_last)))+' since last chg, buffer span ts_inc '+str(int(round(ts_inc)))+', count_inc, '+str(count_inc))  # debug

            if (ts - self.ts_last < 0.99*self.off_tout): # pulse increase below off_tout, hysteresis plus-minus 1% added
                if self.state == 0:
                    self.state = 1  # swithed ON #######################################################################
                    chg = 1
                power = round((3600000.0 / self.pulses4kWh)*(1.0*count_inc/ts_inc),3) # use buffer (with time-span close to off_tout) for increased precision
                self.count_last = count
                self.ts_last = ts
                return power, self.state, chg, round(ts_inc,2), count_inc, 'sure ON'
            else:
                self.count_last = count
                self.ts_last = ts
                return None, self.state, chg, timedelta, 0, 'no switch ON or off yet'

        elif count == self.count_last: # no count increase, no change in count_last or ts_last!
            if (ts_now - self.ts_last > 1.01*self.off_tout): # no new pulses, possible switfOFF with hysteresis 1%
                log.debug('consider_off: ts_now, ts_last, off_tout',int(round(ts_now)), int(round(self.ts_last)), self.off_tout) # debug
                if self.state >0:
                    self.state = 0 # swithed OFF #######################################################################
                    chg = -1
                return 0, 0, chg, round(ts_now - self.ts_last,2), 0, 'sure OFF'  # definitely OFF
            else:
                return None, self.state, chg, timedelta, 0, 'no switch OFF yet'

        else:
            return None, self.state, chg, timedelta, 0, 'something must be wrong'  # no power can be calculated, no state change for now

