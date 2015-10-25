''' Calculate cycle speed per second '''
import time, traceback

import logging
log = logging.getLogger(__name__)


class SpeedoMeter:
    ''' Counts the calls, return their number per second  '''

    def __init__(self, windowsize=100):
        ''' Calculations are based on sliding window of count() call timestamps. Counting can be started/stopped. '''
        self.winsize = windowsize
        self.counting = False
        self.reset()
        log.info('speedometer created with window size '+str(self.windowsize))

    def reset(self):
        ''' initial state, but does not change counting state! '''
        self.window = []
        self.speed = None


    def start(self):
        ''' Starts counting '''
        self.counting = True
        skiptime = time.time() - self.window[-1]
        for i in range(len(self.window)):
            self.window[i] += skiptime
        log.info('speedometer (re)started')

    def stop(self):
        ''' Stops counting, window time is not increased '''
        self.counting = False
        log.info('speedometer stopped')

        
    def get_state(self):
        ''' Returns False if stopped, True if counting '''
        return self.counting
        
        
    def get_speed(self):
        ''' Return current count per second '''
        return self.speed
        
        
    def count(self):
        ''' Updates the counting window (if counting) and calculates the new self.speed. No output returned. '''
        if self.counting:
            self.window.append(time.time())
            if len(self.window) > self.winsize:
                del self.window[0] # remove the oldest
        
            len = len(self.window)
            if len > 1:
                self.speed = (len - 1) / (self.window[-1] - self.window[0])
                log.info('current speed '+str(self.speed))
