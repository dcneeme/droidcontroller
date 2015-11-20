# This Python file uses the following encoding: utf-8
# last change  6.9.2015, added crc chk

''' 
mbys.py - query and process kamstrup, sensus or axis heat meters via Mbus protocol, 2400 8E1
 usage:
 from mbus import *
 m=Mbus()
 m.read() # tekitab m.mbm (bytes)
 m.debug()
 m.get_temperatures(), m.get_energy, m.get_flow, m.get(volume), m.get-all()

mbm uurimiseks (anna m.mbm=b' .... ' ette kui lugejat pole kyljes. peta ftdi kaabliga)
>>> import codecs
>>> codecs.encode(m.mbm, 'hex')
b'6842426808007299007642184e6004861000000c06859545000c13651457550c3b000000000c2b000000000a5a72010a5e73010b600000000c78990076420cfd10990076421fda16'
>>> len(m.mbm)
72

data='99007642184e6004861000000c06859545000c13651457550c3b000000000c2b000000000a5a72010a5e73010b600000000c78990076420cfd10990076421f'

length=4
hex=0
start=21
key='0c'
m.mb_decode(start, key=key, coeff = 1.0, desc = 'test', length = length, hex = hex)

'''

from codecs import encode # for encode to work in py3
import time
import serial
import traceback
import struct  # struct.unpack for float from hex 
import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO) # temporary
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
        Decoding is different, see mb_decode().
    '''

    def __init__(self, port='auto', autokey='FTDI', tout=3, speed=2400, model='sensusPE'):  # tout 1 too small! win port like 'COM27'
        ports = list(serial.tools.list_ports.comports())
        #found = 0
        if port == 'auto':
            try:
                for i in range(len(ports)):
                    if autokey in ports[i][1]:
                        #found = 1
                        self.port = ports[i][0]
            except:
                log.warning('USB port autodiscovery for Mbus FAILED')
                self.port = '/devAMA0' # console
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
        ''' Use this to get rid of the instance if not required '''
        self.__del__()

    def __del__(self):
        ''' Destroyer for close() '''
        class_name = self.__class__.__name__
        log.info(class_name+' destroyed')

    def reopen(self): # try to restore serial channel
        ''' Attempt to restore failing USB port by closing and reopening '''
        log.warning('trying to restore Mbus connectivity by closing and reopening serial port '+self.port)
        self.ser.close()
        time.sleep(1)
        self.ser.open()
        if self.model == 'sensusPE':
            self.ser.write(b'\x68\x03\x03\x68\x73\xFE\x50\xC1\x16') # answer mode set
            time.sleep(0.5)
        self.read() 

    def chk_crc(self): # works against m.mbm
        if self.mbm != None and len(self.mbm) > 10:
            chk = ord(self.mbm[-2:-1]) # chksum as int
            sum = 0
            for bait in range(4,len(self.mbm)-2):
                sum += self.mbm[bait]
                sum = (sum & 0xFF)
            if sum == chk:
                return True
            else:
                log.warning('CRC problem! sum '+str(sum)+', chk '+str(chk))
                print('CRC problem! sum '+str(sum)+', chk '+str(chk)) ##
                return False
    
    def set_model(self, invar):
        self.model = invar

    def get_model(self):
        return self.model

    def get_port(self):
        return self.port

    def get_errors(self):
        return self.errors

    def mb_decode(self, start, key='', coeff = 1.0, desc = 'unknown', length = None, hex = None): 
        # len and hex will be autodetected if hex is not given
        ''' Returns decoded value from Mbus binary string self.mbm or None if no valid self.mbm.
            Decoded part of length bytes in mbm starts from invar.
            If key (2 bytes as hex string before data start) is given,
            then it is used for finding len and decoding type selection.
            Coeff is used for unit normalization, to produce output in common units.
        '''
        # default encoding (hex == 1) is hex 4 bytes, LSB first
        # if hex == 0, BCD is used with numbers 0..9 only used
        if (length == None or hex == None) and key != '' and len(key) > 1: # 2 or 4 characters, first 2 define data length
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
                elif key[1] == 'C' or key[1] == 'c' or key[1] == '2': # viimane on axis sks3 temp
                    length = 4
                    hex = 0
                elif key[1] == '5': # hex float 32 bit real
                    length = 4
                    hex = 3 # real32
                else:
                    log.warning('length/hex autodetection failed, length '+str(length)+', key '+key)
                    return None
            else:
                log.warning('length/hex autodetection failed, length '+str(length)+', key '+key)
                return None
        else:
            log.debug('using length '+str(length)+' and hex '+str(hex)+' for decoding starting from '+str(start))
        
        if length == None or hex == None:
            log.warning('invalid hex='+str(hex)+' or length='+str(length))
            return None
            
        try: # swap the bytes order and convert to integer
            res = 0
            log.debug('decoding data string '+str(self.mbm[start:start+length])) ##
            for i in range(length):
                if hex == 1:
                    #res += int(ord(self.mbm[start + i])) << (i * 8) # ok for py2, but not for py3
                    res += int(str(self.mbm[start + i]), 16) << (i * 8) # py3. numbers still 0..9, base 10!
                    log.debug('decoding HEX value step '+str(i)+', res='+str(res))
                elif hex == 0: # MSB == F then it signals negative number! A...E are invalid!
                    # UNTESTED WITH NEGATIVE NUMBERS!!!
                    res += int(str(encode(self.mbm[(start + i):(start +i +1)], 'hex_codec'))[-3:-1],10)  * (10 ** (2*i)) # 6.9.2015 
                    # testitud str(encode(m.mbm[23:24], 'hex_codec'))[-3:-1]
                    log.debug('decoding BCD value step '+str(i)+', res='+str(res))
                    ##print('decoding hex=0 value step '+str(i)+', res='+str(res)) ##
                    #if i == length - 1: # last (MSB), possible sign data
                    #    if (int(str(self.mbm[len - 1]), 10) & 0xF0) == 0xF0: # the result is negative
                    #        res= -res
                elif hex == 4: # int 16
                    # UNTESTED WITH NEGATIVE NUMBERS!!!
                    res += int(str(encode(self.mbm[(start + i):(start +i +1)], 'hex_codec'))[-3:-1],16)  * (10 ** (2*i)) # 6.9.2015 
                    # testitud str(encode(m.mbm[23:24], 'hex_codec'))[-3:-1]
                    log.debug('decoding BCD value step '+str(i)+', res='+str(res))
                    ##print('decoding hex=4 value step '+str(i)+', res='+str(res)) ##
                elif hex == 2: # axis energy
                    res += int(str(self.mbm[start + i]), 10) << (i * 8)
                elif hex == 3:
                    hf = self.mbm[start:start+4] # need to be reordered, WITH UNPACK
                    hfs = str(encode(hf, 'hex_codec'))[2:10]
                    res = struct.unpack('<f', bytes.fromhex(hfs))[0] # py3, converts to float from 32real hex LITTLE ENDIAN
                    #return res * coeff # coeff defined in parent
                else:
                    log.warning('illegal hex value '+str(hex))
                    return None
                    
            # modify coefficients
            if key != '' and str(key.lower()) not in str(encode(self.mbm[start-2:start], 'hex_codec')) \
                and str(key.upper()) not in str(encode(self.mbm[start-2:start], 'hex_codec')): # check
                log.warning('non-matching key '+str(key)+' for '+desc+' in key+data ' + str(encode(self.mbm[start-2:start], 'hex_codec'))+ \
                    ' '+str(encode(self.mbm[start:start+4], 'hex_codec')))
                self.errors += 1
                return None
            else: # key exists and matches, fix coeff if needed
                self.errors = 0
                keyext = str(encode(self.mbm[start-1:start], 'hex_codec'))
                if desc == 'flow' and '2d' in keyext:
                    coeff = 1.0
                    log.debug('2d coeff chg to '+str(coeff))
                elif desc == 'energy' and '06' in keyext:
                    coeff = 1.0 # rahvamaja, sensusPE
                    log.debug('07 coeff chg to '+str(coeff))
                elif desc == 'energy' and '07' in keyext:
                    coeff = 10.0 # pargi3, sensusPE
                    log.debug('07 coeff chg to '+str(coeff))
                elif desc == 'volume' and '14' in keyext:
                    coeff = 10.0 # KUS?
                    log.debug('15 coeff chg to '+str(coeff))
                elif desc == 'volume' and '15' in keyext:
                    coeff = 100.0 # spordihoone, kamstrup402
                    log.debug('15 coeff chg to '+str(coeff))
                elif desc == 'power' and '2d' in keyext:
                    coeff = 100.0 # multical 602 power karla koolis
                    log.debug('coeff chg for multical 602 power to '+str(coeff))
                elif '3b' in keyext:
                    coeff = 1.0
                    log.debug('3b coeff chg to '+str(coeff))
                elif '2b' in keyext: # sensusPE power rahvamaja
                    coeff = 1.0
                    log.debug('2b coeff chg to '+str(coeff))
                elif '13' in keyext: # sensus volume rahvamaja
                    coeff = 1.0
                    log.debug('13 coeff chg to '+str(coeff))
                elif '14' in keyext: # volume coeff 10
                    coeff = 10.0
                    log.debug('14 coeff chg to '+str(coeff))
                elif '15' in keyext: # volume coeff 100
                    coeff = 100.0
                    log.debug('15 coeff chg to '+str(coeff))
                else:
                    log.debug('coeff NOT changed, still '+str(coeff)+', key end '+keyext)

                log.debug('mb_decode coeff '+str(coeff)+' for '+desc+', key '+ keyext)
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


    def rd_chk(self, query=b'\x10\x7B\xFE\x79\x16'): 
        ''' Sends the query, reads the response and checks the content '''
        try:
            self.ser.flushInput() # no garbage or old responses wanted
            #if self.model == 'sensusPE':
            #    self.ser.write(b'\x68\x03\x03\x68\x73\xFE\x50\xC1\x16') # answer mode set
            #    time.sleep(0.5) # muidu ei tule jargmist vastust
            ## addded 5.7.2015
            self.ser.write(b'\x10\x40\xfe\x3e\x16') # init? from mtool example
            time.sleep(0.5) # muidu ei tule jargmist vastust

            self.ser.write(b'\x68\x03\x03\x68\x73\xFE\x50\xC1\x16') # answer mode set, from mtool
            time.sleep(0.5) # muidu ei tule jargmist vastust
            ## adding end
            
            self.ser.flushInput() # no garbage or old responses wanted
            self.ser.write(query) # kamstrup and sensus
            
            self.mbm = self.ser.read(253) # kamstrup: should be 254 bytes, but the first byte E5 disappears??
            if len(self.mbm) > 0:
                if str(encode(self.mbm, 'hex_codec'))[-3:-1] == '16' and self.chk_crc(): # crc chk added 6.9.2015
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

    def get_test(self, start, key='', length = 4, hex = 1):
        ''' returns data from m.mbm based on variables start, key ''' 
        res = self.mb_decode(start, key, coeff = 1.0, desc = 'test', length = length, hex = hex) # len always 4 = default
        #if res == 0: 
        #    log.warning('invalid mb_decode output '+str(res))
        #    return None
        return res
        

    def get_energy(self):
        ''' Return energy from the last read result. Chk the datetime in self.mbm as well! '''
        key = ''
        length = None
        hex = None # autodetect in mb_decode() where not given
        coeff = 1.0 # kwh
        if self.model == 'kamstrup602':
            start = 27 # check with mtools and compare with debug output
            key = '0406' # 2 hex bytes before data, to be sure
        elif self.model == 'kamstrup402': # tapselt nagu axisSKS3
            start = 27 # check with mtools and compare with debug output
            key = '0407' # 2 hex bytes before data, to be sure
            length = 4 # auto andis vale! 6.9.2015
            hex = 2 # auto andis vale! 6.9.2015
            coeff  = 10.0
        elif self.model == 'sensusPE':
            start = 21
            #key = '0c07' # voib olla ka 0c06 !
            key = '0c'
            #lenght = 4 # olgu auto! pargi3 ja rahvamaja sensused erinevad!
            #hex = 2 # olgu auto! pargi3 ja rahvamaja sensused erinevad!
        elif self.model == 'axisSKU03': # lasteaed
            start = 53
            key = '863b'
            hex = 2
            length = 4
        elif self.model == 'axisSKS3': # katlamaja x 10 kWh
            coeff = 10 
            start = 27
            key = '0407'
            hex = 2
            length = 4
        else:
            log.warning('unknown meter model '+self.model)
            return None

        res = self.mb_decode(start, key, coeff, 'energy', length = length, hex = hex) # len always 4 = default
        if res == 0: # double protection
            log.warning('invalid mb_decode output '+str(res))
            return None
        return res
            
            
    def get_volume(self): # one value
        ''' Return volume in l from the last read result. Chk the datetime in self.mbm as well! '''
        key = ''
        coeff = 1.0
        hex = None
        length = None
        if self.model == 'kamstrup602' or self.model == 'kamstrup402':
            start = 33
            key = '04' # teine osa 14 voi 15? auto?
            coeff = None # parandus mb_decode ajal
            hex = 2 # 6.9.2015
            length = 4
        #elif self.model == 'kamstrup402':
        #    start = 33
        #    key = '0415'
        #    coeff = 100.0 # l
        elif self.model == 'sensusPE':
            start = 27
            key = '0c' # 14 or 13 the end for volume
            coeff = 10.0
            hex = 0 # 6.9.2015, enne puudus
            length = 4
        elif self.model == 'axisSKU03': # lasteaed
            start = 59
            key = '0413'
            hex = 2
            coeff = 1.0
            length = 4
        elif self.model == 'axisSKS3': # katlamaja
            start = 34
            key = '4015'
            length = 4
            hex = 2
        elif self.model == 'cyble_v2': # itron cyble v2, 32bit var, magnetic target reader
            start = 69
            key = '0413'
            coeff = 1.0 # L unit
            hex = 0
        elif self.model == 'itron_mb+m': # itron optical, 32 bit var
            start = 27
            key = '0413'
            coeff = 1.0 # L unit
            hex = 0
            
        else:
            log.warning('unknown model '+self.model)
            return None

        res = self.mb_decode(start, key, coeff, 'volume', length = length, hex = hex) # len always 4 = default
        if res == 0: # double protection
            log.warning('invalid mb_decode output '+str(res))
            return None
        return res


    def get_power(self):
        ''' Return power from the last read result. Chk the datetime in self.mbm as well! '''
        key= ''
        coeff = 1
        length = None
        hex = None
        if self.model == 'kamstrup602' or self.model == 'kamstrup402': # similar
            start = 63
            key = '04' # 2d' # use lower or upper case, no difference
            coeff = 100.0 # W
        elif self.model == 'sensusPE':
            start = 39
            #key='0c2c'
            key='0c'
            coeff = 10.0 #
            length = 4 # 6.9.2015
            hex = 0 # 6.9.2015
        elif self.model == 'axisSKU03': # lasteaed
            start = 65
            key = '052e' # from fex float, 32real
            coeff = 1000.0
            hex = 1
        elif self.model == 'axisSKS3': # katlamaja
            start = 40
            key = '052e' # from fex float, 32real
            coeff = 1000.0
            hex = 1
        else:
            log.warning('unknown model '+self.model)
            return None

        res = self.mb_decode(start, key, coeff, 'power', length = length, hex = hex)
        return res
        
        
    def get_flow(self):
        ''' Return power from the last read result. Chk the datetime in self.mbm as well! '''
        key= ''
        coeff = 1
        length = None
        hex = None
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
            hex = 0
            coeff = 10.0 #  L/h
            length = 4 # autodetect with None
        elif self.model == 'axisSKU03': # lasteaed
            start = 71
            key = '053e' # from fex float
            coeff = 1000.0
            hex = 3
            length = 4
        elif self.model == 'axisSKS3': # katlamaja
            start = 47
            key = '403e' # from fex float
            coeff = 1000.0
            hex = 3
            length = 4
        else:
            log.warning('unknown model '+self.model)
            return None

        res = self.mb_decode(start, key, coeff, 'flow', length = length, hex = hex)
        return res
        

    def get_volumes(self): # DOES NOT WORK, ERRORS
        ''' Return water volume readings. 
            testing
            m.mb_decode(69,'0413',1.0,'vol',length=4,hex=0)
        '''
        temp = None
        key = ['','','']
        coeff = [1.0, 1.0, 1.0]
        length = [4, 4, 4] # bytes
        hex = None # 1
        if self.model == 'cyble_v2': # itron cyble v2, 32bit var, the first is the normal reading
            ''' 69  0413   00000000
                75  0493   7F000000 
                82  4413   00000000
            '''
            start = [69, 75, 82]
            key = ['0413', '0493', '4413'] # three volumes, dunno why so many
            #coeff = [1.0, 1.0, 1.0] # L unit
            hex = 0
        elif self.model == 'itron_mb+m': # itron opto, 32bit var, the first is the normal reading
            ''' 27  0413   00000000
                37  4413   00000000
            '''
            start = [27, 37]
            key = ['0413', '4413'] # volumes, dunno why 2 of them
            coeff = [1.0, 1.0] # L unit
            hex = 0
        
        else:
            log.warning('unknown model '+self.model)
            return None

        out = []
        #try:
        for i in range(len(start)):
            try:
                temp = round(self.mb_decode(start[i], key[i], coeff[i], 'volumes', length=length[i], hex=hex),3)
                out.append(temp)
            except:
                log.warning('failed to mb_decode volumes output, start '+str(start[i])+', key '+key[i]+', coeff '+str(coeff[i]))
                traceback.print_exc()

        return out
        
    
    def get_temperatures(self):
        ''' Return temperature readings out, return, diff extracted from the last read result.   '''
        temp = None
        key = ['','','']
        coeff = [1.0, 1.0, 1.0]
        length = [4, 4, 4] # bytes
        hex = 1
        if self.model == 'kamstrup602' or self.model == 'kamstrup402': # checked, 402 is similar
            start = [45, 51, 57]
            key = ['0459', '045D', '0461'] # inlet outlet diff
            coeff = [0.01, 0.01, 0.01] # 10 mK unit
            hex = 4 # eriti idiootne kodeering, 10 astmetega 16/koodi vaartused liita!
        elif self.model == 'sensusPE':
            start = [45, 49, 53] 
            key = ['0a5a', '0a5e', '0b60']
            coeff = [0.1, 0.1, 0.001]
            length = [2, 2, 3]
            hex = 0 # 6/9/2015   # 0 
        elif self.model == 'axisSKU03': # lasteaed
            coeff = [1.0, 1.0, 1.0]
            start = [77, 83, 89]
            key = ['055b', '055f', '0563'] 
            length = [4, 4, 4]
            hex = 3 # !!!  float
        elif self.model == 'axisSKS3': # katlamaja
            coeff = [0.01, 0.01, 0.01]
            start = [53, 57, 68]    # 32, 32, 16 bit numbers. 
            key = ['0259', '025d', 'fd17']  
            length = [2, 2, 2]
            hex = 2
        else:
            log.warning('unknown model '+self.model)
            return None

        out = []
        try:
            for i in range(len(start)):
                temp = round(self.mb_decode(start[i], key[i], coeff[i], 'temperatures', length=length[i], hex=hex),3)
                if temp != 0:
                    out.append(temp) # converted to degC
                else:
                    out.append(None) # 0 kraadi on voimatu veetorustikus
        except:
            log.warning('failed to append mb_decode temperatures output')
            traceback.print_exc()

        return out


    def get_datetime(self):
        ''' Returns some 23 bit number of minutes(?) in unknown format 
            http://www.aquametro.com/downloads/docs/3166a_e_calec-mb_m-bus-protokoll.pdf
            4.2.1 Definition of the G format (coding the date)
            first byte               second byte
            a2 a1 a0 j4 j3 j2 j1 j0  a6 a5 a4 a3 M3 M2 M1 M0
             j4..j0 code the day (1..31), M3..M0 code the month (1..12), a6..a0 code the year (0..99)
             
            4.2.2 Definition of the F format (coding the date and time).
            first byte             second byte          third byte      fourth byte
            0 0 n5 n4 n3 n2 n1 n0  0 0 0 h4 h3 h2 h1 h0 =byte1 format G = byte2 format G
             h4..h0 code the hour (0..23), n5..n0 code the minute (0..59)
         '''
        key = '046d' # the same for every meter
        if self.model == 'kamstrup602' or self.model == 'kamstrup602':
            start = 124
        elif self.model == 'sensusPE': #FIXME
            key = '046d' # seda koodi ei ole / FIXME
            start = 124
        elif self.model == 'axisSKS3': # katlamaja
            start = 21
        elif self.model == 'cyble_v2': 
            start = 43 #FIXME
        elif self.model == 'itron_mb+m': # OK
            start = 43
            
        else:
            log.warning('datetime not implemented for '+self.model)
            return None

        #output seconds from 1.1.1970 in minute step 
        # 2309EB18 = 15, 08, 11, 09, 35
        minute = (int(str(self.mbm[start]), 10) & 0x3F)
        hour = (int(str(self.mbm[start + 1]), 10) & 0x1F)
        year = ((int(str(self.mbm[start + 3]), 10) & 0xF0) >> 1) + ((int(str(self.mbm[start + 2]), 10) & 0xE0) >> 5)
        month = (int(str(self.mbm[start + 3]), 10) & 0x0F)
        day = (int(str(self.mbm[start + 2]), 10) & 0x1F)
        
        return year, month, day, hour, minute


    def get_all(self):
        '''Returns all or most measured values fot heat meters '''
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
    print('result', m.mb_decode(45))
    m.debug(45)

