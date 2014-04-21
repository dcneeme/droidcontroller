# used by cchannels.py, handles calculations for power one service member
# accepts input as raw counter value and returns value based on count and time increments since last execution
# 17.4.2014 started
# 21.4.2014 simplified (dict off)


class Counter2Power(): 
    ''' Accepts input as raw counter value and returns value based on count and time increments since last execution.
        Missing pulse count increments will start off-state if time from last execution has been enough to detect drop below 1/3 of ON-state power.
        On-state is started if count has increased at least by one since last execution.
        When ON-state has been lasting long enough to cover at least increment of avg_inc, precision flag will be set to 1.
        
    '''

    def __init__(self, svc_name = '', svc_member = 1, off_tout = 120):  # 120s corresponds to 30W if 1Ws per pulse
        self.svc_name=svc_name
        self.svc_member=svc_member
        self.ts_last=0
        self.count_last=0
        self.state=0 # OFF
        self.off_tout = off_tout


    def get_svc(self):
        ''' Reports handled svc_name and member number as a tuple, adding also min and max limits '''
        return self.svc_name, self.svc_member, self.min, self.max


    def calc(self, ts, count):
        ''' Try to output a sane value based on count and time increments.
            If count increment is small, the precision is heavily affected. Use sliding window averaging
            and remember the maximum values, avoiding spikes during startup of the input pulse flow.
            What happens if decrease is negative? Ignore, output None, do not change inc_dict!
        '''

        if self.ts_last == 0: # first execution
            self.ts_last=ts
            self.count_last=count
            return None,None,None,None # no data to calculate anything yet

        count_inc = count - self.count_last if count > self.count_last else 0
        ts_inc = ts - self.ts_last if ts - self.ts_last > 0 else 0
        power_last = 0
        
        if ts_inc > 0:
            if (count_inc > 0) : # count increase since last execution!
                self.state = 1 # definitely ON
                power=round(1.0*(count - self.count_last)/(ts - self.ts_last),3)
                self.count_last=count
                self.ts_last=ts
                power_last=power_last
                return power, self.state, ts_inc, count_inc


            elif count_inc == 0: # no count increase
                if self.state>0:
                    if (ts_inc > self.off_tout): # time with no delay indicates at least 3 times drop in power
                        if self.state >0:
                            self.state=0
                            print('OFF due to no count increase in',ts_inc,'s') # debug
                        return 0,0,ts_inc, count_inc  # definitely OFF

                return None, self.state, ts_inc, count_inc  # no power returned, no change in state

        else:
            print 'zero time increment, no power output!'
            return None, self.state, ts_inc, count_inc
