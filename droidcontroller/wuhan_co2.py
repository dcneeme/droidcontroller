# This Python file uses the following encoding: utf-8
'''
co2, rh and T sensor from wuhan.cubic, gassensor.com.cn

'''

from codecs import encode # for encode to work in py3
import time
import serial
import traceback
import struct  # struct.unpack for float from hex
import sys, logging
log = logging.getLogger(__name__)

import serial.tools.list_ports
print(list(serial.tools.list_ports.comports()))
# [('/dev/ttyUSB1', 'FTDI TTL232R FTH8AIQ9', 'USB VID:PID=0403:6001 SNR=FTH8AIQ9')]

class Sensor:
    '''
    '''

    def __init__(self, port='auto', autokey='FTDI', tout=3, speed=9600):  # win port like 'COM29'
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
        self.model = None
        self.ser = serial.Serial(self.port, self.speed, timeout=tout, parity=serial.PARITY_NONE) # also opening the port
        self.errors = 0 # every success zeroes
        self.mbm = '' # last message
        try:
            self.read()
            log.info('serial connection established successfully on port '+self.port)
        except:
            log.error('serial connection FAILED on port '+self.port)

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


    def rd_chk(self, query=b'\x11\x01\x01\xED'):
        ''' Sends the query, reads the response and checks the content '''
        try:
            self.ser.flushInput() # no garbage or old responses wanted
            self.ser.write(query) #
            time.sleep(0.5) # muidu ei tule jargmist vastust

            self.mbm = self.ser.read(99) #
            if len(self.mbm) > 0:
                log.info('got a message from sensor, length ' + str(len(self.mbm)) + ' bytes: '+str(encode(self.mbm, 'hex_codec'))[:20])
                return 0

            else:
                log.warning('no answer from sensor device')
        except:
            log.error('USB port probably disconnected!!')
            self.errors += 1 # sure increase needed
        return 1


    def decode_co2(self):
        '''co2 only from this model '''
        res = 0
        for i in range(2):
            res += int(str(self.mbm[4 - i])) << (i * 8)
            #res += int(str(self.mbm[4 - i]), 16) << (i * 8) # wrong!
            #print('adc 16 debug ', i, self.mbm[4 - i], int(str(self.mbm[4 - i]), 16), res)
            #print('adc 10 debug ', i, self.mbm[4 - i], int(str(self.mbm[4 - i])), res)
        return res


    def get_all(self):
        '''Returns all or most measured values fot heat meters '''
        res = {}
        self.read() # self.mbm created
        res.update({ 'co2' : self.decode_co2() })
        #res.update({ 'temperature' : self.get_power() })
        #res.update({ 'humidity' : self.get_energy() })
        return res

    def set_co2(self, invar):
        ''' sets zero shift
            CO2 Set Zero & Calibration
            Send:11 03 03 DF1 DF2 CS
            Response:16 01 03 E6
            kuid ainult co2 anduriga variant ei lase end kalibreerida, peale sedA 550 JA SIIS 680 JNE PPM...
        '''
        if invar < 300 or invar > 10000:
            log.error('invalid value for co2 zero setting '+str(invar))
            return 2
        df1 = int(invar) >> 8
        df2 = int(invar) & 0xFF
        print('data to write ',df1, df2, '=',df1*256+df2)
        crc = ( (-1 *(0x11 + 0x03 + 0x03 + df1 + df2)) & 0xFF )
        sendbytes = b'\x11\x03\x03'
        sendbytes += bytes([df1])
        sendbytes += bytes([df2])
        sendbytes += bytes([crc])
        print('sendbytes '+str(sendbytes))
        self.ser.write(sendbytes)
        time.sleep(1)
        res = self.ser.read(99) #
        if len(res) > 0:
            log.info('calibration response: '+str(encode(res, 'hex_codec'))[:20]) # something like b'160103e6'
            return 0
        else:
            log.warning('no answer from sensor device')
            return 1


##########################################################
if __name__ == '__main__':
    m=Mbus()
    m.read()
    print('result', m.mb_decode(45))
    m.debug(45)

