# This Python file uses the following encoding: utf-8

#-------------------------------------------------------------------------------
# PID.py
# A simple implementation of a PID controller and also the threestep motor control
#-------------------------------------------------------------------------------
# Heavily modified PID source from the book "Real-World Instrumentation with Python"
# by J. M. Hughes, published by O'Reilly Media, December 2010,
# ISBN 978-0-596-80956-0.
#-------------------------------------------------------------------------------
# modified and ThreeStep class added by droid4control.com 2014, Neeme Takis
#
# usage example:
# from pid import *
# f=PID(setpoint=20, min=-100, max=100)
# f.output(11)   # returns output, p, i, d, e, onLimit
# or
# f=ThreeStep(setpoint=3)
# print f.output(10)

# last change 3.11.2014 by neeme

# starmanis 5.11.2014 (appd.log failis)
# pid: fixing onLimit value 1 to zero!
# pid: fixing onLimit value -1 to zero!
# OCT 2015  added noint variable to output() in order to fight dead-time reset windup (use this whenever the if inner loop is saturated)
# aug 2016 tuning tests, downspeed added (natural cooling vs active heating)

''' SOOVITUSI
  1. mõõtmisi teosta 20 x kiiremini kui võimalik võnkumisperiood, ja ilma keskmistamata
  2. kaskaadlylituse korral välisesse loopi ainult I, 10 x väiksem, kui sisemises
  3. sisemine häälesta enne, PI, PID on ebatäpse mõõtmisega igal juhul jama.
  4. välise loobi aktiveerimisel vahenda sisemise loobi Kp, Ki 10..20%. Kd kõigil alati 0!

  häälestamiseks Ki=0, Kd=0. suurenda Kp kuni vongub. registreeri periood Tu s, Ku=Kp
  PI jaoks optimaalne Kp=Ku*0.45, Ki=1.2*Ku/Tu

'''

import time
import logging
log = logging.getLogger(__name__)

