#
# Copyright 2014 droid4control
#

''' classes and methods to calculate limit level
    to control load based on currents in phases

    mittekriitilised tarbijad on soltuvad F2 koormusest.
    mitsu ja ventventilatsiooni taastamisel
    (ja ka tarbe suurenemisel) juhib teatud
    vahekriitiliste tarbijate tood ouman-gw
    piirangutaset ylal pidades. piirangutase
    leitakse kasutamata reservi alusel ja on
    jargmised:

    piirangutase max_vent%  vent_jahut_keeld  mitsu_keeld
    3               20            1              1
    2               100           1              1
    1               100           0              1
    0               100           0              0

    varujahutuse ja pohijahutuse suhe/lubatus soltub F1 koormusest,
    kontrollida, kus fiidril varujahutus asub!
'''

import time
import logging
log = logging.getLogger(__name__)

class LoadLimit:
    ''' Class to calculate limit level to enable or disable
        some load based on N-phase current on feed. Compares current
        with lo_limit, hi_limit and updates returned level
        being in range 0...3.
    '''
    def __init__(self, currentlevel=3, maxlevel=3, leveldelay=30, \
                                                 currentdelay=10, \
              lo_limit=180000, hi_limit=200000, phasecount=3):
        # current in mA
        self.currentlevel = currentlevel # initial limitation level on output
        self.maxlevel = maxlevel # initial limitation level on output
        self.lo_limit = lo_limit # decrease currentlevel by one if current below
        self.hi_limit = hi_limit # increase currentlimit to maxlevel if any current above
        self.leveldelay = leveldelay # no level changes more often than that
        self.currentdelay = currentdelay # filter to check current against lo_limit
        self.ts_notlocurrent = time.time() # must have age above currentdelay to enable currentlevel change
        self.phasecount = phasecount
        self.set_currentlevel(currentlevel)
        log.info('LimitLevel init done')


    def get_hi_limit(self):
        return self.hi_limit


    def set_hi_limit(self, input):
        self.hi_limit = input


    def get_lo_limit(self):
        return self.lo_limit


    def set_lo_limit(self, input):
        self.lo_limit = input


    def get_currentlevel(self):
        return self.currentlevel


    def set_currentlevel(self, input):
        if input >= 0 and input <= self.maxlevel:
            self.currentlevel = input
            self.ts_level = time.time()
        else:
            log.warning('attempt to set an invalid currentlevel ') # +str(input))


    def output(self, current = [0, 0, 0]):
        ''' Returns limitation level in range from 0 (no limitations) to
            3 (maximum limitation), avoiding changes faster than self.leveldelay.
            Limitation level increase is immediate, but decrease is allowed in
            increments of 1 after leveldelay s from previous change.
        ''' 
        tsnow = time.time()
        updn = 0 # self.currentlevel change
        if len(current) != self.phasecount:
            log.warning('invalid number of phase currents ') # +str(current))
            log.info('all controlled loads to be disconnected')
            return self.maxlevel

        for i in range(self.phasecount):
            # the values for i are 0 1 2 for 3 phases
            if current[i]  == None:
                #no valid value yet, do nothing
                log.warning('no change to self.currentlevel due to invalid current')
                return self.currentlevel # stop

            if (current[i] > self.hi_limit and \
                    self.currentlevel < self.maxlevel):
                updn += self.phasecount # to ensure detection
                self.ts_notlocurrent = tsnow  # updating with above lo_limit only
            elif (current[i] < self.lo_limit \
                    and self.currentlevel > 0 and updn <= 0):
                updn += -1 # must be -N (number of phases) in the end to have effect
            else:
                self.ts_notlocurrent = tsnow # updating with above lo_limit only

        if (updn > 0 and self.currentlevel < self.maxlevel):
            self.currentlevel = self.maxlevel
            self.ts_level = tsnow
            log.info('max limitations on backup feeder load set!') #  due to current '+str(current))
            #print('limitations to be set, level',self.currentlevel) # temporary
        elif (updn == -self.phasecount and tsnow > self.leveldelay + self.ts_level \
                and self.ts_notlocurrent < tsnow - self.currentdelay and self.currentlevel > 0):
            self.currentlevel += -1
            self.ts_level = tsnow
            log.info('limitations decrease to '+str(self.currentlevel))
            #print('limitations decrease, level', self.currentlevel) # temporary

        return self.currentlevel
