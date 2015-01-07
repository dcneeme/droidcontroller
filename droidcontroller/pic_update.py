# update pic firmware from hex file by writing modbus register regadd
# usage windows: python pic_update.py 1 0 COM31 IOplaat.hex
# usage linux: python pic_update.py 1 0 /dev/ttyUSB0 IOplaat.hex

#998 multikulti slave id (2 baiti koos) ja dddd
#vastab ok, bootloaderisse
#saata 998 multikulti
#kui 3 korda ei ole ok multikulti kirjutamine, siis pea 30s pausi ja alusta algusest

## NB! mitme plaadi puhul kasuta mbi muutujat! modbus kanal mb[mbi]

import traceback
import os
import sys
from droidcontroller.sqlgeneral import *

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

class PicUpdate(SQLgeneral): # using modbus connections mb[] created by sqlgeneral
    ''' Class for updating PIC microcontrollers with new firmware.
        Sending hex file rows as binary string, withour CRC and leading colon.
    '''

    def __init__(self, mbi=0, mba=1, regadd=998, id=0, keepconf=1): # **kwargs): #
        ''' mb[self.mbi] may exist already '''
        self.skipsend = 0 # this becomes 1 for data eeprom
        self.set_params(mbi, mba, regadd, id, keepconf)
        
    def set_params(self, mbi=0, mba=1, regadd=998, id=0, keepconf=1):
        ''' Change the modbus address of the io-board to update '''
        self.mbi = mbi
        self.mba = mba
        self.regadd = regadd
        self.pic_id = id
        self.keepconf = keepconf # overwriting data eeprom if 0. may change modbus address and device serno!
        log.info('target modbus channel and address for the updater set to mbi.mba '+str(self.mbi)+'.'+str(self.mba))


    def get_params(self):
        ''' Returns effective parameters '''
        return self.mbi, self.mba, self.regadd, self.pic_id, self.keepconf
        
    
    def upload_hex(self, filename='IOplaat.hex'):
        ''' Upload the hex file (converted to binary on the way), row by row as binary strings,
            stripping : from the beginning and CRC plus CRLF from the end.
            In the case of odd number of bytes the LSB of the last register written is
            fulfilled with CRC.
        '''
        res = 0
        linetrymax = 3
        #i = 0

        if os.path.isfile(filename):
            log.info('hex file '+filename+' found')
        else:
            log.warning('hex file '+filename+' NOT found')
            return 1

        lines = [line.rstrip().strip(':') for line in open(filename,'r')]
        for line in lines:
            i = 0 # line retry counter
            hexlen = len(line) - 2 # skip crc
            regcount = int(hexlen / 4) # taisarv peab olema
            regword = []
            reghex = ''
            if hexlen % 4 > 0: # last word incomplete
                regcount += 1
                #line = line + 'FF' # pole vaja, kasutame crc kui bait puudu

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
                log.info('sending to reg '+str(self.regadd)+': ' + reghex)
                while i < linetrymax: # retry once
                    i += 1
                    print('attempt '+str(i)+' to write mba '+str(self.mba)+' reg '+str(self.regadd)+' values ' +str(regword))
                    res = mb[self.mbi].write(self.mba, self.regadd, values=regword) # sending to pic   #######################
                    time.sleep(0.01) # igaks juhuks
                    if res == 0: # ok
                        log.info('line '+reghex+' written')
                        break
                    else:
                        time.sleep(1) 
                else:
                    log.warning('line upload FAILED after '+str(i)+' tries, res '+str(res))
                    
                if res > 0: # write not ok
                    print('upload_hex FAILED, res '+str(res)+', breaking the upload loop, wait and retry')
                    time.sleep(10) # 30 s?
                    break
                    
                #time.sleep(0.05) # give some time to save portion of flash? nno need, pic response means ready for next

            else:
                log.info('skipping data eeprom line: '+reghex)

        else:
            print('file '+filename+' upload successful')
        
        return res # 0 if ok


    def update(self, pic_id=0, filename='IOplaat.hex'):
        ''' Starts and stops the upload process. pic id is 0 if not stored into registers  '''
        res = 0 # return code, 0 = ok
        log.info('going to switch pic with id '+str(pic_id)+' into bootloader mode')
        if pic_id != 0:
            self.pic_id = pic_id

        try:
            res = mb[self.mbi].write(self.mba, self.regadd, values=[self.pic_id, 0xdddd])
            if res == 0: # ok
                log.info('bootloader for pic with id '+str(self.pic_id)+' started')
            else: # viivitas vastusega yle 0.5 s
                res = mb[self.mbi].read(self.mba,1,1) # eg ena loetav pole tavaline reg
                if res == 0: # ikka normal
                   log.warning('bootloader for pic with id '+str(self.pic_id)+' NOT started, still in normal mode!')
                   return 100
                else:
                    log.info('bootloader for pic with id '+str(self.pic_id)+' seems to be started...')
        except:
            log.warning('mode switching FAILED, response '+str(res))
            #traceback.print_exc()
            return 99 # sys.exit()

        time.sleep(3)

        start = time.time()
        log.info('going to send ' + filename + ' to mba ' + str(self.mba) + ', regadd '+ str(self.regadd))
        res = self.upload_hex(filename) # hex faili saatmine registrisse 998 yks rida korraga
        if res == 0:
            log.info('upload done in '+str(int(time.time() - start))+' s, waiting for pic restart...')
            time.sleep(10) # 4 on vahe!
            try:
                uptime = mb[self.mbi].read(self.mba,498,2)[1] # read 32 bit always, use LSB
                if uptime < 10 and uptime > 0:
                    log.info('upload done, pic autorestarted and responsive')
                else:
                    log.warning('pic uptime incorrect: ' + str(uptime))
            except:
                log.warning('upload FAILED, pic still in bootloader mode')
                traceback.print_exc()
        else:
            log.warning('upload FAILED, pic still in bootloader mode')

        return res

##################   MAIN  #####################


#iseseisvalt kaivitamiseks: python droidcontroller/pic_update.py 1 0 /dev/ttyAPP0 IOplaat.hex

if __name__ == '__main__': # parameters mba regadd host:port|tty filename
    logging.basicConfig(level=logging.WARNING)
    try:
        mba = int(sys.argv[1])
        regadd = 998 # testimiseks kasuta 400 voi 100
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
        if mb:
            log.info('modbus connection(s) already existing: '+str(mb))
            pass
    except:
        #    self.mb=CommModbus()  # define in comm_modbus2
        mb = []
        try:
            from comm_modbus3 import *  # # for PC
        except:
            #from droidcontroller.comm_modbus import *  # for olinuxino
            from comm_modbus import *  # for olinuxino

        mb.append(CommModbus(port=port)) # PC jaoks
        log.info('modbus connection mb[self.mbi] created')


    up = PicUpdate(mba, regadd, port, pic_id) # kwargs?

    res = up.update(pic_id, filename)
    if res > 0:
        log.warning('pic update FAILED!')