class PID:
    ''' Simple PID control.
        This class implements a simplistic PID control algorithm
    '''

    def __init__(self, setpoint = 0, P = 1.0, I = 0.01, D = 0.0, min = 5, max = 995, outmode = 'nolist', name='undefined', dead_time = 0, inv=False, downspeed=1):
        ''' if outmode = 'list', then extra data is returned from output().
         min and max are required for normal operation!
         downspeed is used to multiply Ki, Ki, Kd in out calc if da<0, to enable asymmetry (fast heating, slow cooling for example)
        '''
        self.outmode = outmode # remove later, temporary help to keep list output for some installations
        self.error = 0
        self.inv = inv # inversion if True (negate error)
        self.name = name
        self.vars = {} # to be returned with almost all internal variables
        self.tsLimit = 0 # timestamp of reaching the saturation
        self.actual = None
        self.out = None
        self.outMin = min # min allowed output
        self.outMax = max # max allowed output
        self.setSetpoint(setpoint) # this value will be compared to output() parameter to produce output value
        self.setKp(P)
        self.setKi(I)
        self.setKd(D)
        self.setMin(min) # minimum allowed output value
        self.setMax(max) # maximum allowed output value
        self.setName(name)
        self.dead_time = dead_time # time for reaction start for the controlled object
        self.extnoint = 0 # from outside, on output()
        self.noint = 0 # internal saturation-initiated dead time signal to prevent outer loop integration in one direction
        self.downspeed = downspeed
        self.Initialize()
        #msg=str(self.getvars())
        log.info('PID '+self.name+' init done')


    def set_actual(self, invar):
        if invar != None:
            self.actual = invar
        else:
            log.warning('ignored illegal actual value None! keeping '+str(self.actual))

    def setSetpoint(self, invar):
        ''' Set the goal for the actual value '''
        if invar != None:
            self.setPoint = invar
        else:
            log.warning('ignored illegal setpoint value None! keeping '+str(self.setPoint))

    def getSetpoint(self):
        ''' Returns the setpoint for the actual value to follow '''
        return self.Setpoint

    def get_extnoint(self):
        ''' returns the externally given via output() integration enable flag, usually from innner loop '''
        return self.extnoint

    def setKp(self, invar):
        ''' Sets proportional gain  '''
        if invar != None:
            self.Kp = invar
        else:
            log.warning('ignored illegal Kp value None! keeping '+str(self.Kp))

    def setKi(self, invar):
        ''' Set integral gain and modify integral accordingly to avoid related jumps '''
        try:
            #print('trying to set new setKi '+str(invar)+' while existing Ki='+str(self.Ki)) # debug
            if self.Ki > 0 and invar > 0 and self.Ki != invar:
                log.info('setKi with initialize')
                self.Ki = invar
                #self.Initialize() # enam pole vaja, sest meeles peame integraali Ki ja errori korrutisest  14.8.2016
            else:
                self.Ki = invar
        except:
            self.Ki = invar # no init needed


    def setKd(self, invar):
        ''' Set derivative gain  '''
        if invar != None:
            self.Kd = invar
        else:
            log.warning('ignored illegal Kd value None! keeping '+str(self.Kd))


    def getKp(self):
        ''' Returns proportional gain '''
        return self.Kp


    def getKi(self):
        ''' Returns integral gain '''
        return self.Ki


    def getKd(self):
        ''' Returns derivative gain '''
        return self.Kd


    def getLimit(self):
        ''' Returns the limit state and the saturation age as list. Also asuggestion not to integrate for outer loop id age < deadtime. '''
        noint = 0 # recalculated every time based on age and onLimit
        if self.onLimit != 0:
            age = int(time.time() - self.tsLimit) # limitation age
            if self.dead_time > age:
                noint = self.onLimit
        else:
            age = 0
            noint = 0
        return self.onLimit, age, noint # noint on sama plaarsusega kui onlimit, kehtides deadzone pikkuses


    def getvars(self, filter = None):
        ''' Returns internal variables as dictionary '''
        self.vars.update({'Kp' : self.Kp, \
            'Ki' : self.Ki, \
            'Kd' : self.Kd, \
            'outMin' : self.outMin, \
            'outMax' : self.outMax, \
            'outP' : self.Cp, \
            'outI' : self.Ci, \
            'outD' : self.Cd, \
            'setpoint' : self.setPoint, \
            'onlimit' : self.onLimit, \
            'error' : self.error, \
            'actual' : self.actual, \
            'out' : self.out, \
            'extnoint' : self.extnoint, \
            'name': self.name })
        if filter is None: # return everything
            return self.vars
        else:
            if filter in self.vars:
                return self.vars.get(filter)


    def resetIntegral(self):
        ''' reset integral part  '''
        self.Ci = 0

    def setDeadTime(self, invar):
        '''' Sets the dead time in s. Used to suggest non integration for outer loop '''
        self.dead_time = invar # seconds


    def setPrevErr(self, invar):
        ''' Set previous self.error value    '''
        self.prev_err = invar


    def setMin(self, invar):
        ''' Set lower limit for output    '''
        if invar != None and ('float' in str(type(invar)) or 'int' in str(type(invar))):
            log.info('pid: outMin set to '+str(invar))
            self.outMin = invar
        else:
            log.error('INVALID value for outMin: '+str(invar))

    def getMin(self):
        return self.outMin


    def setMax(self, invar):
        ''' Set upper limit for output    '''
        if invar != None and ('float' in str(type(invar)) or 'int' in str(type(invar))):
            log.info('outMin set to '+str(invar))
            self.outMax = invar
        else:
            log.error('INVALID value for outMax: '+str(invar))


    def getMax(self):
        return self.outMax


    def setName(self, invar):
        ''' Sets the descriptive name for the instance '''
        self.name = invar

    def Initialize(self):
        ''' initialize delta t variables  '''
        self.currtime = time.time()
        self.prevtm = self.currtime
        self.prev_err = 0
        self.onLimit = 0 # value 0 means between limits, -10 on lo limit, 1 on hi limit
        # term result variables
        self.Cp = 0
        if self.Ki >0 and self.outMin != None and self.outMax != None:
            #self.Ci=(2 * self.outMin + self.outMax) / (3 * self.Ki) # to avoid long integration to normal level, set int between outmin and outmax
            self.Ci=(2 * self.outMin + self.outMax) / 3 # to avoid long integration to normal level
            log.info('pid: integral component biased to '+str(round(self.Ci))+' while Ki='+str(self.Ki))
        else:
            self.Ci = 0
        self.Cd = 0
        self.out = None
        log.info(self.name+' pid: initialized')


    def getLimit(self, onlimit=None):
        ''' Returns the limit state and the saturation age as list.
            Also noint as a suggestion not to integrate for outer loop while limitation age < deadtime.
            If noint is finished, then no new noint with the same value during deadzone!
            noint cannot be restarted!
        '''
        if onlimit != None:
            self.onLimit = onlimit # for testing

        age = time.time() - self.tsLimit
        if age > self.dead_time: # time over for noint or noint restart protection
            if self.noint == 0: # no noint currently
                if self.onLimit != 0: # saturated
                    self.noint = self.onLimit
                    self.tsLimit = time.time() # start time
                    log.info('started noint '+str(self.noint)+' for '+self.name)
                else:
                    log.debug('no reason for noint starting...')
            else: # ongoing noint
                if self.noint != 0:
                    self.noint = 0
                    self.tsLimit = time.time() # stop time
                    log.info('stopped noint at age '+str(int(age))+' for '+self.name)
        else:
            if self.noint != 0:
                log.info('noint '+str(self.noint)+' ongoing, age '+str(int(age))+'s for '+self.name)
            else:
                log.info('noint protection time lasting '+str(int(age))+'s ongoing for '+self.name)

        return self.onLimit, age, self.noint # noint on sama plaarsusega kui onlimit, kehtides deadzone pikkuses


    def output(self, actual = None, setpoint = None, noint = 0): # actual and external integration prevention via noint (signed, 1 = no upwards)
        ''' Performs PID computation and returns a control value and it's components (and self.error and saturation)
            based on the elapsed time (dt) and the difference between actual value and setpoint.
            Added oct 2015: noint value other than 0 will stop integration in both directions.

            If actual and/or setpoint is not given, these should be defined and updated via set_actual(), setSetpoint() !
        '''
        if setpoint != None:
            self.setPoint = setpoint # replacing setpoint if given
        if actual != None:
        #    da = actual - self.actual if self.actual != None else 0
            self.actual = actual
        self.extnoint = noint
        direction = ['down','','up'] # up or down / FIXME use enum here! add Limit class! reusable for everybody...
        try:
            self.error = self.setPoint - self.actual            # self.error value  oli invar
            if self.inv:
                self.error = -self.error ## inversion, effect is like swapping act and set
        except:
            self.error = 0 # for the case of invalid actual
            log.warning('invalid actual '+repr(actual)+' for pid '+self.name+' error calculation, error zero used!')

        self.currtime = time.time()               # get t
        dt = self.currtime - self.prevtm          # get delta t
        de = self.error - self.prev_err              # get delta self.error

        self.Cp = self.Kp * self.error  # proportional term. should we take da sign into account?

        if self.Ki > 0:
            if ((self.onLimit == 0 and
                    ((self.extnoint == 0) or
                    (self.extnoint == -1 and self.error > 0) or
                    (self.extnoint == 1 and self.error < 0))) or
                    (self.onLimit == -1 and self.error > 0) or
                    (self.onLimit == 1 and self.error < 0)): # ok to integrate both, up, down
                #integration is only allowed if Ki not zero and no limit reached or when output is moving away from limit
                ##self.Ci += self.error * dt   # integral term
                if self.error > 0: # actual (possibly temperature) is increasing
                    self.Ci += self.error * dt * self.Ki # integral term
                    #print('integration up)
                else:
                    self.Ci += (self.error * dt * self.Ki) * self.downspeed # integral term during passive cooling is smaller
                    #print('integration down or steady, downspeed '+str(self.downspeed))
            else:
                #pass
                log.info(self.name+' integration '+direction[self.onLimit+1]+' forbidden, onLimit '+str(self.onLimit)+', extnoint '+str(self.extnoint)+', dead_time '+str(self.dead_time))

        if dt > 0 and self.out != None:                 # no div by zero
            Cd = 1.0 * self.Kd * de/dt                     # derivative term
            #old_pi = self.out - self.Cd
            #new_pi = self.Cp + self.Ci
            #dpi = new_pi - old_pi
            #Cd = 1.0 * self.Kd * dpi/dt    # derivative term based on P + I, less jumpy than error, more dynamic than actual!
            #print('old_pi '+str(old_pi)+', new_pi '+str(new_pi)+', dpi '+str(dpi)+', Cd '+str(self.Cd))
            if abs(Cd) < (self.outMax - self.outMin): # seems normal
                self.Cd = (Cd + self.Cd) / 2 # averaging to make the differential spikes smoother
            else:
                #self.Cd = 0 # jaagu endine
                log.warning('IGNORED too large Cd '+str(Cd)+', de '+str(de)+', dt '+str(dt)+' above allowed output span')
        else:
            self.Cd = 0


        self.prevtm = self.currtime               # save t for next pass
        self.prev_err = self.error                   # save t-1 self.error

        ##out = self.Cp + (self.Ki * self.Ci) + (self.Kd * self.Cd) # sum the terms and return the result
        out = self.Cp + self.Ci + self.Cd # sum the components

        if self.outMax != None and self.outMin != None:
            if self.outMax < self.outMin or self.outMax == self.outMin: # avoid faulty limits
                log.error(self.name+' illegal outmin, outmax values:'+str(self.outMin)+', '+str(self.outMax))

        if self.outMax != None:
            if out > self.outMax:
                out = self.outMax
                if self.onLimit != 1:
                    self.onLimit = 1 # reached hi limit
                    self.tsLimit = self.currtime
                    log.warning('loop '+self.name+' output reached hi limit '+str(out)+' while set='+str(self.setPoint)+', act='+str(self.actual))


        if self.outMin is not None:
            if out < self.outMin:
                out = self.outMin
                if self.onLimit != -1:
                    self.onLimit = -1 # reached lo limit
                    self.tsLimit = self.currtime
                    log.warning('loop '+self.name+' output reached lo limit '+str(out)+' while set='+str(self.setPoint)+', act='+str(self.actual))

        if self.outMin != None and self.outMax != None: # to be sure about onLimit, double check
            hyst = 0.03 * (self.outMax - self.outMin) # 3 %
            if out > self.outMin + hyst and out < self.outMax - hyst: # lubatud piires
                if self.onLimit != 0:
                    log.warning(self.name+' onLimit value '+str(self.onLimit)+' zeroing! due to out '+str(out)+' while limits '+str(self.outMin)+' - '+str(self.outMax))
                    self.onLimit = 0 # fix possible self.error

        else:
            log.warning('one of the required limits for '+self.name+' missing! outMin '+str(self.outMin)+', outMax '+str(self.outMax))

        if out == self.outMax and self.onLimit == -1: # swapped min/max and onlimit values for some reason?
            log.warning(self.name+' hi out and onlimit values do not match! out='+str(out)+', outMax='+str(self.outMax)+', onlimit='+str(self.onLimit))
            self.onLimit = 1 # fix possible self.error
        elif out == self.outMin and self.onLimit == 1:
            log.warning(self.name+' lo out and onlimit values do not match! out='+str(out)+', outMin='+str(self.outMin)+', onlimit='+str(self.onLimit))
            self.onLimit = -1 # fix possible self.error

        log.debug(self.name+' sp '+str(round(self.setPoint))+', actual '+str(actual)+', out'+str(round(out))+', p '+str(round(self.Cp))+', i '+str(round(self.Ki * self.Ci))+', d '+str(round(self.Kd * self.Cd))+', onlimit'+str(self.onLimit))

        if self.out != None:
            pout = round(out)
        else:
            pout = None
            log.warning('pid out None, possibly due to init')

        self.out = out

        if self.outmode == 'list':
            return pout, round(self.Cp), round(self.Ci), round(self.Cd), round(self.error), self.onLimit, self.extnoint
        else:
            return pout # summary value only




