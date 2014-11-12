#mbys.py - query and process kamstrup and sensus meters via Mbus protocol, 2400 8E1
# usage:
# from mbus import *
# m=Mbus()
# m.read()
# m.get_temperature()


import time
import serial
import traceback
import sys, logging
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
#logging.getLogger('acchannels').setLevel(logging.DEBUG) # yks esile
log = logging.getLogger(__name__)

class Mbus:
    ''' Read various utility meters using Mbus, speed 2400, 8E1   '''

    def __init__(self, port='COM27', tout=3, speed=2400, model='kamstrup602'):  # tout 1 too small!
        self.tout = tout
        self.speed = speed
        self.port = port
        self.model = model
        self.ser = serial.Serial(self.port, self.speed, timeout=tout, parity=serial.PARITY_EVEN) # opening the port
        self.mbm = '' # last message 
        
        
    def set_model(self, invar):
        if invar in ['kamstrup602', 'sensusPE']:
            self.model = invar
            
            
    def get_model(self):
        return self.model
        
    
    def decode(self, invar, key=''):
        ''' Returns decoded value from Mbus binary string self.mbm.
            If key (2 bytes as hex string before data start) is given, 
            then it iwill used for data verification.
        '''
        try:
            res = 0
            for i in range(4):
                res += int(ord(self.mbm[invar + i])) << (i * 8)
            if key != '' and str(key.lower()) != self.mbm[invar-2:invar].encode('hex_codec') and str(key.upper()) != self.mbm[invar-2:invar].encode('hex_codec'):
                log.warning('possible non-matching key '+key+' in key+data '+ self.mbm[invar-2:invar].encode('hex_codec')+' '+self.mbm[invar:invar+4].encode('hex_codec'))
                return None
            else:
                return res
        except:
            traceback.print_exc()
            log.debug('hex string decoding failed')
            return None
            
        
    def read(self):
        ''' Read and keep the answer from the Mbus device '''
        #ser.open()
        self.ser.write('\x10\x7B\xFE\x79\x16') # query to mbus device
        self.mbm = self.ser.read(253) # should be 254 bytes, but the first byte E5 disappears??
        if len(self.mbm) > 0:
            log.debug('got from mbus ' + str(len(self.mbm)) + ' bytes')
            print(self.mbm.encode('hex_codec')) # debug
            return 0
        else:
            log.debug('no answer from mbus device')
            return 1
        
        
    def debug(self, invar = ''):
        ''' Prints out the last response in 4 byte chunks as hex strings,
            shifting the starting byte one by one. 
            Use lower or upper case hex string for searching matches, or lists all.
            DO NOT mix upper and lower case characters though!
        '''
        for i in range(len(self.mbm)):
            if i>4:
                if invar != '':
                    if invar in self.mbm[i:i+4].encode('hex_codec'):
                        print(i, self.mbm[i-2:i].encode('hex_codec'), self.mbm[i:i+4].encode('hex_codec'), self.decode(invar))
                else:
                    print(i, self.mbm[i-2:i].encode('hex_codec'), self.mbm[i:i+4].encode('hex_codec'), self.decode(invar))
        
        
    def get_energy(self):
        ''' Return energy from the last read result. Chk the datetime in self.mbm as well! '''
        key = ''
        coeff = 1 # kwh
        if self.model == 'kamstrup602':
            start = 27 # check with mtools and compare with debug output
            key = '0406' # 2 hex bytes before data, to be sure
        elif self.model == 'sensusPE':
            start = 27
            key = ''
        else:
            log.warning('unknown model '+self.model)
            return None
            
        return self.decode(start, key) * coeff
            
    
    def get_volume(self):
        ''' Return volume from the last read result. Chk the datetime in self.mbm as well! '''
        key = ''
        coeff = 1
        if self.model == 'kamstrup602':
            start = 33
            key = '0414'
            coeff = 10 # l
        elif self.model == 'sensusPE':
            start = 33
        else:
            log.warning('unknown model '+self.model)
            return None
            
        return self.decode(start, key) * coeff
        
        
    def get_power(self):
        ''' Return power from the last read result. Chk the datetime in self.mbm as well! '''
        key= ''
        coeff = 1
        if self.model == 'kamstrup602':
            start = 63
            key = '042d' # use lower or upper case, no difference
            coeff = 100 # W
        elif self.model == 'sensusPE':
            start = 63
        else:
            log.warning('unknown model '+self.model)
            return None
            
        return self.decode(start, key) * coeff
    
    
    def get_temperature(self):
        ''' Return temperature reading extracted from the last read result. Chk the datetime in self.mbm as well! '''
        key =''
        coeff = 1
        divisor = 1
        if self.model == 'kamstrup602':
            start = 45
            key = '0459'
            coeff = 0.01
        elif self.model == 'sensusPE':
            start = 45
        else:
            log.warning('unknown model '+self.model)
            return None
            
        return self.decode(start, key) * coeff # converted to degC
        
        