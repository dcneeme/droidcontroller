#
# Copyright 2014 droid4control
#

''' Classes and methods to calculate heat agent flow
and transported energy

usage:
    from heatflow import *
    fr = FlowRate()
    he = HeatExchange(0.05)
    fr.output(1,1)
    he.output(1,40,30)

    2015 added class COP to be used with heat pumps 
'''

import time
import logging
log = logging.getLogger(__name__)

class FlowRate:
    ''' Class to calculate values related to heat exchange metering.
    Suitable in cases where flow signal (like pump state) is available
    in addition to relatively rare S0 pulses from flowmeter.
    '''
    def __init__(self, litres_per_pulse=10):
        self.litres_per_pulse = litres_per_pulse
        self.flowrate = None
        self.di_pulse = 0
        self.di_pump = 0
        self.pstate = 0
        self.ts_start = 0
        log.info('FlowRate init')

    def output(self, di_pump, di_pulse):
        ''' Returns flow rate l/s based on pulse count slow increment from
        fluid flow meter, usually with symmetrical (50% active) pulse
        output.

        Flowrate on output is calculated during continuous pumping only,
        based on flowmeter pulse raising edge (this may be detected faster
        than the counters are read). Not to be used with electric
        meters / fast pulse output.

        Averages the flow rate with the last calculated result. Result is
        likely to vary depending on the temperature of the pumped fluid.
        Execute this at DI polling speed, will skip unnecessary execs.
        '''
        tsnow = time.time()
        flowrate = 0
        if di_pump == 1:
            # pumping
            if di_pulse != self.di_pulse:
                # pulse input level change
                self.di_pulse = di_pulse
                if self.di_pulse == 1:
                    # this edge active
                    if self.pstate == 0:
                        # first pulse during pumping session
                        self.ts_start = tsnow
                        self.pstate = 1
                        #self.avg = 1 # average on first pulse interval
                    else:
                        if tsnow > self.ts_start and self.ts_start != 0:
                            # update on every pulse
                            flowrate = self.litres_per_pulse / (tsnow - self.ts_start)
                            # count again for each pulse
                            self.ts_start = tsnow
                        else:
                            log.warning('invalid flowrate timing')

                    if self.flowrate != None and flowrate != 0:
                        # first pulse during pumping session
                        self.flowrate = (self.flowrate + flowrate)/2
                        #self.avg = 0
                    else:
                        self.flowrate = flowrate
        else:
            self.pstate = 0

        return self.flowrate