class ThreeStep:
    ''' Three-step motor control.
        Outputs pulse length to run the motor in one or another direction.
        Another pulse may not start before runperiod is over.
        State is usable for level control, output returns pulse length.
        onlimit is active (not zero) if abs(runtime) reaches motortime.
        No output to sstart a new pulse if error is below minerror (usable for dead zone setting).
    '''
    def __init__(self, setpoint = 0, motortime = 100, maxpulse = 10, maxerror = 100, \
            minpulse =1 , minerror = 1, runperiod = 20, outmode = 'nolist', name = 'undefined', dead_time = 0):
        self.outmode = outmode # remove later, temporary help to keep list output for some installations
        self.name = name
        self.error = 0
        self.vars = {} # to be returned with almost all internal variables
        self.state= 0 # level output in parallel to returned by output() length, use with caution (less precise)
        self.actual = None
        self.out = None
        self.setSetpoint(setpoint)
        self.setMotorTime(motortime)
        self.setMaxpulseLength(maxpulse)
        self.setMaxpulseError(maxerror)
        self.setMinpulseLength(minpulse)
        self.setMinpulseError(minerror)
        self.setRunPeriod(runperiod)
        self.setName(name)
        self.dead_time = dead_time # not used here yet
        self.Initialize()


    def getvars(self, filter = None):
        ''' Returns internal variables as dictionary '''
        self.vars.update({'motortime' : self.MotorTime,  \
            'setpoint' : self.Setpoint, \
            'state' : self.state, \
            'onlimit' : self.onLimit, \
            'runtime' : self.runtime, \
            'MinpulseError' : self.MinpulseError, \
            'MaxpulseError' : self.MaxpulseError, \
            'MinpulseLength' : self.MinpulseLength, \
            'RunPeriod' : self.RunPeriod, \
            'error' : self.error, \
            'actual' : self.actual, \
            'out' : self.out, \
            'name': self.name })
        if filter is None:
            return self.vars
        else:
            if filter in self.vars:
                return self.vars.get(filter)


    def setSetpoint(self, invar):
        """ Set the setpoint for the actual value to follow """
        self.Setpoint = invar


    def setDeadTime(self, invar):
        '''' Sets the dead time in s. Used to suggest non integration for outer loop '''
        self.dead_time = invar # seconds

    def getSetpoint(self):
        """ Returns the setpoint for the actual value to follow """
        return self.Setpoint


    def setMotorTime(self, invar):
        """ Sets motor running time in seconds to travel from one limit to another
        (give the bigger value if the travel times are different in different directions)
        """
        self.MotorTime = abs(invar)


    def setMaxpulseLength(self, invar):
        """ Sets maximum pulse time in seconds to use """
        self.MaxpulseLength = abs(invar)


    def setMaxpulseError(self, invar):
        """ Ties maximum self.error to maximum pulse length in seconds to use.
        That also defines the 'sensitivity' of the relation between the self.error and the motor reaction
        """
        self.MaxpulseError = abs(invar)


    def setMinpulseLength(self, invar):
        """ Sets minimum pulse length in seconds to use """
        self.MinpulseLength = abs(invar)


    def setMinpulseError(self, invar):
        """ Ties the minimum pulse length to the self.error level. This also sets the dead zone,
        where there is no output (motor run) below this (absolute) value on either direction """
        self.MinpulseError = abs(invar)


    def setRunPeriod(self, invar):
        """ Sets the time for no new pulse to be started """
        self.RunPeriod = abs(invar)

    def setName(self, invar):
        ''' Sets the descriptive name for the instance '''
        self.name = invar

    def Initialize(self):
        """ initialize time dependant variables
        """
        self.currtime = time.time()
        #self.prevtime = self.currtime
        self.last_start = self.currtime # - self.RunPeriod - 1 # this way we are ready to start a new pulse if needed - this is NOT GOOD! better wait.
        self.last_length = 0 # positive or negative value means signal to start pulse with given length in seconds. 0 means no pulse start
        #self.last_state = 0 # +1 or -1 value means signal to start pulse with given length in seconds
        self.last_limit = 0 # value 0 for means travel position between limits, +1 on hi limit, -1 on lo limit
        self.runtime = 0 # cumulative runtime towards up - low
        self.onLimit = 0
        self.tsLimit = 0 # timestamp of reaching the saturation


    def interpolate(self, x, x1 = 0, y1 = 0, x2 = 0, y2 = 0):
        """ Returns linearly interpolated value y based on x and
        two known points defined by x1y1 and x2y2
        """
        if x1 == x2:
            log.warning('invalid interpolation attempt')
            # return average in case points have the same x coordinate
            return (y1+y2)/2
        else:
            return y1+(y2-y1)*(x-x1)/(x2-x1)


    def getLimit(self):
        ''' Returns the limit state and the saturation age as list. Also asuggestion not to integrate for outer loop id age < deadtime. '''
        noint = 0
        if self.onLimit != 0:
            age = int(time.time() - self.tsLimit)
            if self.dead_time > age:
                noint = 1
        else:
            age = 0
        return self.onLimit, age, noint


    def set_onlimit(self, invar):
        self.setLimit(invar) # starman main_rescue jaoks ajutine abi


    def setLimit(self, invar):
        ''' Sets the 3step instance into saturated state based on external signal (limit switch for example) '''
        try:
            if invar <2 and invar > -2 and int(invar) != self.onLimit:
                self.onLimit = int(invar)
                if self.onLimit != 0:
                    self.runtime = self.onLimit * self.MotorTime # to keep the limit active and runtime logical
                    self.tsLimit = time.time() # timestamp  of new state begin
                    log.info(self.name+' onlimit set to '+str(self.onLimit))

            else:
                log.debug(self.name+' invalid value for set_onlimit for pid '+self.name+' or no need for state change')
        except:
            log.warning(self.name+' invalid value for set_onlimit for pid '+self.name+': '+str(invar))


    def output(self, invar): # actual as parameter or 3T control
        ''' Performs pulse generation if needed and if no previous pulse is currently active.
        Returns output value for pulse length in s. Other variables available via getvars() as dict.
        All output values can be either positive or negative depending on the direction towards higher or lower limit.
        If self.error gets smaller than minpulse during the nonzero output, zero the output state.
        '''
        self.actual = invar
        try:
            self.error=self.Setpoint - invar            # self.error value
        except:
            self.error = 0 # for the case of invalid actual
            msg=self.name+' invalid actual '+repr(invar)+' for 3step '+self.name+' error calculation, error zero used!'
            log.warning(msg)

        #self.error=self.Setpoint - invar            # current self.error value
        self.currtime = time.time()               # get current time

        #current state, need to stop? level control happens by calling only!
        if self.currtime > self.last_start + abs(self.last_length) and self.state != 0: # need to stop ##########  STOP ##############
            #print('need to stop ongoing pulse due to pulse time (',abs(self.last_length),') s out') # debug
            #if self.onLimit == 0 or (self.onLimit == -1 and self.error > 0) or (self.onLimit == 1 and self.error < 0): # modify running time
            #    self.runtime = self.runtime + self.last_state*(self.currtime - self.last_start) # sign via state is important
            self.state = 0 # stop the run
            #self.last_state = self.state
            log.debug('loop '+self.name+'  stopped pulse, cumulative travel time',round(self.runtime))

        if self.runtime > self.MotorTime: # limit
            self.runtime = self.MotorTime
            if self.onLimit != 1:
                self.onLimit = 1 # reached hi limit
                self.tsLimit = self.currtime
                log.info('loop '+self.name+' reached hi limit') # debug

        if self.runtime < -self.MotorTime: # limit
            self.tsLimit = self.currtime
            if self.onLimit != -1:
                self.onLimit = -1 # reached lo limit
                self.runtime = -self.MotorTime
                log.info('loop'+self.name+' reached lo limit') # debug

        #need to start a new pulse? chk runPeriod
        #if self.currtime > self.last_start + self.RunPeriod and self.last_state == 0: # free to start next pulse (no ongoing)
        if self.currtime > self.last_start + self.RunPeriod and self.state == 0: # free to start next pulse (no ongoing)
            log.debug('no ongoing pulse, time from previous pulse start '+str(int(self.currtime - self.last_start)))
            if abs(self.error) > self.MinpulseError: # pulse is needed
                log.debug('3step: new pulse needed due to self.error vs MinpulseError',self.error,self.MinpulseError)
                if self.error > 0 and self.error > self.MinpulseError: # pulse to run higher needed
                    length = self.interpolate(self.error, self.MinpulseError, self.MinpulseLength, self.MaxpulseError, self.MaxpulseLength)
                    if length > self.MaxpulseLength:
                        length = self.MaxpulseLength
                    self.last_length = length
                    self.last_start = self.currtime
                    self.state = 1

                elif self.error < 0 and self.error < -self.MinpulseError: # pulse to run lower needed
                    length = self.interpolate(self.error, -self.MinpulseError, -self.MinpulseLength, -self.MaxpulseError, -self.MaxpulseLength)
                    if length < -self.MaxpulseLength:
                        length = -self.MaxpulseLength
                    self.last_length = length
                    self.last_start = self.currtime
                    self.state = -1

                log.debug(self.name+': STARTED PULSE w len '+str(length))
                self.runtime = self.runtime+length # new cumulative
            else: # no need for a new pulse
                length = 0

        else: # no new pulse yet or pulse already active
            length = 0
            #self.state = self.last_state
            msg=self.name+' waiting for runperiod end to start a new pulse'
            log.debug(msg)


        #if abs(self.error) < self.MinpulseError and state != 0: # stop the ongoing pulse - not strictly needed, level output hardly in use anyway
        #    state = 0 # if the actual drive to the motor happens via timer controlled by length previously output, this does not have any effect
        #    print('stopped the ongoing pulse') # debug

        pulseleft=int(self.last_start + abs(self.last_length) - self.currtime)
        if self.state != 0 and pulseleft > 0:
            log.debug(self.name+' ongoing pulse time left '+str(pulseleft)+', state (direction) '+str(self.state))

        msg=self.name+' error '+str(round(self.error))+', minpulseError '+str(self.MinpulseError)+', maxpulseError '+str(self.MaxpulseError)+', LENGTH '+str(round(length))+', minpulse '+str(self.MinpulseLength)+', maxpulse '+str(self.MaxpulseLength) # debug
        log.debug(msg)

        self.out = length
        if self.outmode == 'list':
            return length, self.state, self.onLimit, int(self.runtime)
        else:
            return length # this will be the only way

        #END