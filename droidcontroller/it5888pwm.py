# This Python file uses the following encoding: utf-8
#-------------------------------------------------------------------------------
# this is a class to simplify io board it5888 pwm usage
# 1 oct 2015 started, neeme
# FIXME  - is dictionary better?

import time, traceback
import logging
log = logging.getLogger(__name__)

class IT5888pwm(object):
    ''' Takes new periodical PWM values and resends them if changed. Use external PID instance for value generation. '''

    def __init__(self, d, mbi=0, mba=1, name='IT5888', period=1000, bits=[8], phases=[0], periodics=[], per_reg=150):
        ''' One instance per I/O-module, as period is shared! Define the PWM channels via the bits list.
            Do not include channels not used in pwm
            The channels in pwm list should not be present in dochannels.sql (trying to sync static values)!
        '''
        self.d = d
        self.bits = bits # channel list
        self.mbi = mbi # modbus comm instance
        self.mba = mba # modbus address
        self.per_reg = per_reg # 150
        self.period = period # ms
        self.periodics = periodics # True, False list
        self.phases = phases # 0..3
        self.values = []
        self.fullvalues = [] # together with phase etc codes for pwm channel
        self.phaseset = False
        # values for bit channels. do1..do8 = bit8..bit15  (reg 108..115)
        for i in range(len(self.bits)):
            self.values.append(None) # initially no change to the existing values in registers
            #self.fullvalues.append(None) # initially no change to the existing values in registers
            self.fullvalues.append(0) # initially
            if len(self.bits) != len(periodics): # must be list then
                self.periodics.append(True) # all periodical by default
        
        self.name = name
        self.period = period # generation starts with value writing
        self.set_phases(phases)
        res = self.fix_period()
       

    def set_phases(self, phases):
        ''' Set the phases list. Used with value sending '''
        if len(phases) == len(self.bits):
            self.phases = phases # repeating
        else:
            self.phases = []
            for i in range(len(self.bits)):
                self.phases.append(0) # first phase
            log.warning('using default phase 0 for bit '+str(self.bits[i]))
        self.phaseset = True
        log.info('phases set to '+str(self.phases))


    def set_period(self, invar):
        ''' set new period '''
        if invar > 4095:
            invar = 4095
            log.warning(self.name+' limited pwm period to max allowed 4095 ms')
        self.period = invar
        log.info(self.name+' new pwm period '+str(self.period)+' ms set')
        self.fix_period()


    def fix_period(self):
        '''  Restores the correct period value in IO register (150) '''
        try:
            if self.d.get_doword(self.mba, self.per_reg, 1, mbi=self.mbi)[0] != (self.period): # << 2): # on some version the period was in .25 ms steps!
                self.d.set_doword(self.mba, self.per_reg, value = self.period, mbi=self.mbi) # restore the period register value in IO
                log.info(self.name+' pwm period fixed to '+str(self.period)+' ms')
        except:
            log.error('failed to communicate with period register '+str(self.per_reg)+' at mbi '+str(self.mbi)+' mba '+str(self.mba))

    def set_value(self, chan, value):# one or all? the same can be shared in some cases...
        ''' Set one or all multiphase channels the new PWM value. Will be sent to register only if it differs from the previous '''
        i = chan # pwm chan index
        if value > 4095:
            value = 4095
            log.warning(self.name+' limited pwm value to max allowed 4095')

        try:
            if chan < len(self.bits): # chan is pwm channel index from this do port
                log.debug(self.name+' pwm chan '+str(chan)) ##
                if self.values[i] == None or (self.values[i] != None and value != (self.fullvalues[i] & 0x0FFF)) or self.phaseset:
                    self.values[i] = value
                    self.fullvalues[i] = int(value + self.periodics[i] * 0x8000+ self.periodics[i] * 0x4000 + (self.phases[i] << 12)) # phase lock needed for periodic...
                    bit = self.bits[chan]  # the separate bit for phase lock seems unnecessary!
                    #self.mb[self.mbi].write(self.mba, 100 + bit, value=self.fullvalues[i])
                    self.d.set_doword(self.mba, 100 + bit, value=self.fullvalues[i], mbi=self.mbi)
                    log.debug(self.name+' new pwm value '+str(value)+', fullvalue '+str(hex(self.fullvalues[i]))+' set for channel '+str(i)+'/ bit '+str(bit)+', phase '+str(self.phases[i])+', periodic '+str(self.periodics[i]))
            else:
                log.error('INVALID '+self.name+' chan'+str(chan)+' / bit '+str(bit)+' used! chan should be < len(bits) '+str(len(self.bits))+', self.bits '+str(self.bits))
                return 1
            return 0
        except:
            log.error('FAILURE in setting pwm value for chan '+str(chan)+', fullvalues '+str(self.fullvalues))
            traceback.print_exc()
            return 1


    def set_values(self, values): # full list according to bits
        ''' Set one channel to the new PWM value. Will be sent to modbus register if differs from the previous '''
        chg = 0
        try:
            if len(values) == len(self.bits):
                if values != self.values or self.phaseset:  # change, refresh need in IO!
                    #self.values = values # tehakse set_value() sees
                    for i in range(len(self.bits)):
                        self.set_value(self.bits[i], values[i])
                log.debug('all changed '+self.name+' PWM values sent to IO')
            else:
                log.warning('invalid length for values list:'+str(len(values))+', values '+str(values)+', bits '+str(self.bits))
                return 1
            return 0

        except:
            traceback.print_exc()
            return 1


    def get_values(self):
        ''' Returns the pwm pulse length value list for bits '''
        return self.values # these contain also periodic and phase information! use (values[i] & 0x0FFF) to see the length

    def get_fullvalues(self):
        ''' Returns the full pwm value list (periodics, phase, length) for bits '''
        return self.fullvalues # these contain also periodic and phase information! use (values[i] & 0x0FFF) to see the length

    def get_phases(self):
        ''' Returns the phase list for bits '''
        return self.phases # these contain also periodic and phase information! use (values[i] & 0x0FFF) to see the length


    def get_period(self):
        ''' Returns the period in ms '''
        return self.period # these contain also periodic and phase information! use (values[i] & 0x0FFF) to see the length


    def get_bits(self):
        ''' Returns the channels list '''
        return self.bits