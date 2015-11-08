#-------------------------------------------------------------------------------
# this is a class to simplify io board it5888 pwm usage
# 1 oct 2015 started, neeme
# FIXME  - is dictionary better?

import time, traceback
import logging
log = logging.getLogger(__name__)

class IT5888pwm(object):
    ''' Takes new periodical PWM values and resends them if changed '''

    def __init__(self, mb, mbi = 0, mba = 1, name='IT5888', period = 1000, bits = [8, 9, 10, 11, 12, 13, 14, 15], phases = None, periodics = None):
        ''' One instance per I/O-module. Define the PWM channels via the bits list. '''
        self.mb = mb
        self.bits = bits # channel list
        self.mbi = mbi # modbus comm instance
        self.mba = mba # modbus address
        self.period = period # ms
        self.periodics = [] # True, False list
        self.phases = [] # 0..3
        self.values = [] # values for bit channels. do1..do8 = bit8..bit15  (reg 108..115)
        for i in range(len(self.bits)):
            self.values.append(None) # initially no change to the existing values in registers
            if phases != None and len(phases) == len(self.bits):
                self.phases = phases # repeating
            else:
                self.phases.append(0) # first phase
            if periodics != None and len(self.bits) == len(periodics): # must be list then
                self.periodics = periodics # kordub aga mis teha
            else:
                self.periodics.append(True) # periodical by default

        self.name = name
        self.period = period # generation starts with value writing
        try:
            res = self.mb[self.mbi].write(self.mba, 150, value=self.period) # needs to be resent after io board reset
            if res == 0:
                log.info(self.name+' successfully created')
            else:
                log.warning(self.name+' possible I/O-problem, could not write into the period register 150 value '+str(self.period))
        except:
            log.warning(self.name+' possible I/O-problem, could not write into the period register 150 value '+str(self.period))
            traceback.print_exc()


    def set_period(self, invar):
        ''' set new period '''
        if invar > 4095:
            invar = 4095
            log.warning(self.name+' limited pwm period to max allowed 4095 s')
        self.period = invar
        log.info(self.name+' new pwm period '+str(self.period)+' s set')


    def set_value(self, bit, value):
        ''' Set one channel to the new PWM value. Will be sent to modbus register if differs from the previous '''
        if value > 4095:
            value = 4095
            log.warning(self.name+' limited pwm value to max allowed 4095')

        try:
            if bit in self.bits:
                gen = (i for i,x in enumerate(self.bits) if x == bit)
                for i in gen: pass # should find one i only if bits correctly!
                if self.values[i] == None or (self.values[i] != None and value != (self.values[i] & 0x0FFF)):
                    self.values[i] = value + self.periodics[i] * 0x8000 + (self.phases[i] << 12)
                    self.mb[self.mbi].write(self.mba, 100 + bit, value=self.values[i])
                    log.info('new pwm value '+str(value)+' set for channel bit '+str(bit)+', phase '+str(self.phases[i])+', periodic '+str(self.periodics[i]))
            else:
                log.warning('invalid (not defined in bits) bit '+str(bit)+' used ! bits='+str(self.bits))
                return 1
            return 0
        except:
            traceback.print_exc()
            return 1


    def set_values(self, values): # full list according to bits
        ''' Set one channel to the new PWM value. Will be sent to modbus register if differs from the previous '''
        chg = 0
        try:
            if len(values) == len(self.bits):
                if values != self.values:  # change
                    self.values = values
                    for i in range(len(self.bits)):
                        self.set_value(self.bit[i], self.value[i])
                log.info('all changed PWM values sent to IO')
            else:
                log.warning('invalid length for values list:'+str(len(values))+', values '+str(values)+', bits '+str(self.bits))
                return 1
            return 0

        except:
            traceback.print_exc()
            return 1


    def get_values(self):
        ''' Returns the value list for bits '''
        return self.values # these contain also periodic and phase information! use (values[i] & 0x0FFF) to see the length


    def get_phases(self):
        ''' Returns the phase list for bits '''
        return self.phases # these contain also periodic and phase information! use (values[i] & 0x0FFF) to see the length


    def get_period(self):
        ''' Returns the period in ms '''
        return self.period # these contain also periodic and phase information! use (values[i] & 0x0FFF) to see the length


    def get_bits(self):
        ''' Returns the channels list '''
        return self.bits