# use serial port COM11 for delta instrument
# send 'HA\r\n'
# read Date=2014/09/22 14:44:52;   622;     0;   49.8;   23.3;   999;  ERR. ;  ERR. ;  ERR. ;   12.3;   10.4;    8.9;   16.5;   46.0

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

from droidcontroller.uniscada import UDPchannel

class DeltaOhm(object):
    ''' Using DeltaOhm HD21AB17 as monitoring info source '''
    def __init__(self, port='auto', autokey='TUSB3410', tout=1,
            model='HD21AB17', conf={
                'DMC2V': [1, 1, 'co2 ppm'],
                'DMC1V': [2, 1, 'co ppm'],
                'DMHV': [3, 10, 'hum %'],
                'DMTV': [4, 10, 'temp degC'],
                'DMPV': [5, 1, 'pressure hPa']
            },
            speed=460800, parity='N',
            interval = 60,
            id = '010000000010',
            ip='195.222.15.51'
            ):

        self.interval = interval # between readings
        self.id = id # monitooringus host
        ports = list(serial.tools.list_ports.comports())
        #found = 0
        if port == 'auto':
            try:
                for i in range(len(ports)):
                    if autokey in ports[i][1]:
                        #found = 1
                        self.port = ports[i][0]
            except:
                log.warning('USB port autodiscovery FAILED')
                self.port = '/devAMA0' # console
        else: # no
            self.port = port

        self.tout = tout

        self.speed = speed
        if parity == 'E':
            self.parity = serial.PARITY_EVEN
            #self.ipars = 'Even' # no need
        elif parity =='N':
            self.parity = serial.PARITY_NONE
            #self.ipars = 'None'
        else:
            log.warning('UNKNOWN parity '+parity)

        self.model = model
        self.ser = serial.Serial(self.port, self.speed, timeout=self.tout, parity=self.parity) # also opening the port
        #self.errors = 0 # every success zeroes
        self.conf = conf
        
        self.udp = UDPchannel(id=id, ip=ip)

    
    def read(self):
        ''' return all available (defined in self.conf) values in a list format '''
        try:
            self.ser.write('HA\r'.encode('ascii')) # CR needed
            sendstring = 'id:'+self.id +'\n' # no in: here
            time.sleep(0.5)
            res = self.ser.readline().decode('ascii')
            if len(res) < 100: # powered down?
                stop=1
                print('no deltaohm response')
                return None
            print(res)

            cols = res.split(';')
            for svc in self.conf:
                #print(svc)
                #print(self.conf[svc])
                #print(eval(str(cols[self.conf[svc][0]])))
                #print(eval(str(self.conf[svc][1])))
                numvalue = int(eval(str(cols[self.conf[svc][0]])) * eval(str(self.conf[svc][1])))
                sys.stdout.write(self.conf[svc][2]+' '+str(cols[self.conf[svc][0]])+' -> '+str(numvalue)+',   ') # to see retries
                sendstring +=  svc+':'+str(numvalue)+'\n'+svc[:-1]+'S:0\n'
            sys.stdout.write('\n')
            sys.stdout.flush()
            return sendstring
        except:
            log.error('FAILURE to communicate with deltaohm')
            traceback.print_exc()
            return None
        
    
    def comm(self, sendstring):
        self.udp.udpsend(sendstring = sendstring, age = 0)
        time.sleep(2)
        self.udp.udpread()
        
        
#############################################################################
d = DeltaOhm()
if __name__ == '__main__':
    while True:
        ss = d.read()
        if ss != None:
            d.comm(ss)
        else:
            log.error('communication FAILURE with deltaohm, trying close/open')
            try:
                d.ser.close()
                d.ser.open()
            except:
                log.error('FAILED to close or open serial port!')
        time.sleep(d.interval)
        #time.sleep(5) # test
