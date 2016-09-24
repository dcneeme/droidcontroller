# update pic firmware from hex file by writing modbus register regadd
# usage on windows: python pic_update.py 1 0 COM31 IOplaat.hex
# usage on linux: python pic_update.py 1 0 /dev/ttyUSB0 IOplaat.hex
# first runs dry to get crc, then sends the modified hex file.


import traceback, os, sys
import time
import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)


''' PIC uploader via modbus. Send  hex file lines as modbus multiwrite commands, without hex crc,
    stripping ":" from the beginning and CRC plus CRLF from the end.
    
    USAGE if python is already started:
    from main_application import *; from droidcontroller.pic_update import *; pic=PicUpdate(mb); pic.update(mba=1, filename='IOplaat.hex')
    or
    pic=PicUpdate(mb, mbi=0); pic.update(1, 'IOplaat.hex')
'''

class PicUpdate(object): # using the existing mb instance
    ''' Class for updating PIC microcontrollers with new firmware.
        Sending hex file rows as binary string, withour CRC and leading colon.
        On the first run while the self.sum == -1 or simu == 1 , control sum is calculated
        and saved to self.sum. Nothing gets sent without self.sum from range 0...255.
    '''

    def __init__(self, mb, mbi=0, regadd=998): # **kwargs): # mba later
        self.mb = mb # modbus communication instance / object
        self.skipsend = 0 # this becomes 1 for data eeprom
        if mbi > len(mb) -1:
            log.error('invalid mbi '+str(mbi)+' while len(mb) is '+str(len(mb)))
            raise ValueError 
        self.set_params(mbi, regadd)
        self.sum = -1 # valid control sum 0..255
        self.filename = ''
        log.info('PicUpdate instance created.')
        
    def close(self):
        ''' Use this to get rid of the instance if not required '''
        self.__del__()

    def __del__(self):
        ''' Destroyer for close() '''
        class_name = self.__class__.__name__
        log.info(class_name+' destroyed')

        
    def set_params(self, mbi, regadd, simu=1, keepconf=1):
        ''' Change the modbus address of the io-board to update. During simu only crc calculation will be done '''
        self.mbi = mbi
        self.regadd = regadd
        
        self.keepconf = keepconf # overwriting data eeprom if 0. may change modbus address and device serno!
        self.simu = simu
        log.info('target modbus channel '+str(self.mbi)+', upload register address  '+str(self.regadd)+', simu '+str(simu))
            
    def get_params(self):
        ''' Returns effective parameters '''
        return self.mbi, self.regadd, self.keepconf, self.simu


    def set_sum(self, indata=0xdd):
        self.sum = indata # for initial bootloader version without checksum check

    def get_sum(self):
        return self.sum

    def add_sum(self, regword):
        ''' Calculates the new crc based on old crc and all bytes in the regword list (each member is 16 bits, crc is xor over bytes '''
        for i in range(len(regword)):
            #sum = 0xff & (self.sum ^ int(hexpiece[0:2],16) ^ int(hexpiece[2:4],16)) # xor checksum as one byte, initially -1
            sum = (0xff & (self.sum ^ (regword[i] >> 8) ^ regword[i])) # xor checksum as one byte, initially -1
            #self.log.info('self.sum was '+str(self.sum)+', became '+str(sum)+' due to word '+str(i)+' with value '+str(regword[i])+' processed on line '+str(self.linenum))
            self.sum = sum
            
    #def upload_hex(self, mb):
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

            if self.keepconf == 1: ## skip line, data EEPROM for example
                if '0200 0004 0030' in reghex[0:16] \
                    or '1000 0000 0100' in reghex[0:16] \
                    or '10ea 0000' in reghex[0:10]: # start skipping, cpu conf & data area plus bootloader 
                    # in fact the first check has no effect as it follows the  last
                    self.skipsend = 1
                elif '0000 0001' in reghex[0:11]: # stop skipping. last line MUST be sent
                    self.skipsend = 0
                

            if self.skipsend == 0: # line to be sent and included into crc calculation
                if self.simu == 1: # crc calc
                    self.add_sum(regword) # adding the line bytes xor to self.sum
                    #self.log.debug('crc after processing line '+str(self.linenum)+' with content '+reghex+' became '+str(self.sum))
                    log.debug('crc after processing line '+str(self.linenum)+' with content '+reghex+' became '+str(self.sum))
                    sys.stdout.write('.') # dot without newline for main loop
                    sys.stdout.flush()
                    
                else: # send, no simulation or skipping
                    #self.log.debug('sending to reg '+str(self.regadd)+': ' + reghex)
                    log.debug('sending to reg '+str(self.regadd)+': ' + reghex)
                    
                    while i < linetrymax: # retry once
                        i += 1
                        res = self.mb[self.mbi].write(self.mba, self.regadd, values=regword) # sending to pic   ############ SEND ###########
                        if res == 0: # ok
                            #self.log.debug('line '+reghex+' written')
                            log.debug('line '+reghex+' written')
                            if i > 1:
                                sys.stdout.write(':') # retry
                            else:
                                sys.stdout.write('.') # first try
                            sys.stdout.flush()
                            break
                        else:
                            time.sleep(1)
                    else:
                        #self.log.warning('line upload FAILED after '+str(i)+' tries, res '+str(res))
                        log.warning('line upload FAILED after '+str(i)+' tries, res '+str(res))

                    if res > 0: # write not ok
                        #self.log.warning('upload_hex FAILED, res '+str(res)+', pls retry')
                        log.warning('upload_hex FAILED, res '+str(res)+', pls retry')
                        time.sleep(5) 
                        return 2 # break

                #time.sleep(0.05) # give some time to save portion of flash? no need, pic response means ready for next
                
            else:
                #self.log.debug('skipping line: '+reghex+' due to skipsend '+str(self.skipsend)+', simu '+str(self.simu)) ###
                log.debug('skipping line: '+reghex+' due to skipsend '+str(self.skipsend)+', simu '+str(self.simu)) ###
                #sys.stdout.write('-') # skipping a line
                #sys.stdout.flush()

            ##############################

        if self.simu != 0: 
            #self.log.info('file '+self.filename+' checksum '+str(self.sum))
            log.info('file '+self.filename+' checksum '+str(self.sum))

        return res # 0 if ok


    def update(self, mba, mbi = 0, filename='IOplaat.hex'): # this is for the whole process
        ''' Starts and stops the upload process. pic id is 0 if not stored into registers. Returns crc if simu == 1 '''
        pic_id = 0 # means unknown
        self.mba = mba # the device id to update, likely to change every time
        self.mbi = mbi # may change from one upload to another!
        log.info('going to update mbi '+str(self.mbi)+', mba '+str(self.mba)+' with '+filename)
        
        try:
            devtype, oldver = self.mb[self.mbi].read(self.mba, 256, 2) # 241 = F1h
            time.sleep(0.2)
            id_list = self.mb[self.mbi].read(self.mba, 258, 2) 
            pic_id = ((0xff & id_list[0]) << 8) + (0xff & id_list[1]) # only used for entering the bootloader mode, irrelevant lster
            
            if devtype == 241:
                #self.log.info('going to update the device on mba '+str(self.mba)+' with type 214 (0xF1) and id '+str(pic_id))
                log.info('going to update the device on mba '+str(self.mba)+' with type 241 (0xF1) and id '+str(pic_id))
            else:
                #self.log.warning('device on modbus address '+str(self.mba)+' NOT 241 (0xF1), not io-board IT5888?')
                log.warning('device on modbus address '+str(self.mba)+' NOT 241 (0xF1), not io-board IT5888?')
                return 2 # cancel update
                
            if oldver < 0x024F:
                #self.log.warning('updating impossible, too old fw '+str(hex(oldver))+' (should be >= 0x24F)')
                log.warning('updating impossible, too old fw '+str(hex(oldver))+' (should be >= 0x024F)')
                return 1
            log.info('the existing fw version '+str(hex(oldver))+' >=  0x24F, going to update')
                
        except:
            oldver = 0 # unknown, possibly due to already in bootloader mode
            devtype = 0 # unknown, possibly due to already in bootloader mode
            #traceback.print_exc()
            log.warning('no comm with 256..258, device possibly in bootloader mode already, going to check with 3F3F into 998')
            try:
                time.sleep(0.5)
                res = self.mb[self.mbi].write(self.mba, self.regadd, values=[pic_id, 0x3F3F]) # test for bootloader mode, write success in this case
                if res == 0:
                    log.info('tested with 0x3F3F to regadd 998 - device on mba '+str(self.mba)+' already in bootloader mode!')
                else:
                    log.warning('device on modbus address '+str(self.mba)+' not in normal neither in bootloader mode, FATAL FAILURE!')
                    return 2
            except:
                log.warning('device on modbus address '+str(self.mba)+' not in normal neither in bootloader mode, FATAL FAILURE! chk mba!')
                traceback.print_exc()
                time.sleep(2)
                return 2
            
        ver = 0 
        # only to continue if verified to be in bootloader mode
        ############# going to update now !####################
        
        if os.path.isfile(filename):
            log.info('hex file '+filename+' found, going to calculate crc')
            self.filename = filename
        else:
            log.warning('hex file '+filename+' NOT found, stopped')
            return 1

        res = 0 # return code, 0 = ok
        self.simu = 1 # for crc (self.sum) calc
        self.sum = 0xFF
        self.upload_hex() ###### simualation to find crc
        log.info('CRC calculation for '+str(self.linenum)+' lines done, value '+str(self.sum))
        time.sleep(2)
        
        self.simu = 0 # for actual upload
        try:
            values = [pic_id, (0xdd00 + (self.sum & 0x00ff))] # send crc for the total hex data to be sent
            log.info('going to write crc - mba '+str(self.mba)+', regadd '+str(self.regadd)+', values '+str(values))
            res = self.mb[self.mbi].write(self.mba, self.regadd, values=values)  ##### into bootloader mode
            if res == 0: # ok
                log.info('bootloader accepted crc, ready to receive, deleting flash, pls wait...')
                time.sleep(18) ## kui seda viidet ei ole, kukub kiirus 19k2?
            else:
                log.warning('bootloader did NOT accept the crc, wait to retry...')
                time.sleep(10)
                log.info('checking bootloader mode - mba '+str(self.mba)+', regadd '+str(self.regadd)+', values '+str(values))
                res = self.mb[self.mbi].write(self.mba, self.regadd, values=[pic_id, 0x3F3F]) # uus proov - kas juba bootloader
                if res == 0:
                    log.info('pic with id '+str(pic_id)+' now in bootloader mode after delay and retry')
                    log.info('retry to write crc - mba '+str(self.mba)+', regadd '+str(self.regadd)+', values '+str(values))
                    res = self.mb[self.mbi].write(self.mba, self.regadd, values=values)
                    if res == 0: # ok
                        log.info('bootloader accepted crc, ready to receive')
                    else:
                        log.error('bootloader did NOT accept the crc, values '+str(values))
                        return 2
                else:
                    log.error('device to be updated in invalid state, not responding!')
                    return 2
               
        except:
            log.warning('mode switching with values '+str(values)+' to regadd 998 FAILED, response '+str(res))
            traceback.print_exc()
            return 99 # sys.exit()

        log.info('starting upload of the new hex file, pls wait...')
        #time.sleep(5) # delay needed for flash erasing

        start = time.time()
        res = self.upload_hex() ### actual upload sendingthe hex file (line by line)
        if res == 0:
            log.info('upload done in '+str(int(time.time() - start))+' s, waiting for pic restart...')
            time.sleep(15) # 
            try:
                self.mb[self.mbi].read(self.mba,498,2)[1] # pic uptime, read 32 bit always, use LSB
            except:
                log.warning('first modbus read after upload FAILED')
                time.sleep(5)
                
            try:
                uptime = self.mb[self.mbi].read(self.mba,498,2)[1] # pic uptime, read 32 bit always, use LSB
                
                if uptime < 20 and uptime > 0:
                    log.debug('upload done, pic autorestarted and responsive')
                    ver = self.mb[self.mbi].read(self.mba,257,1)[0]
                    log.info('successfully updated pic fw from '+format("%04x" % oldver)+'h ('+str(oldver)+') to '+format("%04x" % ver)+'h ('+str(ver)+')')
                    time.sleep(0.2)
                    self.mb[self.mbi].write(self.mba, 276, value = 512) # timeout modbus comm 5V pause # neid ei saa korraga kirjutada!
                    time.sleep(0.2)
                    self.mb[self.mbi].write(self.mba, 277, value = 9) # 5v pause len
                    time.sleep(0.2)
                    self.mb[self.mbi].write(self.mba, 278, value = 768) # pic restart timeput if no modbus comm
                    time.sleep(0.2)
                    touts = self.mb[self.mbi].read(self.mba, 276, 3) # read 32 bit always, use LSB
                    log.info('timeout registers 276..278 set to: '+str(touts))
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


