#-------------------------------------------------------------------------------
# this is a class to simplify io board it5888 pwm usage
# 1 oct 2015 started, neeme
# FIXME  - is dictionary better?

import time
import logging
log = logging.getLogger(__name__)

class IT5888pwm:
    ''' Takes new periodical PWM values and resends them if changed '''

    def __init__(self, mbi = 0, mba = 1, name='IT5888', period = 1000, bits = []):
        self.bits = bits
        self.mbi = mbi
        self.mba = mba
        self.period = period
        self.values = [] # values for bit channels. do1..do8 = bit8..bit15  (reg 108..115)
        for i in range(len(self.bits)):
            self.values.append(None) # initially no change to the existing va;ues in registers
        self.name = name
        self.vars = {} # to be returned with almost all internal variables
        self.period = period # generation starts with value writing
        mb[self.mbi].write(self.mba, 150, self.period) # needs to be resent after io board reset
        log.info('self.__name__ '+self.name+' created')


    def set_value(self, bit, value, periodic = True, phase = 0): 
        ''' Set one channel '''
        chg = 0
        if bit in self.bits:
            if value != self.values[bit]
                self.values[bit] = value + periodic * 0x8000 + (phase << 12)
                mb[self.mbi].write(self.mba, 100 + bit, self.values[bit])
        else:
            log.warning('invalid (not defined in bits) bit '+str(bit)+' used ! bits='+str(self.bits))
        
        if chg == 1: # change, send all
            

    def get_values(self):
        ''' Returns the values list  '''
        return self.values
        
        
    def get_bits(self):
        ''' Returns the channels bist '''
        return self.bits