# This Python file uses the following encoding: utf-8
# last change  6.9.2015, added crc chk

''' 
setup usr iot wifi232B modules from the serial port

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

class SerialConf:
    ''' Configure USR IOYT products via serial port '''
    def __init__(self, port='auto', autokey='FTDI', tout=1, speed=19200, parity='E', 
            model='WIFI232B',
            conf={
                'WANN':'static,10.0.0.4,255.255.255.0,10.0.0.253', 
                'WSSSID':'gembird', 
                'WSKEY':'WPA2PSK,AES,villakooguit',
                'NETP':'TCP,SERVER,10001,10.0.0.4'
            }
            ):
        
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
        self.conf = conf
        log.info(str(self.conf))
                    
        
    def comm(self, send_string, expect_string='ok'):
        ''' Delay needed after every character! '''
        i=0
        res= ''
        self.ser.flushInput()
        
        while not expect_string in res and i < 3:
            log.info('sending '+send_string) ##
            try:
                for char in send_string:
                    self.ser.write(char.encode('ascii'))
                    time.sleep(0.03)
                self.crlf()
                time.sleep(0.2)
                res = self.ser.read(80).decode('utf-8').replace('\r','').replace('\n','') # ascii codec will fail with bytes > 127
            except:
                res = 'read '+str(i+1)+' failed'
                #traceback.print_exc()
                time.sleep(0.5)
            i += 1
        return res
        
        
    def crlf(self):
        self.ser.write('\r\n'.encode('ascii'))

    
    def set_mode(self, conf=1):
        ''' test and set the mode '''
        if self.model == 'WIFI232B':
            if conf == 0:
                cmd = 'AT+ENTM'
            else:
                cmd='+++a'
        else:
            log.warning('unsupported model '+model)
            return 1
        
        res = self.comm(cmd)
        return res
            
    
    def set_conf(self):
        for key in self.conf:
            self.comm('AT+'+key+'='+self.conf[key])
            res = self.comm(key)
            log.info(res)
        
            
    def get_conf(self):
        for key in self.conf:
            res = self.comm('AT+'+key)
            log.info(res)
            
            
    def doall(self):
        self.set_mode(1) # switching into at command mode
        self.get_conf() # read current config
        self.set_conf() # set new config
        self.get_conf() # read new config
        self.set_mode(0) # ready for transparent communication
    
##########################################################
if __name__ == '__main__':
    w=WIFI232B()
    w.conf()
    

