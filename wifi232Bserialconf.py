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
#print(list(serial.tools.list_ports.comports()))
# [('/dev/ttyUSB1', 'FTDI TTL232R FTH8AIQ9', 'USB VID:PID=0403:6001 SNR=FTH8AIQ9')]

class SerialConf:
    ''' Configure USR IOT products via serial port
        If setting wskey is not successful, comment the according update line below and set manually via web while in AP mode
        passwd Pargi.09 for Lasteaed
    '''
    def __init__(self, port='auto', autokey='FTDI', tout=1,

        ip='10.0.0.4', defgw='10.0.0.253', speed=9600, parity='None',
            ssid='gembird', passwd='villakooguit', model='WIFI232B', conf={
                'FUDLX': 'on',
                'WMODE': None,
                'WEBU': 'admin,hoira',
            },
            ispeed=57600, iparity='N', aes_tkip='aes'
            ): # veebist yle 5 margi panna ei saanud, at kasuga saab! proovitud 10
        self.ip = ip # to be used for ping
        self.defgw = defgw # to be used for ping

        conf.update({'UART': str(speed)+',8,1,'+parity+',NFC'})
        conf.update({'WANN': 'static,'+ip+',255.255.255.0,'+defgw}) # sta mode network params
        conf.update({'WSSSID': ssid})
        conf.update({'WSKEY': 'wpa2psk,'+aes_tkip+','+passwd}) # min 8 chars
        conf.update({'NETP': 'TCP,Server,10001,10.10.100.100'}) # EI TAHA OMA IP?
        # kiirus peale factory default resetti on 57600
        print(str(conf))

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


    def comm(self, send_string, expect_string='+', delay=0.5, retries=10, silent=False): # line index
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
                for char in send_string: # send loop
                    self.ser.write(char.encode('ascii'))
                    time.sleep(0.005)
                    res = self.ser.read(1).decode('utf-8') # get echo
                    sys.stdout.write(res) # see the echoes
                    sys.stdout.flush()
                self.crlf()
                res = ''
                got = 0
                minsize = 6

                j = 0
                sys.stdout.write(' ') # delimit from command
                while res == '' and j < 100: # receive loop
                    time.sleep(0.1)
                    inbytes = self.ser.inWaiting()
                    if inbytes > minsize: # '\r\n\r+ok=WPA2PSK,AES,villakooguit\r\n\r\n'
                        got = 1
                        break # read all with timeout
                    else:
                        if got == 0: # still waiting
                            sys.stdout.write('.') # to indicate waiting
                            sys.stdout.flush()
                        else: # got == 1 but got no more
                            break
                    j += 1
                time.sleep(delay) # time to get the whole message
                res = self.ser.read(256).decode('utf-8')
                if not silent:
                    sys.stdout.write(' '+res.replace('\r\n',' ').replace('\r','').replace('\n','')+'\n') ## to see every answer during retries
                    sys.stdout.flush() ##
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
            time.sleep(0.2)
            self.ser.flushInput()
            res= ' '
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
            #print('conn: connected, res='+res)
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
            print('serial connected')
        return 0


    def reset_mode(self): # back to transparent
        cmd='AT+ENTM'
        res = self.comm(cmd, expect_string='+ok', delay = 1, retries = 2)
        print(res)


    def set_2ap(self):
        ''' sets to ap mode '''
        self.comm('AT+WMODE=AP')
        self.comm('AT+Z')

    def set_2sta(self):
        ''' sets to sta mode '''
        self.comm('AT+WMODE=sta')
        self.comm('AT+Z')



    def set_conf(self):
        ''' write config as at command '''
        for key in self.conf:
            if self.conf[key] != None:
                res = ''
                i = 0
                cmd = 'AT+'+key+'='+self.conf[key]
                res = self.comm(cmd, expect_string='+ok', delay=2).replace('\r\n',' ').replace('\r','').replace('\n','')[1:] # avoid cr, lf
                #print('   got '+res)
        time.sleep(1)
        self.comm('AT+WMODE=sta') # sta moodi
        self.comm('AT+Z') # restart salvestamiseks/joustamiseks
        print('module restarted, the communication at targeted speed and transparent mode can be tried soon')


    def get_conf(self):
        ''' read config via AT command '''
        for key in self.conf:
            self.comm('AT+'+key, delay = 0.1).replace('\r\n',' ').replace('\r','').replace('\n','')[1:] # avoid cr & lf here, cut first chars
            #print('   got '+res)


    def get_networks(self):
        ''' List available WLANs and chk for connectivity '''
        res = self.comm('AT+WSCAN', delay = 5, silent=True)
        print(res)
        #res = self.comm('AT+TCPLK')
        res = self.comm('AT+WSLK') # connected to...
        res = self.comm('AT+WSLQ') # link quality
        res = self.comm('AT+PING='+self.ip) # test
        res = self.comm('AT+PING='+self.defgw) # test 2
        #print(res)


    def doall(self):
        ''' read, write, read configuration '''
        self.set_mode() # switching into at command mode, changing speed/parity if needed
        ##self.get_conf() # read current config
        print('going to write new configuration\n')
        self.set_conf() # set new config and restarts
        print('wait for module restart\n')
        time.sleep(10)
        self.set_mode() # switching into at command mode
        self.get_conf() # read new config
        self.get_networks() # show networks

##########################################################
if __name__ == '__main__':
    w = SerialConf()
    w.doall()


