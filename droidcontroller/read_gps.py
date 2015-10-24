# This Python file uses the following encoding: utf-8
# last change  6.9.2015, added crc chk

'''
read_gps.py - query GPS device via USB port, normally at 4800 8N1
 usage:
from droidcontroller.read_gps import *
gps = ReadGps()
gps.read()
gps.gpsdata
gps.lines
line='$GPGGA,164123.000,5925.5067,N,02436.8130,E,1,04,9.1,-13.1,M,19.8,M,,0000*4B'
gps.decode(line)
gps.get_coordinates() # do all

see nmea infot at http://www.gpsinformation.org/dale/nmea.htm#RMC
use the following 2 linetypes IF they consist data (some numbers may be missing if not ready)

invalid data until fixed:
'$GPRMC,122033.069,V,,,,,,,240915,,,N*48'
'$GPGGA,122034.056,,,,,0,00,,,M,0.0,M,,0000*53'

fixed data:
$GPRMC,132733.000,A,5925.4861,N,02436.8034,E,0.00,126.97,240915,,,A*65  # note A = active
$GPGGA,132734.000,5925.4861,N,02436.8034,E,1,05,1.7,16.0,M,19.8,M,,0000*64 # note 1 after E

The reader must blink if position is fixed !!!
'''

from codecs import encode # for encode to work in py3
import time
import serial
import traceback
import re

import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

import serial.tools.list_ports
print(list(serial.tools.list_ports.comports()))
# [('/dev/ttyUSB1', 'FTDI TTL232R FTH8AIQ9', 'USB VID:PID=0403:6001 SNR=FTH8AIQ9')] # pl2303

