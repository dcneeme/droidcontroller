# classes and methods to calculate heat agent flow and transported energy
# droid4control 2014
#
# usage:
# from heatflow import *
# fr = FlowRate()
# he = HeatExchange(0.05)
# fr.output(1,1)
# he.output(1,40,30)

import time
import logging
log = logging.getLogger(__name__)

class FlowRate:
    ''' Class to calculate values related to heat exchange metering '''
    def __init__(self, lpp = 10): # litres per pulse from metering device
        self.lpp = lpp
        self.flowrate = None
        self.di_pulse = 0
        self.di_pump = 0
        self.pstate = 0
        self.ts_start = 0
        log.info('FlowRate init')

    def output(self, di_pump, di_pulse):
        ''' Returns flow rate l/s based on pulse count slow increment from
            fluid flow meter, usually with symmetrical (50% active) pulse output.
            Flowrate on output is calculated during continuous pumping only, based on
            flowmeter pulse raising edge (this may be detected faster than
            the counters are read). Not to be used with electric meters / fast pulse output.
            Averages the flow rate with the last calculated result. Result is likely to
            vary depending on the temperature of the pumped fluid.
            Execute this at DI polling speed, will skip unnecessary execs.
        '''
        tsnow = time.time()
        flowrate = 0
        if di_pump == 1: # pumping
            if di_pulse != self.di_pulse: # pulse input level change
                self.di_pulse = di_pulse
                if self.di_pulse  == 1: # this edge active
                    if self.pstate == 0: # first pulse during pumping session
                        self.ts_start = tsnow
                        self.pstate = 1
                        #self.avg = 1 # average on first pulse interval
                    else:
                        if tsnow > self.ts_start and self.ts_start != 0:
                            flowrate = self.lpp / (tsnow - self.ts_start) # update on every pulse
                            self.ts_start = tsnow # count again for each pulse
                        else:
                            log.warning('invalid flowrate timing')

                    if self.flowrate != None and flowrate != 0: # first pulse during pumping session
                        self.flowrate = (self.flowrate + flowrate)/2
                        #self.avg = 0
                    else:
                        self.flowrate = flowrate
        else:
            self.pstate = 0


        return self.flowrate


class HeatExchange:
    ''' Class to calculate values related to heat exchange metering '''
    def __init__(self, flowrate, cp1 = 3776, tp1 = 26.7, cp2 = 3919, tp2 = 93.3, interval = 10): # ethylen-glycol 30%
        self.di_pump = 0 # pump off initally
        self.cp1 = cp1
        self.tp1 = tp1
        self.cp2 = cp2
        self.tp2 = tp2
        self.interval = interval # do not recalculate more often than that during pump on
        self.ts_start = 0 # not pumped since initialization
        self.ts_stop = 0
        self.Tdiff = 0 # degC
        self.energy = 0 # cumulative J
        self.ptime = 0 # cumulative s
        self.setflowrate(flowrate) # may change with temperature change
        log.info('HeatExchange init')


    def setflowrate(self, flowrate):
        ''' Updates flow rate for pump based on actual flowmeter pulse processing '''
        self.flowrate = flowrate


    def getflowrate(self):
        ''' Returns flow rate for pump based on actual flowmeter pulse processing '''
        return self.flowrate


    def output(self, di_pump, Ton, Tret):
        ''' Returns tuple of W, J, s based on pump state, Ton, Treturn,
            flowrate, specific heat and temperature of pumped agent in 2 points.
            Result also depends on changing flowrate (update often).
            Execute this at DI polling speed, will skip unnecessary recalculatsions
            during pumping session if interval is not passed since last execution.
        '''
      # average specific heat based on onflow nand return temperatures
        tsnow = time.time()
        Tdiff = Ton - Tret
        # interpolated specific energy for heat agent based on average temperature
        self.cp = self.interpolate((Ton + Tret)/2, self.tp1, self.cp1, self.tp2, self.cp2)
        if di_pump != self.di_pump: # pump state changed
            self.di_pump = di_pump
            if self.di_pump  == 1: # start
                self.ts_start = tsnow
                self.power = self.flowrate * Tdiff * self.cp
            else: # stop
                ts_diff = tsnow - self.ts_start
                self.energy += ts_diff * self.flowrate * self.cp
                self.ptime += ts_diff
                self.power = 0

            self.Tdiff = Tdiff

        else: # no chg in pump state
            if di_pump == 1: # PUMPING
                if (tsnow > self.ts_start + self.interval or Tdiff > 1.5*self.Tdiff or Tdiff < 0.5*self.Tdiff): 
                    # do not recalculate too often during pumping
                    self.power = self.flowrate * Tdiff * self.cp #
                    self.energy += (tsnow - self.ts_start) * self.power
                    self.ptime += (tsnow - self.ts_start)
                    self.ts_start = tsnow
                    self.Tdiff = Tdiff
            else:
                self.power = 0

        log.info('flowrate, Ton, Tret', self.flowrate, Ton, Tret)
        return self.power, self.energy, self.ptime


    def interpolate(self, x, x1 = 0, y1 = 0, x2 = 0, y2 = 0):
        ''' Returns linearly interpolated value y based on x and two known points defined by x1,y1 and x2,y2 '''
        if y1 != y2: # valid data to avoid division by zero
            return y1+(x-x1)*(y2-y1)/(x2-x1)
        else:
            log.warning('invalid interpolation attempt')
            return None


if __name__ == '__main__':
    pass