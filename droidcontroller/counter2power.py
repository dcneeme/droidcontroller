# used by cchannels.py, handles calculations for power one service member
# accepts input as raw counter value and returns value based on count and time increments since last execution
# 17.4.2014 started
# 21.4.2014 simplified (dict off)
# 24.4.2014 fix to power 0 when no increment in off state
# 25.4.2014 prooviks libisevat akent uuesti
# 27.04.2014 state change flag added to output
# 24.04.2016 refactored! added tests
'''
1) state on or off should be checked based on delays between increments. if above tout, then off, is below, then on. during off power 0 will be the result.
but what to do with the pulses that are slowly gathering? they are lost from power point of view. taken account into energy, so not to worry.
2) power should be calculated based on pulses received during on state. self.inc_dict, cannot have less than 2 members
'''

import time
import logging, sys
log = logging.getLogger(__name__)

class Counter2Power(): # returns power in W (and more)
    ''' Accepts input as raw counter value and returns value in W based on count and time in s increments since last execution.
        Missing pulse count increments will start off-state if time from last execution has been enough to detect drop below 1/3 of ON-state power.
        On-state is started if count has increased second time within off_tout
        
        using dictionary to keep count increments history within off_tout
    '''

    def __init__(self, svc_name='undefined', svc_member=1, off_tout=100, pulses4kWh=1000):  # 100s corresponds to 36W threshold if 1000 pulses per kWh
        self.svc_name = svc_name # just for checking the identity
        self.svc_member = svc_member # just for checking the identity
        self.state = 0 # OFF
        self.count = None # latest count
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

        self.ts_lastinc = None # last increment ts
        self.inc_dict = {} # averaging buffer to be filled with count increment only, {ts:count}
        log.info('Counter2Power() instance created for pwr svc '+self.svc_name+' member '+str(self.svc_member)+', off_tout '+str(self.off_tout))


    
    def get_svc(self):
        ''' Reports handled svc_name and member number as a tuple '''
        return self.svc_name, self.svc_member


    def chk_state(self, count):
        ''' decide about on or off state based on time between the increases. returns state None (no opinion), 0 (off) or 1 (on) '''
        ts = time.time()
        chg = 0 # change 0 or +/- 1
        inc = False

        if self.count != count: # increase in count
            if self.count == None:
                self.count = count; self.ts_lastinc = ts
                return None, 0, inc # next time is different
            self.count = count; self.ts_lastinc = ts

            if count < self.count:
                log.error(self.svc_name+' COUNT DROP from '+str(self.count)+' to '+str(count))
                return None, 0, inc
            else: # must be positive increment
                inc = True
                if ts - self.ts_lastinc < self.off_tout: # ON
                    if self.state != 1:
                        self.state = 1
                        chg = 1
        else: # no change in count
            if ts - self.ts_lastinc > self.off_tout: # OFF
                if self.state != 0:
                    self.state = 0
                    chg = -1

        #log.info(str(ts - self.ts_lastinc)+' s from last pulsecount increment')
        return self.state, chg, inc


    def calc(self, count):  #  ts, count, ts_now = None):
        ''' Return power in W and state based on counter value increment, taking previous values into account '''
        ts = time.time() # current timestamp, calculate in real time only
        count_inc = None
        ts_inc = None
        state, chg, inc = self.chk_state(count) # status 1 = ON. change flag 1 means just turned on, -1 means off. 0 means no change.
        #log.info('got from chk_state(): '+str((state, chg, inc)))

        if state != 1:
            self.power = 0
            self.inc_dict = {} # after a break new calc will begin
            return self.power, self.state, chg

        # now state == 1, power calc is possible
        # self.count = count annab viimase juurdekasvu, self.ts_lastinc on ka teada
        if inc: # COUNT INCREASED
            self.inc_dict.update({ts : count})
            #log.info('inc_dict updated to: '+str(self.inc_dict))

            if len(self.inc_dict) < 2: # not enough members, next time perhaps
                return None, self.state, False

            while min(self.inc_dict) < ts - self.off_tout: # remove the oldest element
                del self.inc_dict[min(self.inc_dict)]
                #log.info('inc_dict shortened to: '+str(self.inc_dict))

            if len(self.inc_dict) > 1:
                timefrom = min(self.inc_dict) # min ts
                countfrom = self.inc_dict[timefrom] # min count in dict, to be used in power calculation

                count_inc = count - countfrom
                ts_inc = ts - timefrom if ts - timefrom > 0 else 0
                if ts_inc == 0:
                    log.error('no time increase since last execution!')
                    return None, self.state, False

                self.power = round((3600000.0 / self.pulses4kWh)*(1.0*count_inc/ts_inc),3) # use buffer (with time-span close to off_tout) for increased precision
                log.debug(self.svc_name+' calculated power '+str(self.power)+' W')
        else:
            self.power = None
            count_inc = 0
            ts_inc = None
        return self.power, self.state, chg, count_inc, ts_inc



    def calctest(self): # use off_tout 3 for testing
        countlist = [0,0,1,2,3,5,7,9,11,11,11,11,9,9,9,9]
        out=[]
        for count in countlist:
            log.info('count '+str(count))
            new = self.calc(count)
            log.info('new '+str(new))
            out.append((count, new))
            time.sleep(2)
        for line in out:
            print(line)

    def statetest(self): # use off_tout 3 for testing
        countlist = [0,0,1,2,3,5,7,9,11,11,11,11,9,9,9,9]
        out=[]
        for count in countlist:
            log.info('count '+str(count))
            new = self.chk_state(count)
            log.info('new '+str(new))
            out.append((count, new))
            time.sleep(2)
        for line in out:
            print(line)
