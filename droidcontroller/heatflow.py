# classes and methods to calculate heat agent flow and transported energy
# droid4control 2014
# usage:
#
#

import time
import logging
log = logging.getLogger(__name__)

class FlowRate:
    ''' Returns flow rate l/s based on pulse count slow increment from
        fluid flow meter, usually with symmetrical (50% active) pulse output.
        Flowrate on output is calculated during continuous pumping only, based on
        flowmeter pulse raising edge (this may be detected faster than
        the counters are read). Not to be used with electric meters / fast pulse output.
        Averages the flow rate with the last calculated result if that is not zero.
    '''
    def __init__(self, lps = 10): # last parameter: litres per second
        self.lps = lps
        self.flowrate = None
        self.di_pulse = 0
        self.di_pump = 0
        self.pstate = 0
        self.ts_start = 0
        log.info('FlowRate init')

    def output(self, di_pump, di_pulse):
        flowrate = 0
        if di_pump == 1: # pumping
            if di_pulse != self.di_pulse:
                self.di_pulse = di_pulse
                if self.di_pulse  == 1: # count
                    if self.pstate == 0: # first pulse during pumping session
                        self.ts_start = time.time()
                        self.pstate = 1
                        self.avg = 1 # average on first pulse interval
                    else:
                        if time.time() > self.ts_start and self.ts_start != 0:
                            flowrate = self.lps / (time.time() - self.ts_start) # update on every pulse
                        else:
                            log.warning('invalid flowrate timing')

                    if self.avg == 1 and self.flowrate != None and flowrate != 0: # first pulse during pumping session
                        self.flowrate = (self.flowrate + flowrate)/2
                        self.avg = 0
                    else:
                        self.flowrate = flowrate
        return self.flowrate


class HeatExchange:
    ''' Returns tuple of W, J, s based on pump state, Ton, Treturn,
        flowrate, specific heat and temperature of pumped agent in 2 points
    '''
    def __init__(self, flowrate, cp1 = 3776, tp1 = 26.7, cp2 = 3919, tp2 = 93.3): # ethylen-glycol 30%
        self.di_pump = 0 # pump off initally
        self.cp1 = cp1
        self.tp1 = tp1
        self.cp2 = cp2
        self.tp2 = tp2
        self.ts_start = 0 # not pumped since initialization
        self.ts_stop = 0
        self.energy = 0 # cumulative J
        self.ptime = 0 # cumulative s
        self.setflowrate(flowrate) # may change with temperature change
        log.info('HeatExchange init')


    def setflowrate(self, flowrate):
        self.flowrate = flowrate


    def getflowrate(self):
        return self.flowrate


    def output(self, di_pump, Ton, Tret):
        # average specific heat based on onflow nand return temperatures
        tsnow = time.time()
        self.cp = self.interpolate((Ton + Tret)/2, self.tp1, self.cp1, self.tp2, self.cp2)
        if di_pump != self.di_pump:
            self.di_pump = di_pump
            if self.di_pump  == 1: # start
                self.ts_start = tsnow
            else:
                self.ts_stop = tsnow
                self.energy += (self.ts_stop - self.ts_start) * self.flowrate * self.cp
                self.ptime += (self.ts_stop - self.ts_start)


        if di_pump == 1: # PUMPING
            power = self.flowrate * (Ton - Tret) * self.cp # to be recalculated at the pumping end
            energy = self.energy + (tsnow - self.ts_start) * power # to be recalculated at the pumping end
            ptime = self.ptime = (tsnow - self.ts_start)
        else:
            power = 0
            energy = self.energy
            ptime = self.ptime

        log.info('flowrate, Ton, Tret', self.flowrate, Ton, Tret)
        return power, energy, ptime


    def interpolate(self, x, x1 = 0, y1 = 0, x2 = 0, y2 = 0):
        ''' Returns linearly interpolated value y based on x and two known points defined by x1,y1 and x2,y2 '''
        if y1 != y2: # valid data to avoid division by zero
            return y1+(x-x1)*(y2-y1)/(x2-x1)
        else:
            log.warning('invalid interpolation attempt')
            return None


if __name__ == '__main__':
    pass