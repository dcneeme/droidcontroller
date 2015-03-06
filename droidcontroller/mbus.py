# This Python file uses the following encoding: utf-8
# last change 5.3.2014

''' 
mbys.py - query and process kamstrup, sensus or axis heat meters via Mbus protocol, 2400 8E1
# usage:
# from mbus import *
# m=Mbus()
# m.read()
# m.get_temperatures()
'''

from codecs import encode # for encode to work in py3
import time
import serial
import traceback
import struct  # struct.unpack for float from hex 
import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG) # temporary
log = logging.getLogger(__name__)

import serial.tools.list_ports
print(list(serial.tools.list_ports.comports()))
# [('/dev/ttyUSB1', 'FTDI TTL232R FTH8AIQ9', 'USB VID:PID=0403:6001 SNR=FTH8AIQ9')]

class Mbus:
    ''' Read various utility meters using Mbus, speed 2400, 8E1
        First read(), then get_ . Keeps count of read errors (since last success or init).
        Needs USB/serial converter and Mbus interface card.
        USB port can be described as port, but this software is able to find the USB
        port (like /dev/ttyUSB0 or COM18) also by autokey (like FTDI).

        With both sensus and kamstrup, data bytes for readings contain numbers 0..9.
        With sensus, this is called BCD 4, 6 or 8 encoding.
        Key block is then starting with 0A, 0B or 0C respectively.
        Decoding is different, see decode().
    '''

    def __init__(self, port='auto', autokey='FTDI', tout=3, speed=2400, model='sensusPE'):  # tout 1 too small! win port like 'COM27'
        ports=list(serial.tools.list_ports.comports())
        found = 0
        if port == 'auto':
            for i in range(len(ports)):
                if autokey in ports[i][1]:
                    found = 1
                    self.port = ports[i][0]
        else: # no
            self.port = port

        self.tout = tout
        self.speed = speed
        self.model = model
        self.ser = serial.Serial(self.port, self.speed, timeout=tout, parity=serial.PARITY_EVEN) # also opening the port
        self.errors = 0 # every success zeroes
        self.mbm = '' # last message
        try:
            self.read()
            log.info('Mbus connection for model '+self.model+' successful on port '+self.port)
        except:
            log.error('Mbus connection FAILED on port '+self.port)

    def close(self):
        self.__del__()

    def __del__(self):
        class_name = self.__class__.__name__
        print(class_name, 'destroyed')

    def reopen(self): # try to restore serial channel
        ''' Attempt to restore failing USB port by closing and reopening '''
        log.warning('trying to restore Mbus connectivity by closing and reopening serial port '+self.port)
        self.ser.close()
        time.sleep(1)
        self.ser.open()
        if self.model == 'sensusPE':
            self.ser.write(b'\x68\x03\x03\x68\x73\xFE\x50\xC1\x16') # answer mode set
            time.sleep(0.5)
        self.read() # dummy, contains zeroes, some buffer??

    def set_model(self, invar):
        if invar in ['kamstrup602', 'sensusPE']:
            self.model = invar

    def get_model(self):
        return self.model

    def get_port(self):
        return self.port

    def get_errors(self):
        return self.errors

    def mb_decode(self, invar, key='', coeff = 1.0, desc = 'unknown', length = 4, hex = 1): # len and hex may be overruled by key
        ''' Returns decoded value from Mbus binary string self.mbm, length bytes starting from invar.
            If key (2 bytes as hex string before data start) is given,
            then it is used for finding len and decoding type selection.
            Coeff is used for unit normalization, to produce output in usual units.
        '''
        # default encoding (hex == 1) is hex 4 bytes, LSB first
        # if hex == 0, BCD is used with numbers 0..9 only used
        if key != '' and len(key) > 1: # 2 or 4 characters, first 2 define data length, the next is unknown for me, may vary even for the same model
            if key[0] == '0':
                if key[1] == '4':
                    length = 4
                    hex = 1
                elif key[1] == 'A' or key[1] == 'a':
                    length = 2
                    hex = 0
                elif key[1] == 'B' or key[1] == 'b':
                    length = 3
                    hex = 0
                elif key[1] == 'C' or key[1] == 'c':
                    length = 4
                    hex = 0
                elif key[1] == '5': # hex float 32 bit real
                    hf = self.mbm[invar:invar+4] # need to be reordered, WITH UNPACK
                    hfs = str(encode(hf, 'hex_codec'))[2:10]
                    res = struct.unpack('<f', bytes.fromhex(hfs))[0] # py3, converts to float from 32real hex LITTLE ENDIAN
                    return res # no coeff needed
                    
                else:
                    log.warning('unsupported encoding for data, key '+str(key[0:2]))
                    return None
        try: # swap the bytes order and convert to integer
            res = 0
            for i in range(length):
                if hex == 1:
                    #res += int(ord(self.mbm[invar + i])) << (i * 8) # ok for py2, but not for py3
                    res += int(str(self.mbm[invar + i]), 16) << (i * 8) # py3. numbers still 0..9, base 10!
                    log.debug('decoding HEX value step '+str(i)+', res='+str(res))
                elif hex == 0: # MSB == F then it signals negative number! A...E are invalid!
                    # UNTESTED WITH NEGATIVE NUMBERS!!!
                    res += int(str(self.mbm[invar + i]), 10) * (10 ** (2*i))
                    log.debug('decoding BCD value step '+str(i)+', res='+str(res))
                    #if i == length - 1: # last (MSB), possible sign data
                    #    if (int(str(self.mbm[len - 1]), 10) & 0xF0) == 0xF0: # the result is negative
                    #        res= -res

            # modify coefficients
            if key != '' and str(key.lower()) not in str(encode(self.mbm[invar-2:invar], 'hex_codec')) \
                and str(key.upper()) not in str(encode(self.mbm[invar-2:invar], 'hex_codec')): # check
                log.warning('non-matching key '+str(key)+' for '+desc+' in key+data ' + str(encode(self.mbm[invar-2:invar], 'hex_codec'))+ \
                    ' '+str(encode(self.mbm[invar:invar+4], 'hex_codec')))
                self.errors += 1
                return None
            else:
                self.errors = 0
                if desc == 'flow' and '2d' in str(encode(self.mbm[invar-1:invar], 'hex_codec')):
                    coeff = 1.0
                    log.debug('2d coeff chg to '+str(coeff))
                elif desc == 'power' and '2d' in str(encode(self.mbm[invar-1:invar], 'hex_codec')):
                    coeff = 100.0 # multical 602 power karla koolis
                    log.debug('coeff chg for multical 602 power to '+str(coeff))
                elif '3b' in str(encode(self.mbm[invar-1:invar], 'hex_codec')):
                    coeff = 1.0
                    log.debug('3b coeff chg to '+str(coeff))
                elif '2b' in str(encode(self.mbm[invar-1:invar], 'hex_codec')): # sensusPE power rahvamaja
                    coeff = 1.0
                    log.debug('2b coeff chg to '+str(coeff))
                elif '13' in str(encode(self.mbm[invar-1:invar], 'hex_codec')): # sensus volume rahvamaja
                    coeff = 1.0
                    log.debug('13 coeff chg to '+str(coeff))
                elif '14' in str(encode(self.mbm[invar-1:invar], 'hex_codec')): # volume coeff 10
                    coeff = 10.0
                    log.debug('14 coeff chg to '+str(coeff))
                elif '15' in str(encode(self.mbm[invar-1:invar], 'hex_codec')): # volume coeff 100
                    coeff = 100.0
                    log.debug('15 coeff chg to '+str(coeff))
                else:
                    log.debug('coeff NOT changed, still '+str(coeff)+', key end '+str(encode(self.mbm[invar-1:invar], 'hex_codec')))

                log.debug('mb_decode coeff '+str(coeff)+' for '+desc+', key '+ str(encode(self.mbm[invar-2:invar], 'hex_codec')))
                return res * coeff
        except:
            traceback.print_exc()
            log.warning('hex string decoding failed')
            self.errors += 1
            return None


    def read(self):
        ''' Read and save the answer from the Mbus device into self.mbm. Uses rd_chk() to retry once on failure. '''
        res = self.rd_chk()
        if res == 0:
            self.errors = 0
            return 0
        else:
            self.errors +=1
            if self.errors > 1:
                return 1
            elif self.errors == 1: #retrying once
                self.reopen()
                res = self.rd_chk()
                if res == 0:
                    self.errors = 0
                    return 0
                else:
                    self.errors +=1
                    return 1


    def rd_chk(self, query=b'\x10\x7B\xFE\x79\x16'): # proovi ka muid
        ''' Sends the query, reads the response and checks the content '''
        try:
            self.ser.flushInput() # no garbage or old responses wanted
            if self.model == 'sensusPE':
                self.ser.write(b'\x68\x03\x03\x68\x73\xFE\x50\xC1\x16') # answer mode set
                time.sleep(0.5) # muidu ei tule jargmist vastust
            self.ser.flushInput() # no garbage or old responses wanted
            self.ser.write(query) # kamstrup and sensus
            #self.ser.write(b'\x10\x7B\xFE\x79\x16') # sensus - similar!

            self.mbm = self.ser.read(253) # kamstrup: should be 254 bytes, but the first byte E5 disappears??
            if len(self.mbm) > 0:
                #if len(self.mbm) == 253 and str(encode(self.mbm, 'hex_codec'))[2:10] == '68f7f768' and str(encode(self.mbm, 'hex_codec'))[-3:-1] == '16':
                if str(encode(self.mbm, 'hex_codec'))[-3:-1] == '16':
                    log.debug('got a valid message from mbus, length ' + str(len(self.mbm)) + ' bytes')
                    print('got a valid message of '+str(len(self.mbm))+' bytes from mbus (first 20 follow): '+str(encode(self.mbm, 'hex_codec'))[:20])
                    return 0
                else:
                    log.warning('INVALID message with length ' + str(len(self.mbm)) + ' received from mbus device!')
            else:
                log.warning('no answer from mbus device')
        except:
            log.error('USB port probably disconnected!!')
            self.errors += 1 # sure increase needed
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
        elif self.model == 'kamstrup402':
            start = 27 # check with mtools and compare with debug output
            key = '0407' # 2 hex bytes before data, to be sure
        elif self.model == 'sensusPE':
            start = 21
            #key = '0c07'
            key = '0c'
        elif self.model == 'axisSKU03':
            start = 59
            key = '0486'
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff, 'energy') # len always 4 = default


    def get_volume(self):
        ''' Return volume from the last read result. Chk the datetime in self.mbm as well! '''
        key = ''
        coeff = 1.0
        if self.model == 'kamstrup602' or self.model == 'kamstrup402':
            start = 33
            key = '04' # 14'
            coeff = 10.0 # l
        #elif self.model == 'kamstrup402':
        #    start = 33
        #    key = '0415'
        #    coeff = 100.0 # l
        elif self.model == 'sensusPE':
            start = 27
            key = '0c' # 14 or 13 the end for volume
            coeff = 10.0
        elif self.model == 'axisSKU03':
            start = 59
            key = '0413' # from fex float
        
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff, 'volume')


    def get_power(self):
        ''' Return power from the last read result. Chk the datetime in self.mbm as well! '''
        key= ''
        coeff = 1
        if self.model == 'kamstrup602' or self.model == 'kamstrup402': # similar
            start = 63
            key = '04' # 2d' # use lower or upper case, no difference
            coeff = 100.0 # W
        elif self.model == 'sensusPE':
            start = 39
            #key='0c2c'
            key='0c'
            coeff = 10.0 #
        elif self.model == 'axisSKU03':
            start = 65
            key = '052e' # from fex float
            
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff, 'power')

    def get_flow(self):
        ''' Return power from the last read result. Chk the datetime in self.mbm as well! '''
        key= ''
        coeff = 1
        if self.model == 'kamstrup602' or self.model == 'kamstrup402':
            start = 75 # CHK!
            #key = '042d' # use lower or upper case, no difference
            key = '04' # teisest poolest soltub komakoht?
            coeff = 1.0 # L/H
        #elif self.model == 'kamstrup402':
        #    start = 75
        #    key = '043b' # use lower or upper case, no difference
        #    coeff = 1.0 # L/H
        elif self.model == 'sensusPE':
            start = 33
            #key='0c3c'
            key='0c'
            coeff = 10.0 #  L/h
        elif self.model == 'axisSKU03':
            start = 78
            key = '053e' # from fex float
            
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff, 'flow')


    def get_temperatures(self):
        ''' Return temperature readings out, return diff extracted from the last read result. Chk the datetime in self.mbm as well! '''
        key =['','','']
        coeff = [1.0, 1.0, 1.0]
        length = [4, 4, 4] # bytes
        if self.model == 'kamstrup602' or self.model == 'kamstrup402': # checked, 402 is similar
            start = [45, 51, 57]
            key = ['0459', '045D', '0461'] # inlet outlet diff
            coeff = [0.01, 0.01, 0.01] # 10 mK unit
        elif self.model == 'sensusPE':
            start = [45, 49, 53] 
            key = ['0a5a', '0a5e', '0b60']
            coeff = [0.1, 0.1, 0.001]
            length = [2, 2, 3]
        elif self.model == 'axisSKU03':
            start = [77, 83, 96]
            key = ['055b', '055f', '0563'] # from fex float
        else:
            log.warning('unknown model '+self.model)
            return None, None, None

        out = []
        try:
            for i in range(3):
                out.append(round(self.mb_decode(start[i], key[i], coeff[i], 'temperatures', length[i]),3)) # converted to degC
        except:
            log.warning('failed to append mb_decode temperatures output')
            traceback.print_exc()

        return out


    def get_datetime(self):
        ''' Returns some 23 bit number of minutes(?) in unknown format '''
        key= ''
        coeff = 1
        if self.model == 'kamstrup602' or self.model == 'kamstrup602':
            start = 124
            key = '046d' # use lower or upper case, no difference
            coeff = 1
        elif self.model == 'sensusPE':
            start = 124
            key = '046d' # UNTESTED
            coeff = 1
        else:
            log.warning('unknown model '+self.model)
            return None

        return self.mb_decode(start, key, coeff, 'datetime')


    def get_all(self):
        '''Returns all or most measured values '''
        res = {}
        res.update({ 'model' : self.get_model() })
        res.update({ 'power W' : self.get_power() })
        res.update({ 'energy kWh' : self.get_energy() })
        res.update({ 'flow l/h' : self.get_flow() })
        res.update({ 'volume l' : self.get_volume() })
        res.update({ 'temperatures degC' : self.get_temperatures() })
        #res.update({ 'datetime' : self.get_datetime() }) # annab vea index out of range

        return res

##########################################################
if __name__ == '__main__':
    m=Mbus()
    m.read()
    print('result',m.mb_decode(45))
    m.debug(45)

