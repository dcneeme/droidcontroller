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
    def __init__(self, port='auto', autokey='FTDI', tout=1,
            model='WIFI232B', conf={
                'UART': '9600,8,1,None,NFC',
                'FUDLX': 'on',
                'WANN': 'static,10.0.0.4,255.255.255.0,10.0.0.253',
                'WSSSID': 'gembird',
                'WSKEY': 'WPA2PSK,AES,villakooguit',
                'WMODE': 'sta',
                'NETP': 'TCP,SERVER,10001,10.0.0.4'
            },
            ispeed=57600, iparity='N'
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
        self.speed = int(conf['UART'].split(',')[0])
        if 'Even' in conf['UART']:
            self.parity = serial.PARITY_EVEN
            self.pars = 'Even'
        elif 'None' in conf['UART']:
            self.parity = serial.PARITY_NONE
            self.pars = 'None'
        else:
            log.warning('UNKNOWN parity '+parity)

        self.ispeed = ispeed
        if iparity == 'E':
            self.iparity = serial.PARITY_EVEN
            #self.ipars = 'Even' # no need
        elif iparity =='N':
            self.iparity = serial.PARITY_NONE
            #self.ipars = 'None'
        else:
            log.warning('UNKNOWN iparity '+iparity)

        self.model = model
        self.ser = serial.Serial(self.port, self.speed, timeout=self.tout, parity=self.parity) # also opening the port
        #self.errors = 0 # every success zeroes
        self.conf = conf
        log.info(str(self.conf)+', speed '+str(self.speed)+', ispeed '+str(self.ispeed))


    def reopen(self, speed, parity):
        ''' Try other speed and parity on the same port '''
        print('trying to reopen serial port '+self.port+' using speed '+str(speed)+', parity '+str(parity))
        self.ser.close()
        time.sleep(1)
        self.ser = serial.Serial(self.port, speed, timeout=self.tout, parity=parity) # that opens too


    def comm(self, send_string, expect_string='+', expect_size=120, delay=1, retries=3): # line index
        ''' Delay needed after every character! '''
        i=0
        res= ''
        #self.ser.flushInput()
        log.debug('sending '+send_string) ##
        while not expect_string in res and i < retries:
        #while res == '' and i < retries: # TEST
            self.ser.flushInput()
            sys.stdout.write('.') # to see retries
            sys.stdout.flush()
            try:
                res = '' # response string, bytes
                for char in send_string:
                    self.ser.write(char.encode('ascii'))
                    time.sleep(0.01)
                    res = self.ser.read(1).decode('utf-8') # echo
                    sys.stdout.write(res) # to see retries
                    sys.stdout.flush()
                self.crlf()
                res = ''
                j = 0
                while res == '' and j < 5:
                    res = self.ser.read(1).decode('utf-8')
                    sys.stdout.write(',') # to see retries
                    sys.stdout.flush()
                    j += 1
                time.sleep(delay)
                res = self.ser.read(120).decode('utf-8').replace('\r\n',' ').replace('\r','').replace('\n','') # .split('+')[1] # 
                
            except:
                res = ''
                log.debug('read FAILED!')
                #traceback.print_exc()d.doall()
                time.sleep(1)
            i += 1
        return res


    def crlf(self):
        self.ser.write('\r\n'.encode('ascii'))
        

    def conn(self):
        ''' try +++a '''
        print(str(self.ser))
        
        if self.model == 'WIFI232B':
            cmd='+++a'
        else:
            log.warning('unsupported model '+model)
            return 1
        
        res = '' # response string, bytes
        self.ser.flushInput()
        self.ser.write('+++'.encode('ascii'))
        time.sleep(0.1)
        try:
            res = self.ser.read(1).decode('utf-8') # echo
        except:
            traceback.print_exc() # pass
        
        if res == '+': # already in at cmd mode
            print('device already in at mode')
            self.crlf() # finish the cmd
            time.sleep(0.1)
            self.ser.flushInput()
        elif res == 'a': # switching int at cmd mode
            print('switching to at mode')
            time.sleep(0.1)
            self.ser.write('a'.encode('ascii'))
            time.sleep(0.1)
            res = self.ser.read(3).decode('utf-8')
        else:
            log.debug('invalid read result from serial, res='+str(res))
            res = '' # fail
        if res != '':
            print('conn: connected, res='+res)
            return 0
        else:
            log.warning('FAILED to get serial connectivity at this time')
            return 1
        
        
    def set_mode(self): # ALWAYS TO SER CONF, USE AT+Z or AT+ENTM TO get into TRANSPARENT mode!
        ''' test and set the mode to AT command '''
        self.reopen(self.speed, self.parity) # reopen at targeted speed, even if already using this
        res = self.conn()
        if res != 0: # no success with current speed
            print('trying to connect at speed '+str(self.ispeed))
            self.reopen(self.ispeed, self.iparity) # try factory default parameters 57k6 8N1
            res = self.conn()
            
        if res != 0: # no success with current speed
            log.info('FAILED to connect with '+self.model+'. try /reset!')
            return 1
        else:
            print('connected')        
        return 0

    
    def reset_mode(self): # back to tr5ansparent
        cmd='AT+ENTM'
        res = self.comm(cmd, expect_string='+ok', delay = 1, retries = 2)
        print(res)
        
        
    def set_conf(self, retries=3):
        ''' write config as at command '''
        for key in self.conf:
            res = ''
            i = 0
            #while not self.conf[key] in res and i < retries:
            #    sys.stdout.write('*') # to see retries
            #    sys.stdout.flush()
            #    cmd = 'AT+'+key+'='+self.conf[key]
            #    res = self.comm(cmd, expect_size = len(cmd)+7, delay = 1)
            #    i += 1
            #    print('   got '+res)
            cmd = 'AT+'+key+'='+self.conf[key]
            res = self.comm(cmd, expect_string='+ok', delay=3)
            print('   got '+res)
        time.sleep(1)
        self.comm('AT+Z') # restart
        print('module restarted, the communication at targeted speed and transparent mode can be tried soon')
        

    def get_conf(self):
        ''' read config via AT command '''
        for key in self.conf:
            res = self.comm('AT+'+key, delay = 0) # do not use delay less than 3
            print('   got '+res)


    def get_networks(self):
        ''' List available WLANs and chk for connectivity '''
        res = self.comm('AT+WSCAN', expect_size=512, delay = 5)
        print(res)
        #res = self.comm('AT+TCPLK')
        #print(res)


    def doall(self):
        ''' read, write, read configuration '''
        self.set_mode() # switching into at command mode, changing speed/parity if needed
        self.get_conf() # read current config
        print('going to write new configuration\n')
        self.set_conf() # set new config
        #self.comm('AT+Z') # restart
        print('wait for module restart\n')
        time.sleep(10)
        self.set_mode() # switching into at command mode
        self.get_conf() # read new config

##########################################################
if __name__ == '__main__':
    w = SerialConf()
    w.doall()


