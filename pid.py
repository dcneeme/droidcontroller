#-------------------------------------------------------------------------------
# PID.py
# A simple implementation of a PID controller and also the threestep motor control
#-------------------------------------------------------------------------------
# Heavily modified PID source from the book "Real-World Instrumentation with Python"
# by J. M. Hughes, published by O'Reilly Media, December 2010,
# ISBN 978-0-596-80956-0.
#-------------------------------------------------------------------------------
# modified and ThreeStep class added by droid4control.com 2014
#
# usage example:
# from pid import *
# f=PID(setpoint=20, min=-100, max=100)
# f.output(11)   # returns output, p, i, d, e, onLimit
# or
# f=ThreeStep(setpoint=3)
# print f.output(10) 

# last change 02.03.2014 by neeme

import time

class PID:
    """ Simple PID control.
        This class implements a simplistic PID control algorithm.
    """
    def __init__(self, setpoint = 0, P = 1.0, I = 0.01, D = 0.0, min = None, max = None): # initialize gains
        self.setSetpoint(setpoint)
        self.setKp(P)
        self.setKi(I)
        self.setKd(D)
        self.setMin(min)
        self.setMax(max)
        self.Initialize()

    def setSetpoint(self, invar):
        """ Set the goal for the actual value """
        self.setPoint = invar

    def setKp(self, invar):
        """ Sets proportional gain  """
        self.Kp = invar

    def setKi(self, invar):
        """ Set integral gain and modify integral accordingly to avoid related jumps """
        try:
            #print('trying to set new setKi '+str(invar)+' while existing Ki='+str(self.Ki)) # debug
            if self.Ki > 0 and invar > 0 and self.Ki != invar:
                print('setKi with initialize')
                self.Ki = invar
                self.Initialize()
            else:
                self.Ki = invar
        except:
            self.Ki = invar
            

    def resetIntegral(self):
        """ reset integral part   """
        self.Ci = 0

    def setKd(self, invar):
        """ Set derivative gain   """
        self.Kd = invar

    def setPrevErr(self, invar):
        """ Set previous error value    """
        self.prev_err = invar

    def setMin(self, invar):
        """ Set lower limit for output    """
        try:
            #print('pid: trying to set new outMin '+str(invar)+' while outMax='+str(self.outMax)) # debug
            if self.Ki > 0 and invar != None  and self.outMin != invar:
                print('pid: setMin with initialize')
                self.outMin = invar
                self.Initialize()
            else:
                self.outMin = invar
        except:
            self.outMin = invar

    def setMax(self, invar):
        """ Set upper limit for output     """
        try:
            #print('pid: trying to set new outMax '+str(invar)+' while outMin='+str(self.outMin)) # debug
            if self.Ki > 0 and invar != None  and self.outMax != invar:
                print('pid: setMax with initialize')
                self.outMax = invar
                self.Initialize()
            else:
                self.outMax = invar
        except:
            self.outMax = invar


    def Initialize(self):
        """ initialize delta t variables   """
        self.currtm = time.time()
        self.prevtm = self.currtm
        self.prev_err = 0
        self.onLimit = 0 # value 0 means between limits, -10 on lo limit, 1 on hi limit
        # term result variables
        self.Cp = 0
        if self.Ki >0 and self.outMin != None and self.outMax != None:
            self.Ci=(2 * self.outMin + self.outMax) / (3 * self.Ki) # to avoid long integration to normal level, set int between outmin and outmax
            print('pid: integral biased to '+str(round(self.Ci))+' while Ki='+str(self.Ki))
        else:
            self.Ci = 0
        self.Cd = 0
        print('pid: initialized')

    def output(self, invar):
        """ Performs a PID computation and returns a control value based on
            the elapsed time (dt) and the difference between actual value and setpoint.
        """
        dir=['down','','up'] # up or down 
        try:
            error=self.setPoint - invar            # error value
        except:
            error=0 # for the case of invalid actual
            msg='invalid actual '+repr(invar)+' for pid error calculation, error zero used!'
            
        self.currtm = time.time()               # get t
        dt = self.currtm - self.prevtm          # get delta t
        de = error - self.prev_err              # get delta error

        self.Cp = self.Kp * error               # proportional term
        if self.Ki > 0:
            if (self.onLimit == 0 or (self.onLimit == -1 and error > 0) or (self.onLimit == 1 and error < 0)):
                #integration is only allowed if Ki not zero and no limit reached or when output is moving away from limit
                self.onLimit = 0
                self.Ci += error * dt                   # integral term
                #print('pid: integration done, new Ci='+str(round(self.Ci)))
            else: 
                pass
                print('pid: integration '+dir[self.onLimit+1]+' forbidden due to saturation, onLimit '+str(self.onLimit)+', error '+str(error)) # debug

        self.Cd = 0
        if dt > 0:                              # no div by zero
            self.Cd = de/dt                     # derivative term

        self.prevtm = self.currtm               # save t for next pass
        self.prev_err = error                   # save t-1 error

        out=self.Cp + (self.Ki * self.Ci) + (self.Kd * self.Cd) # sum the terms and return the result
        
        if self.outMax is not None and self.outMin is not None:
            if not self.outMax > self.outMin: # avoid faulty limits
                print('pid: illegal outmin, outmax values:',self.outMin,self.outMax) # important notice!
        
        if self.outMax is not None:
            if out > self.outMax:
                self.onLimit = 1 # reached hi limit
                out = self.outMax
                
        if self.outMin is not None:
            if out < self.outMin:
                self.onLimit = -1 # reached lo limit
                out = self.outMin
        
        if self.outMin is not None and self.outMax is not None: # to be sure about onLimit, double check
            if out > self.outMin and out < self.outMax:
                if self.onLimit != 0:
                    print('pid: fixing onLimit error value '+str(self.onLimit)+' to zero!') 
                    self.onLimit = 0 # fix possible error
        
        if out == self.outMax and self.onLimit == -1: # swapped min/max and onlimit values for some reason?
            print('pid: hi out and onlimit values do not match! out',out,', outMin',self.outMin,', outMax',self.outMax,', onlimit',self.onLimit) 
            #self.onLimit = 1 # fix possible error
        elif out == self.outMin and self.onLimit == 1:
            print('pid: lo out and onlimit values do not match! out',out,', outMin',self.outMin,', outMax',self.outMax,', onlimit',self.onLimit) 
            #self.onLimit = -1 # fix possible error
        
        print('pid sp',round(self.setPoint),', actual',invar,', out',round(out),', p i d',round(self.Cp), round(self.Ki * self.Ci), round(self.Kd * self.Cd),', onlimit',self.onLimit) # debug
        return out, self.Cp, (self.Ki * self.Ci), (self.Kd * self.Cd), error, self.onLimit


