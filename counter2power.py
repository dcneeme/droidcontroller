# used by cchannels.py, handles calculations for power one service member
# accepts input as raw counter value and returns value based on count and time increments since last execution
# 17.4.2014 started


class Count2Power(): # should it use cchannels as parent?
    ''' Accepts input as raw counter value and returns value based on count and time increments since last execution.
        Parameter maxinc is pulse increment to be used for sliding window averaging. Only ON-state values are taken into account,
        zero increments will start off-state if time from last execution has been enough to detect drop below 1/3 of ON-state power.
        On-state is started if count has increased at least by one since last execution.
        When ON-state is restarted after OFF-state, the avg_dict size by value diff is decreased to mininc.
        When ON-state has been lasting long enough to cover at least increment of avg_inc, precision flag will be set to 1.
        Power value returned by calc() is 0 during OFF-state and calculated using the values in inc_dict.
        The difference of last count value
    '''

    def __init__(self, svc_name = '', svc_member = 1, mininc = 10, maxinc = 100, minvalue = 0, maxvalue = None):
        self.svc_name=svc_name
        self.svc_member=svc_member
        #self.minvalue=minvalue # sane limits?
        #self.maxvalue=maxvalue
        self.inc=[mininc,maxinc]  # window sizes for restarted and continued ON-state, lower precision on restart using the end of last ON-state.
        self.ts_last=0
        self.count_last=0
        self.state=0 # OFF
        self.inc_dict={} # averaging buffer for ON-state, {ts:count}


    def get_svc(self):
        ''' Reports handled svc_name and member number as a tuple, adding also min and max limits '''
        return self.svc_name, self.svc_member, self.min, self.max


    def calc(self, ts, count):
        ''' Try to output a sane value based on count and time increments.
            If count increment is small, the precision is heavily affected. Use sliding window averaging
            and remember the maximum values, avoiding spikes during startup of the input pulse flow.
            What happens if decrease is negative? Ignore, output None, do not change inc_dict!
        '''

        # check dictionary size, delete items based on state and value differencies
        #min(self.inc_d, key=d.get)

        print self.inc_dict # debug

        if len(self.inc_dict) == 0: # first execution
            self.inc_dict[ts]=count
            self.ts_last=ts
            self.count_last=count
            return None,None,None,None # no data to calculate anything yet

        if len(self.inc_dict)>2: # possibly reduce the number of items if there is more than 2 items in it
            self.inc_dict = {k: v for k, v in self.inc_dict.items() if v > (count - self.inc[self.state])} # reduce item count based on state
            print('reduced inc_dict to:',self.inc_dict) # debug

        #find the item with minimum time (or count, no difference) from the dictionary
        timefrom=min(self.inc_dict, key=self.inc_dict.get) # ts with least count
        countfrom=self.inc_dict[timefrom] # min count in dict, to be used in power calculation

        if count>self.count_last: # only add new items to the inc_dict if there was a count increase since last execution!
            self.state = 1 # definitely ON
            self.inc_dict[ts]=count # added new item
            self.count_last=count
            self.ts_last=ts

        elif count == self.count_last: # no count increase
            # now is the time diff since last big enough to decide about OFF state?
            if count == countfrom: # no change since dict beginning
                self.state=0
                print('off1') # debug
                return 0,0,ts - timefrom, count-countfrom  # definitely OFF
            elif (count - countfrom)>0 and (ts - self.ts_last > 3.3*(ts-timefrom)/(count - countfrom)): # power drop below 1/3 avg verified
                self.state=0
                print('off2') # debug
                return 0,0,ts - timefrom, count-countfrom  # definitely OFF

        return 1.0*(count - countfrom)/(ts - timefrom), self.state, ts-timefrom, count-countfrom # average power over dict!
