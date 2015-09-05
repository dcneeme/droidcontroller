#
# Copyright 2014 droid4control
#

''' Classes and methods to calculate heat agent flow
and transported energy

usage:
from heatflow import *
pp=PulsePeriod()
pp.period(0,0)

fr = FlowRate()
fr.update(0,0)
fr.get_flow()
voi molemad korraga fr.output(0,0)

he = HeatExchange(0.05)
he.output(1,40,30)

    to get COP value use self.energylast divided by el en  consum inc since last cycle stop!
'''

import time, sys
import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)


class PulsePeriod:
    ''' Class to calculate flow meter output pulse periods during pump run only.
        from flowrate_test import *
        pp = PulsePeriod()
        pp.output(0,0)
    '''

    def __init__(self):
        self.di_pulse = 0 # previous
        self.di_pump = 0 # previous
        self.ts_last_fr = None # previous ts
        self.period = [0, 0] # hi lo jaoks eraldi, keskmistada eelmisega
        self.lastperiod = [0, 0] # used to calculate output
        log.info('PulsePeriod 1 init')


    def output(self, di_pump, di_pulse): # output 0 during no di_pump!
        ''' Returns LAST KNOWN averaged period in second averaged taking hi and lo input into account
            Execute this at DI polling speed, not to miss any di changes and to improve precision.
            precision improves with longer pumping cycles. Assuming stable period.
        '''
        if di_pump > 1 or di_pulse > 1:
            log.warning('invalid parameters '+str(di_pump)+' '+str(di_pulse))
            return None

        tsnow = time.time()
        if self.ts_last_fr == None:
            self.ts_last_fr = tsnow
        timeinc = tsnow - self.ts_last_fr
        self.ts_last_fr = tsnow

        if di_pump == 1: # only calculate during pump running
            self.period[0] += timeinc # pumping, extend current period[0]
            self.period[1] += timeinc # pumping, extend current period[1]

        log.info('tsnow '+str(int(tsnow))+', period '+str(self.period)+', lastperiod '+str(self.lastperiod))

        if di_pulse != self.di_pulse: # pulse edge detected, store and reset
            log.debug('pulse level to '+str(di_pulse)+', storing and clearing period['+str(di_pulse)+']')
            if self.period[(di_pulse)] > 0: # avoid zero
                self.lastperiod[(di_pulse)] = self.period[(di_pulse)] # new period result
            self.period[di_pulse] = 0 # clear one of the period time counters
            self.di_pulse = di_pulse

        output = (self.lastperiod[0] + self.lastperiod[1]) / 2

        if self.lastperiod[0] > 0 and self.lastperiod[1] > 0:
            return output
        else:
            log.warning('waiting for pulses... gathered periods currently '+str(self.period))
            return None # too early for results


class FlowRate:
    ''' Class to calculate values related to heat exchange metering.
    Suitable in cases where flow signal (like pump state) is available
    in addition to relatively rare S0 pulses from flowmeter.
    It is assumed that flow is stable when the pump works. Calculation is based on averaging.
    Volume counter (if present) is used to check and correct thee flowrate result.
    '''
    def __init__(self, litres_per_pulse = 10, maxpulsecount = 5):
        self.litres_per_pulse = litres_per_pulse # 
        self.maxpulsecount = maxpulsecount # mac increase in volume between 2 counter readings
        self.flowrate = [0, 0]
        self.di_pulse = 0
        self.di_pump = 0
        self.pstate = [0, 0] # separate for raising and falling edge calculations
        self.ts_last = [0, 0]
        self.pulsecount = [0, 0] # separate for both edges
        self.volume = [None, None]
        log.info('FlowRate init')

    def update(self, di_pump, di_pulse, volume = None): # execute often not to lose pulses!
        '''
        Flowrate output is calculated during continuous pumping only,
        based on flowmeter pulse raising edge (this may be detected faster
        than the counters are read). Not to be used with electric
        meters / fast pulse output.

        Averages the flow rate with the last calculated result. Result is
        likely to vary depending on the temperature of the pumped fluid.
        Execute this at DI polling speed, will skip unnecessary execs.

        Pumping sessions should be longer than the di_pulse intervals. Otherwise no result.

        FIXME do not update self.flowrate if just started the pumping session
        '''

        if di_pulse > 1 or di_pulse < 0:
            log.warning('invalid di_pulse level '+str(di_pulse))
            return None

        tsnow = time.time()
        if di_pump == 1: # pumping
            if di_pulse != self.di_pulse: # pulse edge detected
                if self.pstate[di_pulse] == 0: # first pulse level change during pumping session
                    self.ts_last[di_pulse] = tsnow
                    self.pulsecount[di_pulse] = 0
                    self.volume[di_pulse] = volume
                    self.pstate[di_pulse] = 1
                    log.info('pumping session start for pulse level '+str(di_pulse)+', volume '+str(volume))
                else: # not the first. only calculates for one edge!
                    if volume != None and self.volume[di_pulse] != None and \
                        volume - self.volume[di_pulse] > 0 and volume - self.volume[di_pulse] < self.maxpulsecount:
                        self.pulsecount[di_pulse] = volume - self.volume[di_pulse] # fixes the count even if some edges skpipped
                    else:
                        self.pulsecount[di_pulse] += 1 # assuming no edges are skipped...

                    if tsnow > self.ts_last[di_pulse] and self.ts_last[di_pulse] != 0:
                        # update on every pulse
                        self.flowrate[di_pulse] = (self.litres_per_pulse * self.pulsecount[di_pulse]) / (tsnow - self.ts_last[di_pulse])
                        log.info('flowrate level '+str(di_pulse)+'  updated to '+str(self.flowrate[di_pulse])+', pulsecount since pump start '+str(self.pulsecount[di_pulse]))
        else:
            if self.pstate[0] == 1 or self.pstate[1] == 1:
                self.pstate[0] = 0
                self.pstate[1] = 0
                log.info('pumping sessions end for both pulse levels, volume '+str(volume))
        self.di_pulse = di_pulse # remember the pulse level


    def get_flow(self):
        if self.flowrate[0] > 0 and self.flowrate[1] > 0:
            return (self.flowrate[0] + self.flowrate[1]) / 2
        elif self.flowrate[0] > 0 and self.flowrate[1] == 0:
            return self.flowrate[0]
        elif self.flowrate[1] > 0 and self.flowrate[0] == 0:
            return self.flowrate[1]
        else:
            return 0


    def output(self, di_pump, di_pulse, volume = None): # execute often not to lose pulses!
        ''' Returns flow rate l/s based on pulse count slow increment from
            fluid flow meter, usually with symmetrical (50% active) pulse
            output. Use often not to miss any pulses! time counting stops if di_pump == 0.
            External on/off signal is also needed in order to know when the rate is 0.
        '''
        self.update(di_pump, di_pulse, volume)
        return self.get_flow()


