# used by cchannels.py, handles calculations for power one service member
# accepts input as raw counter value and returns value based on count and time increments since last execution
# 17.4.2014 started
# 21.4.2014 simplified (dict off)
# 24.4.2014 fix to power 0 when no increment in off state


class Counter2Power(): 
    ''' Accepts input as raw counter value and returns value based on count and time increments since last execution.
        Missing pulse count increments will start off-state if time from last execution has been enough to detect drop below 1/3 of ON-state power.
        On-state is started if count has increased at least by one since last execution.
        When ON-state has been lasting long enough to cover at least increment of avg_inc, precision flag will be set to 1.
        
    '''

    def __init__(self, svc_name = '', svc_member = 1, off_tout = 100):  # 100s corresponds to 36W threshold if 1000 pulses per kWh
        self.svc_name=svc_name
        self.svc_member=svc_member
        self.ts_last=0
        self.count_last=0
        self.state=0 # OFF
        self.off_tout = off_tout


    def get_svc(self):
        ''' Reports handled svc_name and member number as a tuple, adding also min and max limits '''
        return self.svc_name, self.svc_member, self.min, self.max


    def calc(self, ts, count, ts_now = None):
        ''' Try to output a sane value based on count and time increments.
            If count increment is small, the precision is heavily affected. Use sliding window averaging
            and remember the maximum values, avoiding spikes during startup of the input pulse flow.
            What happens if decrease is negative? Ignore, output None, do not change inc_dict!
        '''

        if self.ts_last == 0: # first execution
            self.ts_last=ts
            self.count_last=count
            return None,None,None,None # no data to calculate anything yet

        if ts_now == None:
            ts_now=time.time() # time in s now, for testing external time in fictional units can be given
            
        count_inc = count - self.count_last if count > self.count_last else 0
        ts_inc = ts - self.ts_last if ts - self.ts_last > 0 else 0
                
        if (count_inc > 0) : # count increase since last execution! that means ts change too. 1 pulse is not enough!
            if (ts_now - ts < 0.99*self.off_tout): # hysteresis plus-minus 1% added
                if self.state == 0:
                    self.state=1
                    #print('ON due to count increase since',ts_inc,'s') # debug
                power=round(1.0*(count - self.count_last)/(ts - self.ts_last),3)
                self.count_last=count
                self.ts_last=ts
                return power, self.state, round(ts_inc,2), count_inc

        elif count_inc == 0: # no count increase
            if (ts_now - ts > 1.01*self.off_tout): # hysteresis plus-minus 1% added
                if self.state >0:
                    self.state=0
                    #print('OFF due to no count increase since',ts_inc,'s') # debug
                return 0,0,round(ts_now - ts,2), 0  # definitely OFF

        return None, self.state, round(ts_now - ts,2), 0  # no new power reading returned, no change in state

