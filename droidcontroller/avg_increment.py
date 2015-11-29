# neeme 2015`# FIXME sailita slid win koik vaartused, arvesta otsi

import time, logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO) # temporary
log = logging.getLogger(__name__)


class AvgSlidingWindow(object):
    ''' Calculates average increment based on first and last ts and count. 
        Both of them must be monotonic and increasing! use with meters. 
    '''
def __init__(self, timewindow = 3600, name='undefined'):
        self.timewindow = timewindow
        self.timefrom = None
        self.valuefrom = None
        self.timelast = None
        self.valuelast = None
        self.name = name
        self.inc_dict={}
        log.info('averaging instance created')
    
    def calc(self, count):  #  ts, count, ts_now = None):
        ''' Return power, and state based on counter value, taking previous values into account '''
        ts = time.time() # current timestamp, calculate in real time only
        chg = 0 # change flag, 1 means on, -1 means off. 0 means no change.
        
        if self.timelast == None: # first execution
            self.ts_last = ts # time of last change before the current one
            self.count_last = count # last count before the current
            self.timefrom = ts # earliest timestamp (as key) in self.inc_dict
            self.countfrom = count
            return None, None, None, None # no data to calculate anything yet

        ts_inc = ts - self.timefrom if ts - self.timefrom > 0 else 0
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
                len_inc = len_inc - 1
            self.inc_dict = dict # replace the dictionary with shortened version according to the count difference between the ends
            self.timefrom = min(self.inc_dict) # min ts
            self.countfrom = self.inc_dict[self.timefrom] # min count in dict, to be used in power calculation

        # add new item into dictionary
        if count >= self.count_last and ts_inc > 0: 
            return 1.0 * count_inc / ts_inc # average increment within the time window
        else:
            log.warning('negative increment? from '+str(count)+' to '+str(self.count_last)+', timedelta='+str(timedelta)+', initializing!')
            self.__init__()
            return None
            
            