class HeatExchange:
    '''Class to calculate values related to heat exchange metering.
    Suitable in cases where flow signal (like pump state) is available
    and the flow rate of the pump is known (can be updated).

    Default parameters correspond to ethylen-glycol 30%

    for water use cp1=4200, tp1=20, cp2=4200, tp2=50
    '''
    def __init__(self, flowrate, cp1=3776, tp1=26.7,
                                 cp2=3919, tp2=93.3, interval=10, unit='J'): # J = Ws, Wh, hWh, kWh, MWh
        #flowrate unit l/s
        self.di_pump = 0 # pump off initally
        self.cp1 = cp1
        self.tp1 = tp1
        self.cp2 = cp2
        self.tp2 = tp2
        self.interval = interval # do not recalculate more often than that during pump on
        self.ts_last = 0 # not pumped since initialization
        self.ts_stop = 0
        ##self.Tdiff = 0 # degC
        self.energy = 0 # cumulative J
        self.ptime = 0 # cumulative s1
        self.set_flowrate(flowrate) # may change with temperature change
        self.energypos = 0 # restore from server if used
        self.energyneg = 0 # restore from server if used
        self.energycycle = 0 # sum energy during ongoing cycle
        self.energylast = 0 # sum energy from last cycle, use for cop calc
        self.flow_threshold = None # if not None, then used or cycle syncing
        self.unit = unit
        self.__set_divisor()
        log.info('HeatExchange init, energy unit '+self.unit+', power unit W')

    def __set_divisor(self):
        ''' Sets divisor to calc energy in needed units '''
        if self.unit == 'Ws' or self.unit == 'J':
            self.divisor = 1.0
        elif self.unit == 'Wh':
            self.divisor = 3600.0
        elif self.unit == 'hWh':
            self.divisor = 360000.0
        elif self.unit == 'kWh':
            self.divisor = 3600000.0
        elif self.unit == 'MWh':
            self.divisor = 3600000000.0
        else:
            self.divisor = 1.0
            log.warning('divisor 1 due to UNKNOWN unit '+self.unit)

    def set_flowrate(self, flowrate):
        '''Updates flow rate l/s for pump based on actual flowmeter pulse
        processing.

        Use FlowRate class to find the flowrate value based on flowmeter
        pulses.

        Flowrate changes are used for cycle start/end detection, if di_
        '''
        self.flowrate = flowrate

    def set_flow_threshold(self, invar): # l/s
        ''' Sets the level to detect on off states for heat pump for cycle syncing   '''
        self.flowthreshold = invar
        log.info('flowthreshold set to '+str(self.flowthreshold))

    def set_energy(self, invar):
        ''' Sets cumulative PRODUCED HEAT energy if needed to be restored '''
        self.energy = invar
        log.info('cumulative energy set to '+str(self.energy)+self.unit)

    def set_energypos(self, invar):
        ''' Restores produced positive heat '''
        self.energypos = invar
        log.info('energypos set to '+str(self.energypos)+self.unit)

    def set_energyneg(self, invar):
        ''' Restores produced melting heat energy '''
        self.energyneg = invar
        log.info('energyneg set to '+str(self.energyneg)+self.unit)


    def set_el_energy(self, invar): # NOT USED, missing COP calc! FIXME?
        ''' Sets cumulative CONSUMED ELECTRIC ENERGY, update before cop reading! '''
        self.el_energy = invar
        log.info('el_energyneg set to '+str(self.el_energy)+self.unit)


    def get_energy(self):
        ''' Returns flow rate for pump based on actual flowmeter pulse processing '''
        return self.energy # produced J


    def get_el_energy(self):
        ''' Returns WHAT? '''
        return self.el_energy # consumed


    def get_flowrate(self):
        ''' Returns flow rate for pump based on actual flowmeter pulse processing '''
        return self.flowrate

    def get_specificheat(self):
        ''' Returns specific heat of agent (J/(K*kg)) that depends on
        average agent temperature
        '''
        return self.cp


    def output(self, di_pump, Ton, Tret):
        '''Returns tuple of current power W,
        cumulative energy J (updated at the next cycle start!)
        and cumulative active time s
        based on pump state di_pump (0 or 1, where 1 means both compressor and flow active).
        temperatures Ton, Treturn (temperatures of heat exchange agent),
        flowrate and specific heat of the agent (may depend on temperature!).

        Result also depends on changing flowrate (update often).
        Execute this at DI polling speed, will skip unnecessary
        recalculatsions during pumping session if interval is not passed
        since last execution.

        To get value in Wh divide value in J by 3600.
        Output 0 if di_pump == 0, or flowrate == 0.

        To enable COP calculation externally the energy produced during last cycle is kept up too.
        '''

        # average specific heat based on onflow and return temperatures
        tsnow = time.time()
        ts_diff = tsnow - self.ts_last
        Tdiff = Ton - Tret
        log.debug('timediff', ts_diff, 'tempdiff', Tdiff)
        # interpolated specific energy for heat agent based on
        # average temperature for agent, has effect on specific heat
        self.cp = self.interpolate((Ton + Tret) / 2.0, self.tp1, self.cp1,
                                                   self.tp2, self.cp2)
        #cycle start (or end if no new start coming) must be detected
        if di_pump != self.di_pump: # pump state changed
            self.di_pump = di_pump
            if self.di_pump == 1: # start
                self.power = self.flowrate * Tdiff * self.cp
                self.energycycle = 0 # new cycle started, use this value for cop calculation
                self.ts_last = tsnow
                ts_diff = 0
                log.info('heat pump cycle started')

            else: # stop
                energydelta = ts_diff * Tdiff * self.flowrate * self.cp / self.divisor
                self.energy += energydelta
                self.energycycle += energydelta # last pumping cycle
                self.energylast = self.energycycle
                self.ptime += ts_diff
                self.power = 0
                if Tdiff > 0: # energypos increase
                    self.energypos += energydelta
                elif Tdiff < 0:
                    self.energyneg -= energydelta # value positive, meaning negative
                log.info('heat pump cycle stopped, produced energy during cycle '+str(round(self.energylast))+self.unit)


            ##self.Tdiff = Tdiff
        else: # no chg in pump state
            if di_pump == 1: # PUMPING
                #if (ts_diff > self.interval or
                #        Tdiff > 1.5 * self.Tdiff or
                #        Tdiff < 0.5 * self.Tdiff):
                self.power = self.flowrate * Tdiff * self.cp
                energydelta = ts_diff * self.power / self.divisor
                if self.power > 0: # energypos increase
                    self.energypos += energydelta
                elif self.power < 0:
                    self.energyneg -= energydelta # value positive, meaning negative
                self.energy += energydelta
                self.energycycle += energydelta
                self.ptime += (tsnow - self.ts_last)
                self.ts_last = tsnow
                ##self.Tdiff = Tdiff
            else:
                self.power = 0

        log.debug('flowrate = %d, Ton = %d, Tret = %d',
                  self.flowrate, Ton, Tret)
        return self.power, self.energy, self.ptime, self.energypos, self.energyneg, self.unit # W u s u u
        # last two are for separating the produced heat (energypos) from the production loss for heat pump melting (energyneg)


    def get_energylast(self):
        ''' Returns summary energy from last cycle generated by output(), use for COP calc '''
        return self.energylast # in self.units



    def interpolate(self, x, x1=0, y1=0, x2=0, y2=0):
        ''' Returns linearly interpolated value y based on x and
        two known points defined by x1,y1 and x2,y2
        '''
        if x1 == y2:
            log.warning('invalid interpolation attempt')
            # return average in case ponts have the same x coordinate
            return (y1+y2)/2.0
        else:
            return y1+(y2-y1)*(x-x1)/(x2-x1)


            