class HeatExchange:
    '''Class to calculate values related to heat exchange metering.
    Suitable in cases where flow signal (like pump state) is available
    and the flow rate of the pump is known (can be updated).

    Default parameters correspond to ethylen-glycol 30%

    for water use cp1=4200, tp1=20, cp2=4200, tp2=50
    '''
    def __init__(self, flowrate, cp1=3776, tp1=26.7,
                                 cp2=3919, tp2=93.3, interval=10):
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
        self.set_flowrate(flowrate) # may change with temperature change
        self.cop = None # COP of the heat pump, last cycle
        self.flow_threshold = None # if not None, then used or cycle syncing
        #self.avgcop = None # average over all time and energy / non need for this!
        log.info('HeatExchange init')

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
        

    def set_energy(self, invar, unit = 'J'):
        ''' Sets cumulative PRODUCED HEAT energy if needed to be restored '''
        if unit == 'Wh':
            self.energy = 3600 * invar
        elif unit == 'kWh':
            self.energy = 3600000 * invar
        elif unit == 'J':
            self.energy = invar # J
        else:
            log.warning('energy not set due to unknown unit '+str(unit))

    def set_el_energy(self, invar, unit = 'J'):
        ''' Sets cumulative CONSUMED ELECTRIC ENERGY, update before cop reading! '''
        if unit == 'Wh':
            self.el_energy = 3600 * invar
        elif unit == 'kWh':
            self.el_energy = 3600000 * invar
        elif unit == 'J':
            self.el_energy = invar # J
        else:
            log.warning('el_energy not set due to unknown unit '+str(unit))

    def get_energy(self):
        ''' Returns flow rate for pump based on actual flowmeter pulse processing '''
        return self.energy # produced J

        
    def get_el_energy(self):
        ''' Returns flow rate for pump based on actual flowmeter pulse processing '''
        return self.el_energy # consumed J

        
    def get_flowrate(self):
        ''' Returns flow rate for pump based on actual flowmeter pulse processing '''
        return self.flowrate

    def get_specificheat(self):
        ''' Returns specific heat of agent (J/(K*kg)) that depends on
        average agent temperature
        '''
        return self.cp

    def output(self, di_pump, Ton, Tret):
        ''' Older use cases without COP - do not use the available COP value! '''
        return output2(Ton, Tret, di1 = di_pump, di2 = 1)
    
    def output2(self, Ton, Tret, di1 = None, di2 = None):
        '''Returns tuple of current power W, 
        cumulative energy J (updated at the next cycle start!)
        and cumulative active time s 
        based on 
        pump state di_pump (0 or 1, where 1 means both compressor and flow active). 
        temperatures Ton, Treturn (temperature of pumped agent in 2 points),
        flowrate and specific heat of the agent (may depend on temperature!).
        
        Result also depends on changing flowrate (update often).
        Execute this at DI polling speed, will skip unnecessary
        recalculatsions during pumping session if interval is not passed
        since last execution.
        
        To get value in Wh divide value in J by 3600.
        
        To calculate COP of the heat pump use energy change of 
        cumulative energy and time (not only working time). 
        Short term COP has to be calculated for previous cycle, avoiding data from current cycle
        (or the result would otherwise heavily depend on query timing within the cycle).
        If however there is no new cycle and both compressor and flow are stopped, this can be informed
        using active (1) di_off signal and then the last cycle value is calculated. This
        value gets updated however during next cycle start, if there has been any change in cumulative energies.
        
        This method updates self.cop in the beginning of each new cycle start or @ di_off.
        To get the COP value, use get_cop()!        
        '''
        if self.threshold == None or (di1 == None and di2 == None):
            log.warning('no cop calc due to no syncing infomation - threshold or di1 and di2')
            self.cop = None
            
        # average specific heat based on onflow nand return temperatures
        tsnow = time.time()
        Tdiff = Ton - Tret
        # interpolated specific energy for heat agent based on
        # average temperature
        self.cp = self.interpolate((Ton + Tret)/2.0, self.tp1, self.cp1,
                                                   self.tp2, self.cp2)
        #cycle start (or end if no new start coming) must be detected
        if di_pump != self.di_pump: # pump state changed
            self.di_pump = di_pump
            if self.di_pump == 1: # start
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
                if (tsnow > self.ts_start + self.interval or
                        Tdiff > 1.5 * self.Tdiff or
                        Tdiff < 0.5 * self.Tdiff):
                    # do not recalculate too often during pumping, 
                    # there will be to many small pieces added up
                    self.power = self.flowrate * Tdiff * self.cp
                    self.energy += (tsnow - self.ts_start) * self.power
                    self.ptime += (tsnow - self.ts_start)
                    self.ts_start = tsnow
                    self.Tdiff = Tdiff
            else:
                self.power = 0

        log.debug('flowrate = %d, Ton = %d, Tret = %d',
                  self.flowrate, Ton, Tret)
        return self.power, self.energy, self.ptime # W J s


    def get_cop(self):
        ''' Returns COP based on last heat pump cycle, from start to start or from start to cop_timeout.
        Should return None if the last cycle has ended for more than cop_timeout s ago. 
        The timing for calculation is set by output(), thus output must be called frequently. '''
        
        return self.cop

    
    def set_cop(self, cop = None):
        ''' Sets former COP values, last and avg '''
        if cop != None:
            self.cop = cop # no need for average over cumulative, see charts#
                    
    
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


#class COP(HeatEcxhange):
#    ''' Returns heat pump COP based on time and energy. HeatExchange variables usable? '''
#    def __init__(self, active, passive = 0):
        
            