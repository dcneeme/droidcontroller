# use serial port COM11 for delta instrument
# send 'HA\r\n'
# read Date=2014/09/22 14:44:52;   622;     0;   49.8;   23.3;   999;  ERR. ;  ERR. ;  ERR. ;   12.3;   10.4;    8.9;   16.5;   46.0
''' to be used on pc with deltaohm meter connected via usb.
   sensors to be calibrate should be accessed via modbus.
   there is one service per metered value as reference 
   and others with reference value as the first member.
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

from droidcontroller.uniscada import UDPchannel
from droidcontroller.comm_modbus import CommModbus

class DeltaOhm(object):
    ''' Using DeltaOhm HD21AB17 as monitoring info source '''
    def __init__(self, port='auto', autokey='TUSB3410', tout=1,
            model='HD21AB17', conf={
                'DMC2W': [1, 1, 'co2 ppm', {0: [11, 1]}],
                'DMC1V': [2, 1, 'co ppm'],
                'DMHV': [3, 10, 'hum %'],
                'DMTW': [4, 10, 'temp degC', {0: [11, 2]}],
                'DMPV': [5, 1, 'pressure hPa']
            },
            speed=460800, parity='N',
            interval = 30,
            id = '010000000010',
            ip='195.222.15.51',
            mbiconf={0:'10.0.0.4:502'} # {0:'10.0.0.4:10001'} # wifi232B works in modbus proxy mode as well
            ):

        ''' in configuration one reference and several tested values can be described
            (colum, coeff, name] for ref and [mbi, mba, regadd] for tested value(s).
            channels to be tested are defined with mbiconf {mbi:'10.0.0.4:10001', mbi:'COM30|19200|E'} 
            use None for mbiconf if there are no channels to test.
            '''
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
        
        if mbiconf:
            self.mb = []
            self.host = []
            self.port = []
            for mbi in range(len(mbiconf)):
                if ':' in mbiconf[mbi]:
                    self.host.append(mbiconf[mbi].split(':')[0])
                    self.port.append(int(mbiconf[mbi].split(':')[1]))
                    self.mb.append(CommModbus(host = self.host[mbi], port = self.port[mbi]))
                #add serial here elif
                else:
                    log.warning('!! unsupported configuration block '+str(mbiconf[mbi]))
                    
                
        log.info('### setup done ####')
        
    
    def read(self):
        ''' return all available (defined in self.conf) values in a list format '''
        try:
            self.ser.write('HA\r'.encode('ascii')) # CR needed
            sss = 'id:'+self.id +'\n' # no in: here # voib ka ara jaada, siis lisab udpsend!
            time.sleep(0.5)
            res = self.ser.readline().decode('ascii')
            if len(res) < 100: # powered down?
                stop=1
                print('no deltaohm response')
                return None
            print(res)
        except:
            log.error('FAILURE to communicate with deltaohm')
            traceback.print_exc()
            return None
            
        # usb info olemas, nyyd lisaandurid
        
        cols = res.split(';')
        for svc in self.conf:
            print('svc',svc)
            #print(self.conf[svc])
            #print(eval(str(cols[self.conf[svc][0]])))
            #print(eval(str(self.conf[svc][1])))
            numvalue = int(eval(str(cols[self.conf[svc][0]])) * eval(str(self.conf[svc][1])))
            #sys.stdout.write(self.conf[svc][2]+' '+str(cols[self.conf[svc][0]])+' -> '+str(numvalue)+',   ') # to see retries
            sendstring =  svc+':'+str(numvalue) # starting the string for this service
            
            if len(self.conf[svc]) > 3: # channels to be tested present
                # 'DMC2W': [1, 1, 'co2 ppm', {0: [11, 1]}],
                dict2test = self.conf[svc][3] # all channels in one dict
                for mbi in dict2test: 
                    mba = dict2test[mbi][0]
                    reg = dict2test[mbi][1]
                    print('mbi,mba,reg',mbi,mba,reg) ##
                    i = 0
                    res = None
                    while res == None and i < 2:
                        try:
                            res = self.mb[mbi].read(mba, reg, 1)[0]
                        except:
                            log.warning('mbus comm FAILED, trying to recreate channels mbi '+str(mbi))
                            self.mb[mbi] = CommModbus(host = self.host[mbi], port = self.port[mbi])
                            time.sleep(0.5) # proovime kas asi paraneb
                            res = None
                    if res != None:
                        sendstring += ' '+str(res)
                    else:
                        sendstring = ''
                if sendstring != '':
                    sendstring += '\n'+svc[:-1]+'S:0\n' # status always 0 for now
            else: # one (reference) member only
                sendstring += '\n'+svc[:-1]+'S:0\n'
            sss += sendstring                
        return sss
        
        
    
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
        time.sleep(d.interval) # 60 s puhul ei pysi wifi232 yhendus!
        #time.sleep(10) # test