class ThreeStep:
    """ Three-step motor control.
        Outputs pulse length to run the motor in one or another direction
    """
    def __init__(self, setpoint = 0, motortime = 100, maxpulse = 10, maxerror = 100, minpulse =1 , minerror = 1, runperiod = 20):
        self.setSetpoint(setpoint)
        self.setMotorTime(motortime)
        self.setMaxpulseLength(maxpulse)
        self.setMaxpulseError(maxerror)
        self.setMinpulseLength(minpulse)
        self.setMinpulseError(minerror)
        self.setRunPeriod(runperiod)
        self.Initialize() 
        
        
    def setSetpoint(self, invar):
        """ Set the setpoint for the actual value """
        self.Setpoint = invar

    def setMotorTime(self, invar):
        """ Sets motor running time in seconds to travel from one limit to another 
        (give the bigger value if the travel times are different in different directions)
        """
        self.MotorTime = abs(invar)

    def setMaxpulseLength(self, invar):
        """ Sets maximum pulse time in seconds to use """
        self.MaxpulseLength = abs(invar)
    
    def setMaxpulseError(self, invar):
        """ Ties maximum error to maximum pulse length in seconds to use. 
        That also defines the 'sensitivity' of the relation between the error and the motor reaction      
        """
        self.MaxpulseError = abs(invar)
        
    def setMinpulseLength(self, invar):
        """ Sets minimum pulse length in seconds to use """
        self.MinpulseLength = abs(invar)
        
    def setMinpulseError(self, invar):
        """ Ties the minimum pulse length to the error level. This also sets the dead zone, 
        where there is no output (motor run) below this (absolute) value on either direction """
        self.MinpulseError = abs(invar) 
        
    def setRunPeriod(self, invar):
        """ Sets the time for no new pulse to be started """
        self.RunPeriod = abs(invar) 
        
    
    def Initialize(self):
        """ initialize time dependant variables
        """
        self.currtime = time.time()
        #self.prevtime = self.currtime
        self.last_start = self.currtime # - self.RunPeriod - 1 # this way we are ready to start a new pulse if needed - this is NOT GOOD! better wait.
        self.last_length = 0 # positive or negative value means signal to start pulse with given length in seconds. 0 means no pulse start
        self.last_state = 0 # +1 or -1 value means signal to start pulse with given length in seconds
        self.last_limit = 0 # value 0 for means travel position between limits, +1 on hi limit, -1 on lo limit
        self.runtime = 0 # cumulative runtime towards up - low
        self.onLimit = 0
        

    def interpolate(self, x, x1 = 0, y1 = 0, x2 = 0, y2 = 0):
        """ Returns linearly interpolated value y based on x and two known points defined by x1y1 and x2y2 """ 
        if y1 != y2: # valid data to avoid division by zero
            return y1+(x-x1)*(y2-y1)/(x2-x1)
        else:
            return None
            
            
    def output(self, invar): # actual as parameter
        """ Performs pulse generation if needed and if no previous pulse is currently active.
        Returns output values for pulse length, running state and reaching the travel limit. 
        All output values can be either positive or negative depending on the direction towards higher or lower limit.
        If error gets smaller than minpulse during the nonzero output, zero the output state.
        """
        try:
            error=self.Setpoint - invar            # error value
        except:
            error=0 # for the case of invalid actual
            msg='invalid actual '+repr(invar)+' for 3step error calculation, error zero used!'
            print(msg)
            
        #error=self.Setpoint - invar            # current error value
        self.currtime = time.time()               # get current time
        state=0 # pulse level, not known yet
        
        #current state, need to stop? level control happens by calling only!
        if self.currtime > self.last_start + abs(self.last_length) and self.last_state != 0: # need to stop ##########  STOP ##############
            #print('need to stop ongoing pulse due to pulse time (',abs(self.last_length),') s out') # debug
            #if self.onLimit == 0 or (self.onLimit == -1 and error > 0) or (self.onLimit == 1 and error < 0): # modify running time
            #    self.runtime = self.runtime + self.last_state*(self.currtime - self.last_start) # sign via state is important
            state = 0 # stop the run
            self.last_state = state
            print('3step: stopped pulse, cumulative travel time',round(self.runtime))
        
        if self.runtime > self.MotorTime: # limit
            self.onLimit = 1 # reached hi limit
            self.runtime = self.MotorTime
            print('reached hi limit') # debug
            
        if self.runtime < -self.MotorTime: # limit
            self.onLimit = -1 # reached lo limit
            self.runtime = -self.MotorTime
            print('reached lo limit') # debug
                
        #need to start a new pulse? chk runPeriod 
        if self.currtime > self.last_start + self.RunPeriod and self.last_state == 0: # free to start next pulse (no ongoing)
            #print('no ongoing pulse, last_state',self.last_state,'time from previous start',int(self.currtime - self.last_start)) # debug
            if abs(error) > self.MinpulseError: # pulse is needed
                print('3step: new pulse needed due to error vs minpulseerror',error,self.MinpulseError) # debug
                if error > 0 and error > self.MinpulseError: # pulse to run higher needed
                    length = self.interpolate(error, self.MinpulseError, self.MinpulseLength, self.MaxpulseError, self.MaxpulseLength)
                    if length > self.MaxpulseLength:
                        length = self.MaxpulseLength
                    self.last_length = length
                    self.last_start = self.currtime
                    state = 1
                    #print('3step: started pulse w len',round(length)) # debug
                elif error < 0 and error < -self.MinpulseError: # pulse to run lower needed
                    length = self.interpolate(error, -self.MinpulseError, -self.MinpulseLength, -self.MaxpulseError, -self.MaxpulseLength)
                    if length < -self.MaxpulseLength:
                        length = -self.MaxpulseLength
                    self.last_length = length
                    self.last_start = self.currtime
                    state = -1
                print('3step: STARTED PULSE w len '+str(length)) # debug
                self.runtime = self.runtime+length # new cumulative
            else: # no need for a new pulse
                length = 0
                #print('no need for a pulse due to error vs minpulseerror',error,self.MinpulseError) # debug
        else: # no new pulse yet or pulse already active
            length = 0
            state = self.last_state
            msg='3step: pulse last start '+str(int(self.currtime - self.last_start))+' s ago, runperiod '+str(self.RunPeriod)+', cumulative travel time '+str(round(self.runtime)) # debug
            print(msg)
            #syslog(msg) # debug
        
        
        #if abs(error) < self.MinpulseError and state != 0: # stop the ongoing pulse - not strictly needed
        #    state = 0 # if the actual drive to the motor happens via timer controlled by length previously output, this does not have any effect
        #    print('stop the ongoing pulse') # debug
        
        pulseleft=int(self.last_start + abs(self.last_length) - self.currtime)
        if state != 0 and pulseleft > 0:    
            msg='ongoing pulse time left '+str(pulseleft)+', state (direction) '+str(state) # debug
            print(msg)
            #syslog(msg) # debug
        
        
        if state != self.last_state:
            self.last_state = state
        
        msg='3step ERROR '+str(round(error))+', minerror '+str(self.MinpulseError)+', maxerror '+str(self.MaxpulseError)+', LENGTH '+str(round(length))+', minpulse '+str(self.MinpulseLength)+', maxpulse '+str(self.MaxpulseLength) # debug
        print(msg)
        #syslog(msg)
        return length, state, self.onLimit, int(self.runtime)