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
        On the first run while the self.sum == -1 or simu == 1 , control sum is calculated
        and saved to self.sum. Nothing gets sent without self.sum from range 0...255.
    '''

    def __init__(self, mbi=0, mba=1, regadd=998, id=0, keepconf=1, simu=0): # **kwargs): #
        ''' mb[self.mbi] may exist already '''
        self.skipsend = 0 # this becomes 1 for data eeprom
        self.set_params(mbi, mba, regadd, id, keepconf)
        self.sum = -1 # valid control sum 0..255
        
        
    def set_params(self, mbi=0, mba=1, regadd=998, id=0, keepconf=1, simu=0):
        ''' Change the modbus address of the io-board to update '''
        self.mbi = mbi
        self.mba = mba
        self.regadd = regadd
        self.pic_id = id
        self.keepconf = keepconf # overwriting data eeprom if 0. may change modbus address and device serno!
        self.simu = simu
        log.info('target modbus channel and address for the updater set to mbi.mba '+str(self.mbi)+'.'+str(self.mba))

    def get_params(self):
        ''' Returns effective parameters '''
        return self.mbi, self.mba, self.regadd, self.pic_id, self.keepconf, self.simu


    def set_sum(self, indata=0xdd):
        self.sum = indata # for initial bootloader version without checksum check

    def get_sum(self):
        return self.sum

    def upload_hex(self, filename='IOplaat.hex'):
        ''' Upload the hex file (converted to binary on the way), row by row as binary strings,
            stripping : from the beginning and CRC plus CRLF from the end.
            In the case of odd number of bytes the LSB of the last register written is
            fulfilled with CRC.
        '''
        
        res = 0
        linetrymax = 3
        
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
                if self.simu == 1:
                    self.sum = 0xff & (self.sum ^ int(hexpiece[0:2],16) ^ int(hexpiece[2:4],16)) # xor checksum as one byte, initially -1
                    # checksum update done
                reghex += ' '+format("%04x" % regword[regnum])

            if self.keepconf == 1: # skip data EEPROM lines
                if '0200 0004 0030' in reghex[0:16] \
                    or '1000 0000 0100' in reghex[0:16] \
                    or '10ea 0000' in reghex[0:10]: # cpu conf & data area plus bootloader 
                    # in fact the first check has no effect as it follows the  last
                    self.skipsend = 1
                if '0000 0001' in reghex[0:11]: # last line MUST be sent
                    self.skipsend = 0

            if self.skipsend == 0 and self.simu == 0: # send, no simulation or skipping
                log.info('sending to reg '+str(self.regadd)+': ' + reghex)
                while i < linetrymax: # retry once
                    i += 1
                    print('attempt '+str(i)+' to write mba '+str(self.mba)+' reg '+str(self.regadd)+' values ' +str(regword))
                    res = mb[self.mbi].write(self.mba, self.regadd, values=regword) # sending to pic   ############ SEND ###########
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

                #time.sleep(0.05) # give some time to save portion of flash? no need, pic response means ready for next

            else:
                log.info('skipping line: '+reghex)

        else:
            if self.simu == 0:
                print('file '+filename+' upload successful')
            else:
                print('file '+filename+' checksum '+str(self.sum))

        return res # 0 if ok


    def update(self, pic_id=0, filename='IOplaat.hex'):
        ''' Starts and stops the upload process. pic id is 0 if not stored into registers  '''
        res = 0 # return code, 0 = ok
        log.info('going to switch pic with id '+str(pic_id)+' into bootloader mode')
        if pic_id != 0:
            self.pic_id = pic_id

        if self.simu == 0:
            try:
                res = mb[self.mbi].write(self.mba, self.regadd, values=[self.pic_id, 0xdd00+self.sum&0x00ff])
                if res == 0: # ok
                    log.info('bootloader for pic with id '+str(self.pic_id)+' started')
                else: # viivitas vastusega yle 0.5 s
                    res = mb[self.mbi].read(self.mba,1,1) # eg ena loetav pole tavaline reg
                    if res == 0: # ikka normal
                       log.warning('bootloader for pic with id '+str(self.pic_id)+' NOT started, still in normal mode!')
                       return 100
                    else:
                        log.info('bootloader for pic with id '+str(self.pic_id)+' started...')
            except:
                log.warning('mode switching FAILED, response '+str(res))
                #traceback.print_exc()
                return 99 # sys.exit()

            time.sleep(3)

        start = time.time()
        if self.simu != 0 or (self.simu <= 0 and self.simu >= 255): # simulation only
            log.info('going to calculate control sum for lines to be sent from ' + filename)
            self.upload_hex(filename)
            print('sum of the data to be uploaded: '+str(self.sum))
        else:
            log.info('going to send ' + filename + ' to mba ' + str(self.mba) + ', regadd '+ str(self.regadd))
            res = self.upload_hex(filename) # hex faili saatmine yks rida korraga
            if res == 0:
                log.info('upload done in '+str(int(time.time() - start))+' s, waiting for pic restart...')
                time.sleep(10) # 4 on liiga vahe!
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

    up.set_params(0,1,998,0,1,1) # mbi mba reg id keepconf simu
    sum = res = up.update(pic_id, filename) # returns sum to be sent

    up.set_params(0,1,998,0,1,0) # last param is self.simu
    res = up.update(pic_id, filename)
    if res > 0:
        log.warning('pic update FAILED!')

