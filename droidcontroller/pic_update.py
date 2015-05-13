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
import time
import logging
log = logging.getLogger(__name__)

try:
    from droidcontroller.sqlgeneral import *
except:
    log.warning('droidcontroller.sqlgeneral not imported, probably ok')
    

''' PIC uploader via modbus. Send  hex file lines as modbus multiwrite commands, without hex crc,
    stripping ":" from the beginning and CRC plus CRLF from the end.
    
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
        self.filename = ''
        log.info('PicUpdate instance created using regadd '+str(regadd))
        
    def set_params(self, mbi=0, mba=1, regadd=998, id=0, keepconf=1, simu=1):
        ''' Change the modbus address of the io-board to update. During simu only crc calculation will be done '''
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

    def add_sum(self, regword):
        ''' Calculates the new crc based on old crc and all bytes in the regword list (each member is 16 bits, crc is xor over bytes '''
        for i in range(len(regword)):
            #sum = 0xff & (self.sum ^ int(hexpiece[0:2],16) ^ int(hexpiece[2:4],16)) # xor checksum as one byte, initially -1
            sum = (0xff & (self.sum ^ (regword[i] >> 8) ^ regword[i])) # xor checksum as one byte, initially -1
            #log.info('self.sum was '+str(self.sum)+', became '+str(sum)+' due to word '+str(i)+' with value '+str(regword[i])+' processed on line '+str(self.linenum))
            self.sum = sum
            
    def upload_hex(self):
        ''' Calculates crc or uploads the hex file (converted to binary on the way), row by row as binary strings,
            stripping : from the beginning and CRC plus CRLF from the end.
            In the case of odd number of bytes the LSB of the last register written is
            fulfilled with CRC.
        '''
        res = 0
        linetrymax = 3
        
        
        lines = [line.rstrip().strip(':') for line in open(self.filename,'r')]
        self.linenum = 0
        for line in lines:
            self.linenum += 1 # hex file line counter
            i = 0 # line retry counter
            hexlen = len(line) - 2 # skip crc
            regcount = int(hexlen / 4) # taisarv peab olema
            regword = [] # for each line values to send
            reghex = ''
            if hexlen % 4 > 0: # last word incomplete
                regcount += 1
                #line = line + 'FF' # pole vaja, kasutame crc kui bait puudu

            for regnum in range(regcount): # index 0...count-1
                hexpiece = line[4 * regnum : 4 * regnum + 4]
                regword.append(int(hexpiece, 16)) #  2bytes into one word
                reghex += ' '+format("%04x" % regword[regnum])

            if self.keepconf == 1: # skip line, data EEPROM for example
                if '0200 0004 0030' in reghex[0:16] \
                    or '1000 0000 0100' in reghex[0:16] \
                    or '10ea 0000' in reghex[0:10]: # cpu conf & data area plus bootloader 
                    # in fact the first check has no effect as it follows the  last
                    self.skipsend = 1
                elif '0000 0001' in reghex[0:11]: # last line MUST be sent
                    self.skipsend = 0
                

            if self.skipsend == 0: # line to be sent and included into crc calculation
                if self.simu == 1: # crc calc
                    #log.debug('crc calculation')
                    self.add_sum(regword) # adding the line bytes xor to self.sum
                    log.debug('crc after processing line '+str(self.linenum)+' with content '+reghex+' became '+str(self.sum))
                    sys.stdout.write('.') # dot without newline for main loop
                    sys.stdout.flush()
                    
                else: # send, no simulation or skipping
                    log.debug('sending to reg '+str(self.regadd)+': ' + reghex)
                    while i < linetrymax: # retry once
                        i += 1
                        #print('attempt '+str(i)+' to write mba '+str(self.mba)+' reg '+str(self.regadd)+' values ' +str(regword))
                        res = mb[self.mbi].write(self.mba, self.regadd, values=regword) # sending to pic   ############ SEND ###########
                        ##time.sleep(0.01) # igaks juhuks. kiire modbusiga 0.01, muidu 0,1 voi 0,5 isegi
                        if res == 0: # ok
                            log.debug('line '+reghex+' written')
                            sys.stdout.write('.') # dot without newline for main loop
                            sys.stdout.flush()
                            break
                        else:
                            time.sleep(1)
                    else:
                        log.warning('line upload FAILED after '+str(i)+' tries, res '+str(res))

                    if res > 0: # write not ok
                        log.warning('upload_hex FAILED, res '+str(res)+', breaking the upload loop, wait and retry')
                        time.sleep(10) # 30 s?
                        break

                #time.sleep(0.05) # give some time to save portion of flash? no need, pic response means ready for next
                
            else:
                log.debug('skipping line: '+reghex+' due to skipsend '+str(self.skipsend)+', simu '+str(self.simu))
                sys.stdout.write('-') # skipping a line
                sys.stdout.flush()

            ##############################

        if self.simu == 0: # if here then res = 0
            log.info('file '+self.filename+' upload successful')
        else:
            log.info('file '+self.filename+' checksum '+str(self.sum))

        return res # 0 if ok


    def update(self, pic_id=0, filename='IOplaat.hex'): # this is for the whole process
        ''' Starts and stops the upload process. pic id is 0 if not stored into registers. Returns crc if simu == 1 '''
        try:
            oldver = mb[self.mbi].read(self.mba,257,1)[0]
            devtype = mb[self.mbi].read(self.mba,256,1)[0] # 241 = F1h
            if devtype == 241:
                log.info('device on modbus address '+str(self.mba)+' with type 214 (0xF1)')
            else:
                log.warning('device on modbus address '+str(self.mba)+' to be updated type NOT 241 (0xF1), not io-board IT5888?')
        except:
            oldver = 0 # unknown, possibly due to already in bootloader mode
            devtype = 0 # unknown, possibly due to already in bootloader mode
            try:
                mb[self.mbi].write(self.mba, self.regadd, values=[pic_id, 0xdddd]) # test for bootloader mode
                log.info('device on modbus address '+str(self.mba)+' already in bootloader mode')
            except:
                log.warning('device on modbus address '+str(self.mba)+' not in normal neither in bootloader mode, FATAL FAILURE!')
                return 2
            
        ver = 0 
        
        if os.path.isfile(filename):
            log.info('hex file '+filename+' found, going to calculate crc')
            self.filename = filename
        else:
            log.warning('hex file '+filename+' NOT found')
            return 1

        res = 0 # return code, 0 = ok
        self.simu = 1 # for crc (self.sum) calc
        self.sum = 0xFF
        self.upload_hex() ############
        log.info('CRC calculation for '+str(self.linenum)+' lines done, value '+str(self.sum)+'. Going to switch pic (id '+str(pic_id)+') into bootloader mode.')
        time.sleep(3)
        
        if pic_id != 0:
            self.pic_id = pic_id

        self.simu = 0 # actual upload
        try:
            values = [self.pic_id, (0xdd00 + (self.sum & 0x00ff))]
            log.info('going to write mba '+str(self.mba)+', regadd '+str(self.regadd)+', values '+str(values))
            res = mb[self.mbi].write(self.mba, self.regadd, values=values)  ##### into bootloader mode
            if res == 0: # ok
                log.info('bootloader for pic with id '+str(self.pic_id)+' started')
            else:
                res = mb[self.mbi].read(self.mba,1,1) # ega enam loetav pole tavaline reg
                if res == 0: # ikka normal
                   log.warning('bootloader for pic with id '+str(self.pic_id)+' NOT started, still in normal mode!')
                   return 100
                else:
                    log.info('bootloader for pic with id '+str(self.pic_id)+' started...')
        except:
            log.warning('mode switching FAILED, response '+str(res))
            traceback.print_exc()
            return 99 # sys.exit()

        log.info('going to upload, pls wait...')
        time.sleep(5) # delay needed for flash erasing

        start = time.time()
        res = self.upload_hex() # send file self.filename (line by line)
        if res == 0:
            log.info('upload done in '+str(int(time.time() - start))+' s, waiting for pic restart...')
            time.sleep(10) # 4 on liiga vahe!
            try:
                mb[self.mbi].read(self.mba,498,2)[1] # read 32 bit always, use LSB
            except:
                log.warning('first modbus read after upload FAILED')
                time.sleep(1)
                
            try:
                uptime = mb[self.mbi].read(self.mba,498,2)[1] # read 32 bit always, use LSB
                if uptime < 20 and uptime > 0:
                    log.info('upload done, pic autorestarted and responsive')
                    ver = mb[self.mbi].read(self.mba,257,1)[0]
                    log.info('successfully updated pic fw from '+format("%04x" % oldver)+'h ('+str(oldver)+') to '+format("%04x" % ver)+'h ('+str(ver)+')')
                    return 0
                else:
                    log.warning('pic uptime incorrect: ' + str(uptime))
                    return 1
            except:
                log.warning('upload FAILED, pic still in bootloader mode')
                traceback.print_exc()
                return 2
        else:
            log.warning('upload FAILED, pic still in bootloader mode')
            return 3

