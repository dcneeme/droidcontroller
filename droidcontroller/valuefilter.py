# accept new value as output if new value steady for delay or confirmed count times or both
import time
import logging
log = logging.getLogger(__name__)


class ValueFilter():
    ''' Accept new value as output if new value steady for delay s or confirmed cfmcount times or both.   
        # from valuefilter import *
        # vf = ValueFilter()
        # vf.output(1)
    '''

    def __init__(self, delay=1, cfmcount=1, defaultvalue=0): # delay in seconds
        self.delay = delay
        self.cfmcount = cfmcount # number of confirmations to the same value
        self.value = defaultvalue
        self.newvalue = defaultvalue
        self.match= 0
        self.ts_chg = 0
        self.defaultvalue = defaultvalue # to be returned in case of total failure
        log.info('created valuefilter instance with delay '+str(self.delay)+' and cfmcount '+str(self.cfmcount)) 
        # error band could be added for continuous values to accept some noise
        
    def output(self,value):
        ''' Returns filtered value '''
        if value != self.newvalue: # change in value
            self.match = 0
            self.ts_chg = time.time()
            self.newvalue = value
        else:
            self.match += 1
            
        timediff = time.time() - self.ts_chg
        
        if timediff > self.delay and self.match >= self.cfmcount:
            self.value = self.newvalue
            log.debug('change, timediff '+str(round(timediff,2))+', confirmed '+str(self.match)+' times')
        else:
            log.debug('NO change yet, timediff '+str(round(timediff,2))+', confirmed '+str(self.match)+' times')
            
        if self.value != None:
            return self.value
        else:
            log.warning('replaced value to return with default value '+str(self.defaultvalue))
            return self.defaultvalue
            
