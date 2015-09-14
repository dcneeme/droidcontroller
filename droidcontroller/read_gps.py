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
gps.get_coordinates() # extracted from from gps.lines

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
        #found = 0
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
        self.ser = serial.Serial(self.port, self.speed, timeout=tout, parity=serial.PARITY_NONE) # also opening the port
        self.errors = 0 # every success zeroes
        self.gpsdata = '' # last message
        self.lines = []
        if self.ser.isOpen():
            log.info('ReadGps connection for model '+self.model+' successful on port '+self.port)
        else:
            log.error('ReadGps connection FAILED on port '+self.port)

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
                    log.debug('got from GPS device: '+str(self.gpsdata))

                lines = self.gpsdata.decode("utf-8").split('\r\n')
                log.debug('got '+str(len(lines))+' lines to decode')
                self.lines = lines
                return lines # self.gpsdata and self.lines are stored for debugging
            else:
                return None


        except:
            log.warning('FAILED to read GPS device at '+self.port)
            return None


    def decode(self, line):
        '''return decoded lat lng coordinates '''
        linevars = line.split(",")
        log.debug('linevars '+str(linevars)) ##
        if line[0:6] == '$GPGGA': # this line is complete and contains coordinates data
            #print('found GPGGA line: '+line) ##
            return self.getLatLng(linevars[2],linevars[4])
        elif line[0:6] == '$GPRMC':
            #print('found GPRMC line: '+line) ##
            return self.getLatLng(linevars[3],linevars[5])
        else:
            #log.warning('NO GPGGA or GPRMC in line '+line)
            return None


    def checksum(self, line): # FIXME
        checkString = line.split("*")
        checksum = 0
        for c in checkString[0].encode('utf-8'): # into bytes in py3!
            checksum ^= c
            print(checksum)

        try: # Just to make sure
            inputChecksum = int(checkString[1].rstrip(), 16);
        except:
            log.warning("Error in string, no CRC")
            return False

        if checksum == inputChecksum:
            return True
        else:
            log.warning("= Checksum error! =")
            log.warning(hex(checksum), "!=", hex(inputChecksum))
            return False



    def getTime(string,format,returnFormat):
        return time.strftime(returnFormat, time.strptime(string, format)) # Convert date and time to a nice printable format

    def getLatLng(self, latString, lngString):
        '''from https://gist.github.com/Lauszus/5785023 '''
        lat = float(latString[:2].lstrip('0') + "." + "%.7s" % str(float(latString[2:])*1.0/60.0).lstrip("0."))
        lng = float(lngString[:3].lstrip('0') + "." + "%.7s" % str(float(lngString[3:])*1.0/60.0).lstrip("0."))
        return lat, lng

    def getTime(self, string, format, returnFormat):
        return time.strftime(returnFormat, time.strptime(string, format)) # Convert date and time to a nice printable format

    def get_coordinates(self): # from self.lines
        ''' read and process until the first line with coordinates is found and decoded '''
        self.read() # into self.gpsdata and self.lines
        for line in self.lines:
            ##if self.checksum(line): $ FIXME
            res = self.decode(line)
            if res:
                return res

    ## END ##