class ReadGps:
    ''' Read and decode GPS data from serial port. Return lat lng coordinates. '''
    def __init__(self, port='auto', autokey='Prolific', tout=1, speed=4800, model='PL2303'):
        ports = list(serial.tools.list_ports.comports())
        self.port = None
        if port == 'auto':
            try:
                for i in range(len(ports)):
                    if autokey in ports[i][1]:
                        #found = 1
                        self.port = ports[i][0]
            except:
                log.warning('USB port autodiscovery for GPS device FAILED')

        else: # not auto
            self.port = port

        self.tout = tout
        self.speed = speed
        self.model = model
        self.lines = []
        if self.port != None:
            try:
                self.ser = serial.Serial(self.port, self.speed, timeout=tout, parity=serial.PARITY_NONE) # also opening the port
                self.errors = 0 # every success zeroes
                self.gpsdata = '' # last message
                
                if self.ser.isOpen():
                    log.info('ReadGps connection for receiver model '+self.model+' successful on port '+self.port)
                else:
                    log.error('ReadGps connection FAILED on port '+str(self.port)) # port can be None!!
            except:
                log.warning('NO suitable USB port found!')
                #self.close()
        else:
            log.warning('GPS port None...')
            #self.close()

    def close(self):
        ''' Use this to get rid of the instance if not required '''
        self.__del__()

    def __del__(self):
        ''' Destroyer for close() '''
        class_name = self.__class__.__name__
        log.info(class_name+' destroyed')

    def reopen(self): # try to restore serial channel
        ''' Attempt to restore failing USB port by closing and reopening '''
        log.warning('trying to restore ReadGps connectivity by closing and reopening serial port '+self.port)
        self.ser.close()
        time.sleep(1)
        self.ser.open()

    def set_model(self, invar):
        self.model = invar

    def get_model(self):
        return self.model

    def get_port(self):
        return self.port

    def get_errors(self):
        return self.errors


    def read(self):
        ''' Reads the serial buffer and splits it into various lines. Some lines contain lat+lng data. '''
        try:
            if self.ser.inWaiting() > 420: # do not read if not enough data
                self.gpsdata = self.ser.read(420) # in this block a few lines with coordinates must exist
                self.ser.flushInput() # flush the rest
                if len(self.gpsdata) > 10:
                    log.debug('got from GPS device: '+str(self.gpsdata)) ##

                lines = self.gpsdata.decode("utf-8").split('\r\n')
                log.debug('got '+str(len(lines))+' lines to decode') ##
                self.lines = lines
                return lines # self.gpsdata and self.lines are stored for debugging
            else:
                return None


        except:
            log.warning('FAILED to read GPS device at '+str(self.port)) # port can be None
            return None


    def decode(self, line):
        ''' 
            return decoded lat lng coordinates 
            DDDMM.SSSS ("Degrees, minutes, seconds") format used in the NMEA protocol
            use RMC or GGA (complete) member of the following
            ['$GPGGA,133137.000,5925.4915,N,02436.8032,E,1,07,1.2,3.1,M,19.8,M,,0000*56', '$GPGSA,A,3,22,08,04,27,11,14,18,,,,,,2.9,1.2,2.6*3B', '$GPRMC,133137.000,A,5925.4915,N,02436.8032,E,0.00,26.40,240915,,,A*59', '$GPGGA,133138.000,5925.4915,N,02436.8032,E,1,07,1.2,3.1,M,19.8,M,,0000*59', '$GPGSA,A,3,22,08,04,27,11,14,18,,,,,,2.9,1.2,2.7*3A', '$GPRMC,133138.000,A,5925.4915,N,02436.8032,E,0.00,26.40,240915,,,A*56', '$GPGGA,133139.000,5925']
        '''
        #msg = pynmea2.parse(line)
        #log.info('parse output '+str(msg))
        #lat = msg.latitude
        #lon = msg.longitude
        #return lat, lon
    
        '''return decoded lat lng coordinates '''
        linevars = line.split(",")
        log.debug('linevars '+str(linevars)) ##
        if line[0:6] == '$GPGGA' and linevars[6] != '0': # this line is complete and contains coordinates data
            log.debug('found GPGGA line: '+line) ##
            return self.getLatLng(linevars[2],linevars[4])
            
        if line[0:6] == '$GPRMC' and linevars[2] != 'V':
            log.debug('found GPRMC line: '+line) ##
            return self.getLatLng(linevars[3],linevars[5])
            
        else:
            #log.warning('NO $GPRMC or GPRMS found in '+line)
            return None


    def checksum(self, line): # FIXME
        checkString = line.split("*")
        checksum = 0
        bstring= checkString[0].encode('utf-8') # into bytes in py3!
        for i in range(len(bstring)):
            checksum ^= bstring[i]
            
        try: # Just to make sure
            inputChecksum = int(checkString[1].encode('utf-8'), 16)
        except:
            log.warning("Error in string, no CRC")
            return False

        if checksum == inputChecksum:
            log.info('crc ok') ##
            return True
        else:
            log.warning('Checksum ERROR: ' + hex(checksum) + ' != ' + hex(inputChecksum))
            return False



    def getTime(string,format,returnFormat):
        return time.strftime(returnFormat, time.strptime(string, format)) # Convert date and time to a nice printable format

    def getLatLng(self, latString, lngString):
        '''from https://gist.github.com/Lauszus/5785023 '''
        log.debug(' latstring: '+latString+', lngstring: '+lngString)
        lat = float(latString[:2].lstrip('0') + "." + "%.7s" % str(float(latString[2:]) / 60.0).lstrip("0."))
        lng = float(lngString[:3].lstrip('0') + "." + "%.7s" % str(float(lngString[3:])/ 60.0).lstrip("0."))
        return lat, lng

    def getTime(self, string, format, returnFormat):
        return time.strftime(returnFormat, time.strptime(string, format)) # Convert date and time to a nice printable format

    def get_coordinates(self): # from self.lines
        ''' read and process until the first line with coordinates is found and decoded '''
        self.read() # into self.gpsdata and self.lines
        res = None
        for line in self.lines[1:-1]: # skip first and last
            #if self.checksum(line): # FIXME
            res = self.decode(line)
            if res:
                return res

    ## END ##

