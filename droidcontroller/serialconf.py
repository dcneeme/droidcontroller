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
    def __init__(self, port='auto', autokey='FTDI', tout=4,
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
        log.warning('trying to reopen serial port '+self.port+' using speed '+str(speed)+', parity '+str(parity))
        self.ser.close()
        time.sleep(1)
        self.ser = serial.Serial(self.port, speed, timeout=self.tout, parity=parity) # that opens too


    def comm(self, send_string, expect_string='+ok', expect_size=120, delay=1, retries=5, line=1): # line index
        ''' Delay needed after every character! '''
        i=0
        res= ''
        #self.ser.flushInput()
        log.info('sending '+send_string) ##
        while not expect_string in res and i < retries:
            self.ser.flushInput()
            sys.stdout.write('.') # to see retries
            sys.stdout.flush()
            try:
                for char in send_string:
                    self.ser.write(char.encode('ascii'))
                    time.sleep(0.03)
                self.crlf()
                time.sleep(delay + i)
                #res = self.ser.read(expect_size).decode('utf-8').replace('\r\n',' ') # ascii codec will fail with bytes > 127
                res = self.ser.read(expect_size).decode('utf-8').replace('\r\n',' ').replace('\r','') # CR to be removed!
                #res = self.ser.readline().decode('utf-8').replace('\r','').replace('\n','') # this first line is command echo
                #if line == 1:
                #    res = self.ser.readline().decode('utf-8').replace('\r','').replace('\n','') # ascii codec will fail with bytes > 127
            except:
                res = ''
                log.debug('read FAILED!')
                #traceback.print_exc()d.doall()
                time.sleep(1)
            i += 1
        return res


    def crlf(self):
        self.ser.write('\r\n'.encode('ascii'))


    def set_mode(self): # ALWAYS INTO SER CONF, USE AT+Z TO TRANSPARENT!
        ''' test and set the mode '''
        self.reopen(self.speed, self.parity) # reopen at targeted speed, even if already using this
        print(str(self.ser))
        if self.model == 'WIFI232B':
            cmd='+++a'
        else:
            log.warning('unsupported model '+model)
            return 1

        res = self.comm(cmd, expect_string='+++', delay = 1, retries = 1, line = 0) # trying to get back command echo, no more lines coming
        if res == '': # wrong speed?
            log.info('trying initial speed, should connect if /reset is done'+str(self.ispeed))
            self.reopen(self.ispeed, self.iparity) # try factory default parameters 57k6 8N1
            print(str(self.ser))
            if self.model == 'WIFI232B':
                cmd='+++a'
            else:
                log.warning('UNKNOWN model '+self.model)
            res = self.comm(cmd, expect_string='+++', delay = 1, retries = 1)
            log.info(res)
            if res != '': # got some answer
                log.info('serial connectivity established at initial speed '+str(self.ispeed))

        return res


    def set_conf(self, retries=3):
        ''' write config as at command '''
        for key in self.conf:
            res = ''
            i = 0
            while not self.conf[key] in res and i < retries:
                sys.stdout.write('*') # to see retries
                sys.stdout.flush()
                cmd = 'AT+'+key+'='+self.conf[key]
                res = self.comm(cmd, expect_size = len(cmd)+7, delay = 1)
                i += 1
                log.info('   got '+res+'       ')
        self.comm('AT+Z') # restart
        print('module restarted, the communication at targeted speed and transparent mode can be tried soon')
        

    def get_conf(self):
        ''' read config via AT command '''
        for key in self.conf:
            res = self.comm('AT+'+key, delay=2.5) # do not use delay less than 3
            log.info('   got '+res)


    def get_networks(self):
        ''' List available WLANs and chk for connectivity '''
        res = self.comm('AT+WSCAN', expect_size=256)
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


