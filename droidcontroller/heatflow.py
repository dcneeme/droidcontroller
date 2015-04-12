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

    to get COP value use self.energylast in J divided by el en  consum inc since last cycle stop!
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
        self.ts_last = 0
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
                        self.ts_last = tsnow
                        self.pstate = 1
                        #self.avg = 1 # average on first pulse interval
                    else:
                        if tsnow > self.ts_last and self.ts_last != 0:
                            # update on every pulse
                            flowrate = self.litres_per_pulse / (tsnow - self.ts_last)
                            # count again for each pulse
                            self.ts_last = tsnow
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
        
        To enable COP calculation externally the energy produced during last cycle is kept up too. 
        '''
            
        # average specific heat based on onflow and return temperatures
        tsnow = time.time()
        ts_diff = tsnow - self.ts_last
        Tdiff = Ton - Tret
        ##print('timediff', ts_diff, 'tempdiff', Tdiff)
        # interpolated specific energy for heat agent based on
        # average temperature for agent, has effect on specific heat
        self.cp = self.interpolate((Ton + Tret)/2.0, self.tp1, self.cp1,
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
                energydelta = ts_diff * Tdiff * self.flowrate * self.cp
                self.energy += energydelta
                self.energycycle += energydelta # last pumping cycle
                self.energylast = self.energycycle
                self.ptime += ts_diff
                self.power = 0
                if Tdiff > 0: # energypos increase
                    self.energypos += energydelta
                elif Tdiff < 0:
                    self.energyneg -= energydelta # value positive, meaning negative
                log.info('heat pump cycle stopped, produced energy during cycle J '+str(round(self.energylast)))
                

            ##self.Tdiff = Tdiff
        else: # no chg in pump state
            if di_pump == 1: # PUMPING
                #if (ts_diff > self.interval or
                #        Tdiff > 1.5 * self.Tdiff or
                #        Tdiff < 0.5 * self.Tdiff):
                self.power = self.flowrate * Tdiff * self.cp
                energydelta = ts_diff * self.power
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
        return self.power, self.energy, self.ptime, self.energypos, self.energyneg # W J s J J 
        # last two are for separating the produced heat (energypos) from the production loss for heat pump melting (energyneg)


    def get_energylast(self):
        ''' Returns summary energy from last cycle generatred by output(), use for COP calc '''
        return self.energylast # J

    
    def set_energypos(self, invar):
        ''' Restores produced positive heat '''
        if invar != None:
            self.energypos = invar # produced useful heat, excluding melting energy
                    
    def set_energyneg(self, invar):
        ''' Restores produced melting heat energy '''
        if invar != None:
            self.energyneg = invar # produced useful heat, excluding melting energy
                    
    
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


            