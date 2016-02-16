# This Python file uses the following encoding: utf-8
'''
    co2, rh and T sensor from wuhan.cubic, gassensor.com.cn. use python3!

    TEST
    from droidcontroller_co2wifi import Sensor
    w=Sensor(host='staatiline_ip', port=10001)
    w.rd_chk() # tekitab self.mbm
    w.decode_co2() # tagastab co2 ppm

'''

from codecs import encode # for encode to work in py3
import time
import traceback
import struct  # struct.unpack for float from hex
from socket import *
import select
import string


import sys, logging
log = logging.getLogger(__name__)



class Sensor:  # what about restart if conn failing?
    ''' This is for TCP over wifi only, transparent serial '''
    def __init__(self, host='192.168.0.241', port=10001, name=None):  # for co2 only
        self.name = name
        self.tcpsocket = socket(AF_INET,SOCK_STREAM) # tcp # 17.10.2012
        self.tcpsocket.settimeout(10)
        self.tcpport = port # default
        self.tcpaddr = host #
        print('Sensor instance created for '+self.tcpaddr+':'+str(self.tcpport)+', connection not tested!')
        
        
        
    def close(self):
        ''' Use this to get rid of the instance if not required '''
        self.__del__()

    def __del__(self):
        ''' Destroyer for close() '''
        class_name = self.__class__.__name__
        log.info(class_name+' destroyed')

    
    def chk_crc(self): # works against m.mbm # FIXME, this is for mbus, not using currently for wuhan
        if self.mbm != None and len(self.mbm) > 10:
            chk = ord(self.mbm[-2:-1]) # chksum as int
            sum = 0
            for bait in range(4, len(self.mbm)-2):
                sum += self.mbm[bait]
                sum = (sum & 0xFF)
            if sum == chk:
                return True
            else:
                log.warning('CRC problem! sum '+str(sum)+', chk '+str(chk))
                print('CRC problem! sum '+str(sum)+', chk '+str(chk)) ##
                return False

    def set_name(self, invar):
        self.name = invar

    def get_name(self):
        return self.name

    def get_port(self):
        return self.port

   
    def rd_chk(self, query=b'\x11\x01\x01\xED'): # FIXME / add crc chk
        ''' Sends the query, reads the response and checks the content '''
        try:
            self.tcpsocket.connect((self.tcpaddr, self.tcpport))
            self.tcpsocket.sendall(query) # saadame
            log.info("==> "+self.tcpaddr+":"+str(self.tcpport)+" "+str(query)) # naitame mida saatsime
            ready = select.select([self.tcpsocket], [], [], 1) # timeout 1 s.
            if ready[0]: # midagi on tulnud
                self.mbm = self.tcpsocket.recv(99) # kuulame # recv kasutame alles siis, kui data tegelikult olemas!
                self.tcpsocket.close()

            else:
                log.error('NO RESPONSE from co2 sensor')
                return 2
            if len(self.mbm) > 0:
                log.info('got a message from sensor, length ' + str(len(self.mbm)) + ' bytes: '+str(encode(self.mbm, 'hex_codec'))[:20])
                return 0
            else:
                log.warning('EMTPY answer from sensor device')
        except:
            log.error('FAILED TCP connection to '+self.tcpaddr)
            #traceback.print_exc()
            
        return 1


    def decode_co2(self): # wuhan
        '''co2 only from this model '''
        res = 0
        for i in range(2):
            res += int(str(self.mbm[4 - i])) << (i * 8)
        return res


    def get_all(self):
        '''Returns all or most measured values fot heat meters '''
        res = {}
        self.read() # self.mbm created
        res.update({ 'co2' : self.decode_co2() })
        #res.update({ 'temperature' : self.get_power() })
        #res.update({ 'humidity' : self.get_energy() })
        return res

    def set_co2(self, invar): # does not work for co2 only model
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
        ## self.ser.write(sendbytes) # serial
        time.sleep(1)
        ## res = self.ser.read(99) # serial
        if len(res) > 0:
            log.info('calibration response: '+str(encode(res, 'hex_codec'))[:20]) # something like b'160103e6'
            return 0
        else:
            log.warning('no answer from sensor device')
            return 1

    def read(self):
        ''' all together '''
        self.rd_chk()
        return self.decode_co2()
        
### END #######################################################
