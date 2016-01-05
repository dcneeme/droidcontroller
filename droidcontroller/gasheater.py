# last change 5.1.2015 neeme
from droidcontroller.util_n import UN # for val2int()
from droidcontroller.pid import *
from droidcontroller.it5888pwm import *

import traceback, logging
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

class JunkersHeater(object): # Junkers Euromaxx  FIXME use msgbus for ai svc!
    ''' 
        Controlling the water temperature from the heater and the onflow temperature to the floor with 2 sets of pid_pwm and pwm_gas loops.
        Could be improved similar to heating.py (setup, avoid direct modbus register usage etc)
    '''
    def __init__(self, d, ac, msgbus, svc_hmode='GSW', svc_Gtemp='TGW',svc_Htemp='THW',
            svc_P='KGPW', svc_I='KGIW', svc_D='KGDW',
            svc_pwm='PWW', svc_Gdebug='LGGW', svc_Hdebug='LGHW', svc_noint='NGIW',
            chn_gas=0, chn_onfloor=1):  # pwm chn 0 or 1. ac svc listened via msgbus

        self.pwm_gas = IT5888pwm(d, mbi = 0, mba = 1, name='gas_heater', period = 1000, bits = [13, 14]) # do6 nupupinge, do7 3Ttermostaat
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

        self.pid = []
        self.pid.append(PID(P=0.5, I=0.05, D=0, min=5, max=995, name = 'hot_out')) # pwm_gas chan 0
        self.pid.append(PID(P=0.5, I=0.05, D=0, min=5, max=995, name = 'floor_on')) # pwm_gas chan 1
        self.tempvarsG = None
        self.tempvarsH = None
        self.pwm_values = [None, None]
        self.d = d # binary channels modbus
        self.ac = ac # ai modbus, temporary, FIXME
        self.msgbus = msgbus
        self.msgbus.subscribe('hot_out', self.svc_Gtemp, 'gas_heater', self.get_actual) # token, subject, message
        self.msgbus.subscribe('floor_on', self.svc_Htemp, 'gas_heater', self.get_actual) # token, subject, message

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
        self.disvcs.update({svc_hmode : [0, 0] }) # heating mode [flame, heating]

        self.dosvcs = {} # services dict do
        self.dosvcs.update({svc_noint : None })


    def get_actual(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.info('from msgbus token %s, subject %s, message %s', token, subject, str(message))
        #self.actual = message['values'][self.act_svc[1]]
        #log.info('new actual to '+self.name+': '+str(self.actual))


    def set_setpoint(self, token, subject, message): # subject is svcname
        ''' from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} '''
        log.info('from msgbus token %s, subject %s, message %s', token, subject, str(message))

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
        self.pwm_gas.set_value(0, self.pwm_values[0]) ## pwm to heater knob, do bit 13
        self.pwm_gas.set_value(1, self.pwm_values[1]) ## pwm to 3way valve, do bit 14
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
        #log.info('heating output start')
        try:
            #noint = -(self.GSW[0] ^ 1) # inversion. no down integration during non-heating
            tmp = self.disvcs[self.svc_hmode] # GSW
            if tmp != None:
                noint = -((tmp[1]) ^ 1) # inversion. no down integration during non-heating
            else:
                noint = 1 # valid for both heater pid loops
                log.warning('set noint to 1 due to no valid GSW value yet, '+str(tmp))

            #if noint != 0:
            #    log.info('down int forbidden for gasheater loops based on GSW '+str(tmp)+', noint '+str(noint))
            #else: ##
            #    log.info('int allowed for gasheater loops based on GSW '+str(tmp)+', noint '+str(noint)) ##

            self.read_svcs() # refresh TGW, THW, KPPW, KGIW, KGDW values

            #############
            try: # pwm values generation using pid instances
                act_g = self.aisvcs[self.svc_Gtemp][2]
                set_g = self.aisvcs[self.svc_Gtemp][0] # setpoint to hot_out
                act_h = self.aisvcs[self.svc_Htemp][2]
                set_h = self.aisvcs[self.svc_Htemp][0] # setpoint for floor_on

                self.pwm_values = [ UN.val2int(self.pid[0].output(act_g, set_g, noint=noint)),
                                    UN.val2int(self.pid[1].output(act_h, set_h, noint=noint)) ]

                log.info('gasheater pid variables g: '+str(self.pid[0].getvars()))
                log.info('gasheater pid variables h: '+str(self.pid[1].getvars()))
                
                log.info('gasheater hot set_g %d, act_g %d, pwm %d, onfloor set_h %d, act_h %d, pwm %d, noint %d' %
                            (set_g, act_g, self.pwm_values[0], set_h, act_h, self.pwm_values[1], noint))
                            
            except:
                log.warning('gasheater pid related FAILURE!')
                traceback.print_exc()
            #############

            self.write_svcs()  # outputs setting, incl pwm

            self.tempvarsG = self.pid[0].getvars() # dict based on pid variables
            self.tempvarsH = self.pid[1].getvars() # dict bnased on pid variables
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
            #print('tempvarsG',self.tempvarsG) # debug
            #print('tempvarsH',self.tempvarsH) # debug


            if UN.val2int(self.tempvarsG['outMax']) != self.aisvcs[self.svc_Gtemp][3]:
                self.pid[0].setMax(self.aisvcs[self.svc_Gtemp][3])
                log.warning('pid[0] hilim changed to '+str(self.aisvcs[self.svc_Gtemp][3]))
            if UN.val2int(self.tempvarsG['Kp'],10) != self.aisvcs[self.svc_P][0]:
                self.pid[0].setKp(self.aisvcs[self.svc_P][0] / 10.0)
                log.warning('pid[0] kP changed to '+str(self.aisvcs[self.svc_P][0]))
            if UN.val2int(self.tempvarsG['Ki'],1000) != self.aisvcs[self.svc_I][0]:
                self.pid[0].setKi(self.aisvcs[self.svc_I][0] / 1000.0)
                log.warning('pid[0] kI changed to '+str(self.aisvcs[self.svc_I][0]))
            if UN.val2int(self.tempvarsG['Kd']) != self.aisvcs[self.svc_D][0]:
                self.pid[0].setKd(self.aisvcs[self.svc_D][0])
                log.warning('pid[0] kD changed to '+str(self.aisvcs[self.svc_D][0]))

            if UN.val2int(self.tempvarsH['outMax']) != self.aisvcs[self.svc_Htemp][3]:
                self.pid[1].setMax(self.aisvcs[self.svc_Htemp][3])
                log.warning('pid[1] hilim changed to '+str(self.aisvcs[self.svc_Htemp][3]))
            if UN.val2int(self.tempvarsH['Kp'], 10) != self.aisvcs[self.svc_P][1]:
                self.pid[1].setKp(self.aisvcs[self.svc_P][1] / 10.0)
                log.warning('pid[1] kP changed to '+str(self.aisvcs[self.svc_P][1]))
            if UN.val2int(self.tempvarsH['Ki'], 1000) != self.aisvcs[self.svc_I][1]:
                self.pid[1].setKi(self.aisvcs[self.svc_I][1] / 1000.0)
                log.warning('pid[1] kI changed to '+str(self.aisvcs[self.svc_I][1]))
            if UN.val2int(self.tempvarsH['Kd']) != self.aisvcs[self.svc_D][1]:
                self.pid[1].setKd(self.aisvcs[self.svc_D][1])
                log.warning('pid[1] kD changed to '+str(self.aisvcs[self.svc_D][1]))

            log.info('gas_heater done, noint '+str(noint)+', new pwm values '+str(self.pwm_values))
        except:
            log.warning('gasheater control PROBLEM')
            traceback.print_exc()


