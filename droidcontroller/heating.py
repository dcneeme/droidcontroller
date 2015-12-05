# room heating control with possibly several water heating loops in the room. neeme 2015
#  class Cooler may be added....

from droidcontroller.util_n import UN # for val2int()
from droidcontroller.pid import *
from droidcontroller.it5888pwm import *

import traceback, logging
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

class Heater(object): # Junkers Euromaxx for now.
    ''' Controlling the water temperature from the heater and the onflow temperature to the floor loops '''
    def __init__(self, d, ac, svc_hmode='GSW', svc_Gtemp='TGW',svc_Htemp='THW',
            svc_P='KGPW', svc_I='KGIW', svc_D='KGDW',
            svc_pwm='PWW', svc_Gdebug='LGGW', svc_Hdebug='LGHW', svc_noint='NGIW',
            chn_gas=0, chn_onfloor=1):  # pwm chn 0 or 1

        self.pwm_gas = [] # 0 onfloor , 1 hot
        self.pwm_gas.append(IT5888pwm(d, mbi = 0, mba = 1, name='hot water pwm control', period = 1000, bits = [13])) # do6, nupupinge regul, limits from svc
        self.pwm_gas.append(IT5888pwm(d, mbi = 0, mba = 1, name='floor_onTemp pwm control', period = 1000, bits = [14])) # do7, termostaadi kyte
        self.svc_hmode = svc_hmode
        self.svc_Gtemp = svc_Gtemp
        self.svc_Htemp = svc_Htemp
        self.svc_P = svc_P
        self.svc_I = svc_I
        self.svc_D = svc_D
        self.svc_pwm = svc_pwm
        self.svc_Gdebug = svc_Gdebug
        self.svc_Hdebug = svc_Hdebug
        self.svc_noint = svc_noint

        self.pid_gas = []
        self.pid_gas.append(PID(P=0.5, I=0.05, D=0, min=5, max=995, name = 'gasheater watertemp pwm setpoint'))
        self.pid_gas.append(PID(P=0.5, I=0.05, D=0, min=5, max=995, name = 'flooron watertemp pwm setpoint'))
        self.tempvarsG = None
        self.tempvarsH = None
        self.pwm_values = [None, None]
        self.d = d # binary channels modbus
        self.ac = ac # ai modbus

        self.aisvcs = {} # services dict ai
        self.aisvcs.update({svc_Gtemp : None }) # water from gasheater - [actual on, actual ret, setpoint, hilim]
        self.aisvcs.update({svc_Htemp : None }) # water from gasheater - [actual on, actual ret, setpoint, hilim]
        self.aisvcs.update({svc_P : None }) # kP for loops G, H
        self.aisvcs.update({svc_I : None }) # kI for loops G, H
        self.aisvcs.update({svc_D : None }) # kD for loops G, H

        self.aosvcs = {} # services dict ao
        self.aosvcs.update({svc_pwm : None }) # pwm control
        self.aosvcs.update({svc_Gdebug : None }) # ext int stop G
        self.aosvcs.update({svc_Hdebug : None }) # ext int stop H

        self.disvcs = {} # services dict di
        self.disvcs.update({svc_hmode : None }) # heating mode [flame, heating]

        self.dosvcs = {} # services dict do
        self.dosvcs.update({svc_noint : None })

    def read_svcs(self):
        ''' read the cvs tables to get heating related input data '''
        for svc in self.aisvcs:
            #log.info('trying aisvcs update with '+svc)
            self.aisvcs.update({ svc : self.ac.get_aivalues(svc) })
            log.info('aisvcs update '+svc+':'+str(self.aisvcs[svc]))

        for svc in self.disvcs:
            #log.info('trying disvcs update with '+svc)
            self.disvcs.update({ svc : self.d.get_divalues(svc) })
            log.info('disvcs update '+svc+':'+str(self.disvcs[svc]))


    def write_svcs(self):
        ''' writes the sql svc tables with values to monitor AND pwm channels '''
        self.pwm_gas[0].set_value(13, self.pwm_values[0]) # pwm to heater knob, do bit 13
        self.pwm_gas[1].set_value(14, self.pwm_values[1]) # pwm to 3way valve, do bit 14
        self.ac.set_aivalues(self.svc_pwm, values = self.pwm_values)
        if self.tempvarsG != None:
            self.ac.set_aivalues(self.svc_Gdebug, values=[UN.val2int(self.tempvarsG['error'],10),
                    UN.val2int(self.tempvarsG['outP'],10), UN.val2int(self.tempvarsG['outI'],10),
                    UN.val2int(self.tempvarsG['outD'],10) ]) # out comp x 10 for loop 0
        if self.tempvarsG != None:
            self.ac.set_aivalues(self.svc_Hdebug, values=[UN.val2int(self.tempvarsH['error'],10),
                    UN.val2int(self.tempvarsH['outP'],10), UN.val2int(self.tempvarsH['outI'],10),
                    UN.val2int(self.tempvarsH['outD'],10) ]) # PID comp x 10 for loop 1


    def output(self):
        ''' CONTROLS HEATING WATER TEMPERATURE FROM GAS HEATER AND MIX VALVE TO FLOOR. also pump speed.
            setpoints to heater out and floor onflow are taken from the services TGW[2] and THW[2]
            and may depend on outdoor temperature or just demand from the floor (other loops for these valvee)
        '''
        log.info('heating output start')
        try:
            #noint = -(self.GSW[0] ^ 1) # inversion. no down integration during non-heating
            tmp = self.disvcs[self.svc_hmode] # GSW
            if tmp != None:
                noint = -((tmp[1]) ^ 1) # inversion. no down integration during non-heating
            else:
                noint = 1 # valid for both heater pid loops
                log.warning('set noint to 1 due to no valid GSW value yet, '+str(tmp))

            if noint != 0:
                log.info('down int forbidden for gasheater loops based on GSW '+str(tmp)+', noint '+str(noint))
            else: ##
                log.info('int allowed for gasheater loops based on GSW '+str(tmp)+', noint '+str(noint)) ##

            self.read_svcs() # refresh TGW, THW, KPPW, KGIW, KGDW values

            #############
            try: # pwm values generation using pid instances
                self.pwm_values = [ UN.val2int(self.pid_gas[0].output(self.aisvcs[self.svc_Gtemp][2], self.aisvcs[self.svc_Gtemp][0], noint=noint)),
                                UN.val2int(self.pid_gas[1].output(self.aisvcs[self.svc_Htemp][2], self.aisvcs[self.svc_Htemp][0], noint=noint)) ]
            except:
                log.warning('PID FAILURE!')
                traceback.print_exc()
            #############

            self.write_svcs()  # outputs setting, incl pwm

            self.tempvarsG = self.pid_gas[0].getvars() # dict based on pid variables
            self.tempvarsH = self.pid_gas[1].getvars() # dict bnased on pid variables
            '''
            {'Kp' : self.Kp, \
            'Ki' : self.Ki, \
            'Kd' : self.Kd, \
            'outMin' : self.outMin, \
            'outMax' : self.outMax, \
            'outP' : self.Cp, \
            'outI' : self.Ki * self.Ci, \
            'outD' : self.Kd * self.Cd, \
            'setpoint' : self.setPoint, \
            'onlimit' : self.onLimit, \
            'error' : self.error, \
            'actual' : self.actual, \
            'out' : self.out, \
            'extnoint' : self.extnoint, \
            'name': self.name }
            '''
            print('tempvarsG',self.tempvarsG) # debug
            print('tempvarsH',self.tempvarsH) # debug


            if UN.val2int(self.tempvarsG['outMax']) != self.TGW[3]:
                self.pid_gas[0].setMax(self.TGW[3])
                log.warning('pid_gas[0] hilim changed to '+str(self.TGW[3]))
            if UN.val2int(self.tempvarsG['Kp'],10) != self.KGPW[0]:
                self.pid_gas[0].setKp(self.KGPW[0] / 10.0)
                log.warning('pid_gas[0] kP changed!')
            if UN.val2int(self.tempvarsG['Ki'],1000) != self.KGIW[0]:
                self.pid_gas[0].setKi(self.KGIW[0] / 1000.0)
                log.warning('pid_gas[0] kI changed!')
            if UN.val2int(self.tempvarsG['Kd']) != self.KGDW[0]:
                self.pid_gas[0].setKd(self.KGDW[0])
                log.warning('pid_gas[0] kD changed to '+str(self.KGDW[0]))

            if UN.val2int(self.tempvarsH['outMax']) != self.THW[3]:
                self.pid_gas[1].setMax(self.THW[3])
                log.warning('pid_gas[1] hilim changed to '+str(self.THW[3]))
            if UN.val2int(self.tempvarsH['Kp'], 10) != self.KGPW[1]:
                self.pid_gas[1].setKp(self.KGPW[1] / 10.0)
                log.warning('pid_gas[1] kP changed!')
            if UN.val2int(self.tempvarsH['Ki'], 1000) != self.KGIW[1]:
                self.pid_gas[1].setKi(KGIW[1] / 1000.0)
                log.warning('pid_gas[1] kI changed!')
            if UN.val2int(self.tempvarsH['Kd']) != self.KGDW[1]:
                self.pid_gas[1].setKd(self.KGDW[1])
                log.warning('pid_gas[1] kD changed to '+str(self.KGDW[1]))

            log.info('gas_heater done, noint '+str(noint)+', new pwm values '+str(self.pwm_values))
        except:
            log.warning('gasheater control PROBLEM')
            traceback.print_exc()



