''' Calculate cycle speed per second '''
import time, traceback

import logging
log = logging.getLogger(__name__)


class SpeedoMeter():
    ''' Counts the calls, return their number per second  '''
    def __init__(self, windowsize=100):
        ''' Calculations are based on sliding window of count() call timestamps. Counting can be started/stopped. '''
        self.windowsize = windowsize
        self.counting = False
        self.ts_up = None
        self.ts_dn = None
        self.reset()
        log.info('speedometer created with window size '+str(self.windowsize))

    def reset(self):
        ''' initial state, but does not change counting state! '''
        self.window = []


    def start(self):
        ''' Starts counting '''
        if not self.counting:
            self.counting = True
            self.ts_up = time.time()
            log.info('speedometer (re)started')
            
        if self.ts_dn:
            skiptime = self.ts_up - self.ts_dn
            for i in range(len(self.window)):
                self.window[i] += skiptime
            log.info('skipped the time stopped')

    def stop(self):
        ''' Stops counting, window time is not increased '''
        if self.counting:
            self.counting = False
            self.ts_dn = time.time()
            log.info('speedometer stopped')


    def get_state(self):
        ''' Returns False if stopped, True if counting '''
        return self.counting


    def get_speed(self):
        ''' Return current count per second '''
        lenn = len(self.window)
        speed = None
        if lenn > 1:
            count = (lenn - 1)
            ts_inc = self.window[-1] - self.window[0]
            if ts_inc > 0:
                speed = count / ts_inc
                log.debug('current speed '+str(speed)+' ('+str(count)+' / ' +str(ts_inc)+')')
            return speed


    def get_window(self):
        ''' For debugging '''
        return self.window
        
        
    def count(self):
        ''' Updates the counting window (if counting) and calculates the new self.speed. No output returned. '''
        if self.counting:
            self.window.append(time.time())
            if len(self.window) > self.windowsize:
                del self.window[0] # remove the oldest

            
