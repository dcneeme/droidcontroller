# update pic firmware from hex file by writing modbus register regadd
# usage windows: python pic_update.py 1 0 COM31 IOplaat.hex
# usage linux: python pic_update.py 1 0 /dev/ttyUSB0 IOplaat.hex  

#998 multikulti slave id (2 baiti koos) ja dddd 
#vastab ok, bootloaderisse
#saata 998 multikulti
#kui 3 korda ei ole ok multikulti kirjutamine, siis pea 30s pausi ja alusta algusest

import traceback
import os
import sys
from pymodbus import *
#from droidcontroller.comm_modbus import CommModbus  #  for linux

import time
import logging
log = logging.getLogger(__name__)

''' PIC uploader via modbus. Send  hex file lines as modbus multiwrite commands, without hex crc,
    stripping ":" from the beginning and CRC plus CRLF from the end.
    Usage: 
    python pic_udate.py 1 0 COM26 ioplaat.hex
    or 
    python pic_udate.py 1 0 192.168.1.102:10502 ioplaat.hex
    or
    python pic_update.py 1 0 /dev/ttyUSB0 IOplaat.hex
    where 1=mba, 0=device id, 0 by default 
'''
class PicUpdate:
    ''' Class for updating PIC microcontrollers with new firmware.
        Sending hex file rows as binary string, withour CRC and leading colon.
    ''' 
        
    def __init__(self, mba=1, regadd=998, port='COM31', id=0, keepconf=1): # **kwargs): #
        ''' mb[0] should exist already '''
        self.mba = mba
        self.regadd = regadd
        self.pic_id = id # pic one time writable LSBs in registers 258 and 259 put together as (msb,lsb)
        self.keepconf = keepconf # overwriting data eeprom if 0. may change modbus address and device serno!
        self.skipsend = 0 # this becomes 1 for 


    def upload(self, filename='pic_update_test.hex'):
        ''' Upload converted to binary hex file, row by row as binary strings,
            stripping : from the beginning and CRC plus CRLF from the end.
            In the case of odd number of bytes the LSB of the last register written is
            fulfilled with CRC.
        '''
        res = 0 # return code
        if os.path.isfile(filename):
            log.debug('hex file '+filename+' found')
        else:
            log.warning('hex file '+filename+' NOT found')
            return 1

        lines = [line.rstrip().strip(':') for line in open(filename,'r')]
        for line in lines:
            hexlen = len(line) - 2 # skip crc
            #print('line', line, 'regcount, reminder', hexlen / 4, hexlen % 4) # debug
            regcount = hexlen / 4
            regword = []
            reghex = ''
            if hexlen % 4 > 0: # last word incomplete
                regcount += 1
                #line = line + 'FF' # pole vaja, saadab nagunii crc

            for regnum in range(regcount): # index 0...count-1
                hexpiece = line[4 * regnum : 4 * regnum + 4]
                regword.append(int(hexpiece, 16)) #  2bytes into one word
                reghex += ' '+format("%04x" % regword[regnum])
                
            if self.keepconf == 1: # skip data EEPROM lines
                if '0200 0004 0030' in reghex[0:16] or '1000 0000 0100' in reghex[0:16]: # cpu conf & data area 
                    self.skipsend = 1
                if '0000 0001' in reghex[0:11]: # last line MUST be sent
                    self.skipsend = 0
                
            if self.skipsend == 0:
                print('sending to reg '+str(regadd)+': ' + reghex) # , regword) # FIXME
                try:
                    mb[0].write(mba,regadd, values=regword) # sending to pic
                    #time.sleep(0.05) # give some time to save portion of flash?
                except:
                    print('modbus write failure, mb',mb)
                    res += 1
            else:
                print('skipping line: '+reghex)
                
        return res # 0 if ok


##################   MAIN  #####################
 

   
if __name__ == '__main__': # parameters mba regadd host:port|tty filename
    logging.basicConfig(level=logging.WARNING)
    try:
        mba = int(sys.argv[1])
        regadd = 998 # testimiseks kasuta 400
        pic_id = int(sys.argv[2]) # koos reg 58 ja 259 sisu nagu MSB LSB
        host = sys.argv[3]
        if ':' in host:
            host = host.split(':')[0]
            port= int(host.split(':')[1])
        else:
            port = host
        filename = sys.argv[4] # hex fail
        
    except:
        log.warning('missing or invalid parameters')
        sys.exit()

    
    try:
        if mb[0]:
            log.info('modbus connection already existing')
            pass
    except:
        #    self.mb=CommModbus()  # define in comm_modbus2
        mb = []
        from comm_modbus3 import *  # # for PC
        mb.append(CommModbus(port=port)) # PC jaoks
        log.info('modbus connection created')
 
 
    up = PicUpdate(mba, regadd, port, pic_id) # kwargs?

    print('going to switch pic with id '+str(pic_id)+' into bootloader mode')
    try:
        res = mb[0].write(mba,regadd,values=[pic_id, 0xdddd])
        print('bootloader started')
    except:
        print('mode switching FAILED, response '+str(res))
        sys.exit()
        
    time.sleep(3)
    
    start = time.time()
    print('going to send ' + filename + ' to ' + host + ', mba ' + str(mba) + ', regadd '+ str(regadd)+ ', pic_id '+ str(pic_id))
    res = up.upload(filename) # hex faili saatmine registrisse 998 yks rida korraga
    if res == 0:
        print('upload done in '+str(int(time.time() - start))+' s, waiting for pic restart...')
        time.sleep(10) # 4 on vahe!
        try:
            uptime = mb[0].read(mba,498,2)[1] # read 32 bit always, use LSB
            if uptime < 10 and uptime > 0:
                print('upload done, pic autorestarted and responsive')
            else:
                log.warning('pic uptime incorrect: ' + str(uptime))
        except:
            print('upload FAILED, pic still in bootloader mode')
    else:
        print('upload FAILED, pic still in bootloader mode')
