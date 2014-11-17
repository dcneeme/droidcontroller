#mbys.py - query and process kamstrup and sensus meters via Mbus protocol, 2400 8E1
# usage:
# from mbus import *
# m=Mbus()
# m.read()
# m.get_temperature()

# ser.write() needs to be changed for py3
# self.ser.write('\x10\x7B\xFE\x79\x16') # TypeError: an integer is required


from codecs import encode # for encode to work in py3
import time
import serial
import traceback
import sys, logging
log = logging.getLogger(__name__)

class Mbus:
    ''' Read various utility meters using Mbus, speed 2400, 8E1   '''

    def __init__(self, port='/dev/ttyUSB0', tout=3, speed=2400, model='kamstrup602'):  # tout 1 too small! win port like 'COM27'
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


    def mb_decode(self, invar, key='', coeff = 1.0): # invar is the byte index in the read result from tty!
        ''' Returns decoded value from Mbus binary string self.mbm, 4 bytes starting from invar.
            If key (2 bytes as hex string before data start) is given,
            then it iwill used for data verification. Coeff is used for unit normalization.
        '''
        try:
            res = 0
            for i in range(4):
                #res += int(ord(self.mbm[invar + i])) << (i * 8) # ok for py2, but not for py3
                res += int(self.mbm[invar + i]) << (i * 8) # py3
                log.debug('res='+str(res))

            if key != '' and str(key.lower()) not in str(encode(self.mbm[invar-2:invar], 'hex_codec')) and str(key.upper()) not in str(encode(self.mbm[invar-2:invar], 'hex_codec')):
                log.warning('possible non-matching key '+str(key)+' in key+data ' + str(encode(self.mbm[invar-2:invar], 'hex_codec'))+' '+str(encode(self.mbm[invar:invar+4], 'hex_codec')))
                return None
            else:
                return res * coeff
        except:
            traceback.print_exc()
            log.warning('hex string decoding failed')
            return None


    def read(self):
        ''' Read and keep the answer from the Mbus device '''
        #self.ser.write('\x10\x7B\xFE\x79\x16') # OK for py2.7 BU T NOT 3.x!
        self.ser.write(b'\x10\x7B\xFE\x79\x16') # works for both

        self.mbm = self.ser.read(253) # should be 254 bytes, but the first byte E5 disappears??
        if len(self.mbm) > 0:
            log.debug('got from mbus ' + str(len(self.mbm)) + ' bytes')
            print('got from mbus (first 60 bytes): '+str(encode(self.mbm, 'hex_codec'))[:60]) # universal, works for 3,3 too
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
                    if str(invar) in str(encode(self.mbm[i:i+4], 'hex_codec')):
                        print(i, encode(self.mbm[i-2:i], 'hex_codec'), encode(self.mbm[i:i+4], 'hex_codec'))
                else:
                    print(i, str(encode(self.mbm[i-2:i], 'hex_codec')), str(encode(self.mbm[i:i+4], 'hex_codec')))


    def get_energy(self):
        ''' Return energy from the last read result. Chk the datetime in self.mbm as well! '''
        key = ''
        coeff = 1.0 # kwh
        if self.model == 'kamstrup602':
            start = 27 # check with mtools and compare with debug output
            key = '0406' # 2 hex bytes before data, to be sure
        elif self.model == 'sensusPE':
            start = 27
            key = ''
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff)


    def get_volume(self):
        ''' Return volume from the last read result. Chk the datetime in self.mbm as well! '''
        key = ''
        coeff = 1.0
        if self.model == 'kamstrup602':
            start = 33
            key = '0414'
            coeff = 10.0 # l
        elif self.model == 'sensusPE':
            start = 33
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff)


    def get_power(self):
        ''' Return power from the last read result. Chk the datetime in self.mbm as well! '''
        key= ''
        coeff = 1
        if self.model == 'kamstrup602':
            start = 63
            key = '042d' # use lower or upper case, no difference
            coeff = 100.0 # W
        elif self.model == 'sensusPE':
            start = 63
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff)


    def get_temperatures(self):
        ''' Return temperature readings out, return diff extracted from the last read result. Chk the datetime in self.mbm as well! '''
        key =['','','']
        coeff = [1.0, 1.0, 1.0]
        if self.model == 'kamstrup602': # checked, is 402 similar?
            start = [45, 51, 57]
            key = ['0459', '045D', '0461'] # inlet outlet diff
            coeff = [0.01, 0.01, 0.01]
        elif self.model == 'sensusPE':
            start = [45, 51, 57] # FIXME
            key = ['0459', '045D', '0461']
            coeff = [0.01, 0.01, 0.01]
        else:
            log.warning('unknown model '+self.model)
            return None, None, None

        out = []
        for i in range(3):
            out.append(self.mb_decode(start[i], key[i], coeff[i])) # converted to degC

        return out


##########################################################
if __name__ == '__main__':
    m=Mbus()
    m.read()
    print('result',m.mb_decode(45))
    m.debug(45)