class RoomTemperature(object):
    ''' Controls room air temperature using floor loops with shared setpoint temperature '''
    def __init__(self, act_svc, set_svc, floorloops, name='undefined'): # floorloops is list of tuples [(in_ret_temp_svc, mbi, mba, reg, bit)]
        #self.act_svc = act_svc if 'list' in str(type(act_svc)) else None # ['svc', member]
        #self.set_svc = set_svc if 'list' in str(type(set_svc)) else None # ['svc', member]
        self.pid2floor = pid(PID(P=1.0, I=0.01, min=100, max=350, outmode='nolist', name='room '+name, dead_time=0))
        self.f = [] # floor loops
        for i in len(floorloops):
            self.f.append(FloorLoop(floorloops[i][0]))

    def doall(self, roomsetpoint):
        ''' Tries to set shared setpoint to floor loops in order to maintain the temperature in the room '''
        setfloor = self.pid2floor(ac.get(act_svc), ac.get(act_svc)) # ddeg



class FloorTemperature(object):
    def __init__(self, act_svc, set_svc, out_mbi = 0, out_mba = 1, out_bit = 8, name = 'undefined', period=1000, phasedelay = 0, lolim = 150, hilim = 350): # time units s, temp ddegC
        ''' floor loops with slow pid and pwm period 1h, use shifted phase to load pump more evenly.
            The loops know their service and d member to get the setpoint and actuals.
            Limits are generally the same for the floor loops.
            when output() executed, new values for loop controls are calculated.
        '''
        # messagebus? several loops in the same room have to listen the same setpoint
        self.lolim = lolim
        self.hilim = hilim
        self.period = period # s
        self.phasedelay = phasedelay
        self.act_svc = act_svc if 'list' in str(type(act_svc)) else None # ['svc', member]
        self.set_svc = set_svc if 'list' in str(type(set_svc)) else None # ['svc', member]
        self.pid = pid(PID(P = 1.0, I = 0.01, D = 0, min = 100, max = 900, outmode = 'nolist', name='floor_loop '+name, dead_time = 0))

    def input(self):
        ''' read input values for output '''
        try:
            actual = self.ac.get_aivalue(self.act_svc[0], self.act_svc[1]) # svc, member
            setpoint = self.ac.get_aivalue(self.set_svc[0], self.set_svc[1])
            return actual, setpoint
        except:
            traceback.print_exc()
            return None

    def output(self, act_set): # tuple from input()
        ''' used pid and decide what to store into output. store too! '''
        self.pid.output
        return 0

    def doall(self):
        ''' check input snd write channel output '''
        res = self.input()
        if res != None and len(res) == 2:
            res = res | self.output()
            return res
        else:
            return 1

