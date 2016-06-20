# This Python file uses the following encoding: utf-8
'''
    co2, rh and T sensor from wuhan.cubic, gassensor.com.cn
    >>> from droidcontroller.wuhan_co2serial import *
    >>> s=Sensor(port='COM23')
    >>> s.rd_chk()
    0
    
    >>> s.decode_co2() # 
    787   
    
    >>> s.get_all() # 
    { 'co2' : 787, 'temperature' : 722, 'humidity' : 310 }
    
    >>> s.mbm
    b'\x16\t\x01\x02N\x02\xcb\x01h\x01\x00Y'

'''

from codecs import encode # for encode to work in py3
import time
import serial
import traceback
import struct  # struct.unpack for float from hex
import sys

import tornado.ioloop
from functools import partial
from concurrent.futures import ThreadPoolExecutor
EXECUTOR = ThreadPoolExecutor(max_workers=1)

import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO) ## kui imporditav main sisse, siis ylearune
log = logging.getLogger(__name__)

import serial.tools.list_ports
print('portlist',list(serial.tools.list_ports.comports()))
# [('/dev/ttyUSB1', 'FTDI TTL232R FTH8AIQ9', 'USB VID:PID=0403:6001 SNR=FTH8AIQ9')]

class Sensor:
    ''' Read wuhan co2 rh temp sensor plus possibly particles as well from another parallel sensor (pm2005 or pm2007) '''

    def __init__(self, msgbus=None, 
            svclist=[['TDV',1,'temperature'], ['HDV',1,'humidity'], ['CDV',1,'co2']], 
            port='/dev/ttyUSB0', autokey='FTDI', tout=2, speed=9600):  # win port like 'COM29'
        ports = list(serial.tools.list_ports.comports())
        self.msgbus = msgbus # publish to msgbus, if not None
        self.svclist = svclist # svc, member, id, name
        #found = 0
        if port == 'auto':
            try:
                for i in range(len(ports)):
                    if autokey in ports[i][1]:
                        #found = 1
                        self.port = ports[i][0]
            except:
                log.warning('USB port autodiscovery for Mbus FAILED, trying /dev/ttyUSB0')
                self.port = '/dev/ttyUSB0' 
        else: # no
            self.port = port

        self.tout = tout
        self.speed = speed
        self.model = None
        self.reopen() # self.ser = serial.Serial(self.port, self.speed, timeout=tout, parity=serial.PARITY_NONE) # also opening the port
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

    
    def reopen(self, tout=3, speed=9600):
        portlist = []
        ports = list(serial.tools.list_ports.comports())
        for i in range(len(ports)):
            portlist.append((ports[i][0], ports[i][1])) # list of tuples
        print('portlist',str(portlist))
        if '/dev/ttyUSB0' in str(portlist):
            self.port = '/dev/ttyUSB0'
        elif '/dev/ttyUSB1' in str(portlist):
            self.port = '/dev/ttyUSB1'
        try:
            self.ser = serial.Serial(self.port, self.speed, timeout=tout, parity=serial.PARITY_NONE) # also opening the ports
            log.info('reopened serial port '+self.port)
        except:
            log.error('FAILED to open serial port '+self.port)
        
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


    def rd_chk(self, query=b'\x11\x01\x01\xED'): # wuhan query for co2, temp, humidity / CM 1102
        ''' Sends the query, reads the response and checks the content '''
        try:
            self.ser.flushInput() # no garbage or old responses wanted
            self.ser.write(query) #
            time.sleep(0.5) # muidu ei tule jargmist vastust
            self.mbm = self.ser.read(99) #
            if len(self.mbm) > 0:
                log.info('got a message from sensor, length ' + str(len(self.mbm)) + ' bytes: '+str(encode(self.mbm, 'hex_codec')))
                return 0
            else:
                log.warning('no answer from sensor device, reopen serial port')
                self.reopen()
        except:
            log.error('USB port probably disconnected!! reopen serial port')
            self.mbm = ''
            self.errors += 1 # sure increase needed
            self.reopen()
        return 1
        

    def rd_chk_particles(self, query=b'\x11\x02\x0B\x01\xE1'): # wuhan query for particles PM 2005, 2007
        ''' Sends the query, reads the response and checks the content '''
        try:
            self.ser.flushInput() # no garbage or old responses wanted
            self.ser.write(query) #
            time.sleep(0.5) # muidu ei tule jargmist vastust
            self.mbm = self.ser.read(99) #
            if len(self.mbm) > 0:
                log.info('got a message from particle sensor, length ' + str(len(self.mbm)) + ' bytes: '+str(encode(self.mbm, 'hex_codec'))) # [:20])
                return 0
            else:
                log.warning('no answer from particle sensor device')
        except:
            log.error('USB port probably disconnected!!')
            self.mbm = ''
            self.errors += 1 # sure increase needed
        return 1
        

    def decode_co2(self): # wuhan
        res = 0
        for i in range(2):
            res += int(str(self.mbm[4 - i])) << (i * 8)
        return res

    def decode_temp(self): # wuhan
        res = 0
        for i in range(2):
            res += int(str(self.mbm[6 - i])) << (i * 8)
        return res - 512 # there is a stupid bias...

    def decode_hum(self): # wuhan
        res = 0
        for i in range(2):
            res += int(str(self.mbm[8 - i])) << (i * 8)
        return res

    def decode_part(self): # wuhan particles result decoding PM2.5, bytes 4..7 based on self.mbm ###
        if len(self.mbm) != 20:
            log.error('INVALID length of particle sensor response '+str(encode(self.mbm, 'hex_codec')))
            return None
        res1 = 0
        res2 = 0
        for i in range(4):
            res1 += int(str(self.mbm[6 - i])) << (i * 8)
            res2 += int(str(self.mbm[10 - i])) << (i * 8)
        alarm = int(str(self.mbm[15])) # chk 4 lsb
            
        return res1, res2, alarm

        
    def get_all(self):
        '''Returns all temp, hum co2 values as dict, based on self.mbm '''
        # svclist=[['TDV',1,'temperature'], ['HDV',1,'humidity'], ['CDV',1,'co2']]
        val = None
        res = {}
        
        for svc in self.svclist:
            if svc[2] == 'temperature':
                val = self.decode_temp()
            elif svc[2] == 'humidity':
                val = self.decode_hum()
            elif svc[2] == 'co2':
                val = self.decode_co2()
            else:
                log.error('invalid name '+svc[2]+' in self.svclist '+str(self.svclist))
                val = None
                
            if val != None:
                res.update({ svc[2] : val })
            if self.msgbus:
                self.msgbus.publish(svc[0], {'values': [ val ], 'status': 0}) # msgbus.publish(val_reg, {'values': values, 'status': status})
                #log.info('published '+str(svc[0])+', '+str( {'values': [ val ], 'status': 0}))
            #else:
                #log.info('no msgbus in use')
        self.mbm = '' # give valid response once after read
        return res # dict
        
        
    def set_part(self, cmd=b'\x11\x02\x06\x01\xE6'): # dynamic mode
        self.ser.flushInput() # no garbage or old responses wanted
        self.ser.write(cmd) #
        time.sleep(0.5) # muidu ei tule jargmist vastust
        res = self.ser.read(99) #
        if len(res) > 0:
            log.info('got a message from particle sensor, length ' + str(len(self.mbm)) + ' bytes: '+str(encode(self.mbm, 'hex_codec')))
            return 0
        else:
            log.warning('no answer from the particle sensor device')
            
    
    def get_part(self): 
        '''Returns PM values and alarms as dict '''
        ress = {}
        self.rd_chk_particles(query=b'\x11\x02\x0B\x01\xE1') # self.mbm created
        res=self.decode_part()
        ress.update({ 'pm25' : res[0] })
        ress.update({ 'pm100' : res[1] })
        ress.update({ 'thi' : (res[2] & 8) >> 3 }) # temperature too high
        ress.update({ 'tlo' : (res[2] & 4) >> 2 }) # temp lo
        ress.update({ 'shi' : (res[2] & 2) >> 1 }) # vent speed too high
        ress.update({ 'slo' : (res[2] & 1) }) # vent speed lo
        
        return ress
        

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
        print('data to write ', df1, df2, '=', df1*256+df2)
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
            log.info('calibration response: '+str(encode(res, 'hex_codec'))) # something like b'160103e6'
            return 0
        else:
            log.warning('no answer from sensor device')
            return 1

            
    # methods needed for async comm
    def run(self):
        self.read_async(self.async_reply)

    def read_async(self, reply_cb):
        log.info(" co2 data request send")
        EXECUTOR.submit(self.rd_chk).add_done_callback(lambda future: tornado.ioloop.IOLoop.instance().add_callback(partial(self.callback, future)))
        #eraldi threadis read_sync, mis ootab vastust.

    def callback(self, future):
        result = future.result()
        self.async_reply(result)

    def async_reply(self, res):
        log.info("    co2 sensor read result processing, rd_chk() exit status " + str(res))
        res = self.get_all() # using self.mbm, also publishes if msgbus in use
        log.info('decoded co2 sensor data: '+str(res))
        

##########################################################


