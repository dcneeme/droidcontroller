# This Python file uses the following encoding: utf-8

''' 
delaychanger699.py - find a new delay for onewire sensors
usage:
 from delaychanger import *
 d=DelayChanger()
 d.get_failcode()
 returns code for reg 699

 use with analogue channel queries 
 '''

import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG) # temporary
log = logging.getLogger(__name__)

class DelayChanger(object): # parameetriks mb
    ''' Returns new delay to try for register 699, from the allowed range '''
    def __init__(self, mb, mbi, mba, senscount, msbmin=0, msbmax=4, lsbmin=0, lsbmax=25):
        self.mb = mb
        self.mbi = mbi
        self.mba = mba
        self.senscount = senscount
        self.msbmin = msbmin
        self.msbmax = msbmax
        self.lsbmin = lsbmin
        self.lsbmax = lsbmax
        self.msb = int((msbmax - msbmin)/2)
        self.lsb = int((lsbmax - lsbmin)/2)
        self.code = self.encode699(self.msb, self.lsb) # reg 699 initial content
        log.info(self.__class__.__name__+' instance created with initial self..code '+hex(self.code)+', sensor count '+str(self.senscount))
        
    def close(self):
        ''' Use this to get rid of the instance if not required '''
        self.__del__()

    def __del__(self):
        ''' Destroyer for close() '''
        log.info(self.__class__.__name__+' destroyed')

    def encode699(self, msb, lsb):
        ''' 2 youngest bits always 1 to avoid discovery and autoadaptivity '''
        return (lsb << 8) + (msb << 2) + 3 
    
    def get_failcode(self):
        ''' bitmap of failing sensors (9 bits max) '''
        temps = self.mb[self.mbi].read(self.mba, 600, self.senscount)
        failcode = 0
        if temps != None:
            for i in range(self.senscount):
                if temps[i] == 4096:
                    failcode += (1 << i)
        else:
            failcode = 15
        return failcode
    
    def newcode(self):
        ''' returns new code to try in reg 699 '''
        if self.get_failcode() > 0: # there is error with reading
            if self.lsb < self.lsbmax:
                self.lsb += 1
            else: #lsb on hi limit
                self.lsb = self.lsbmin
                if self.msb < self.msbmax:
                    self.msb += 1
                else: # msb on hi limit
                    self.msb = self.msbmin
                    
        code699 = self.encode699(self.msb, self.lsb)
        if code699 != self.code:
            log.info('new msb '+str(self.msb)+', new lsb '+str(self.lsb)+', new code '+str(code699)+' to be written into reg 699 of mba '+str(self.mba))            
            self.mb[self.mbi].write(self.mba, 699, value=code699)
        self.code699 = code699
        return self.msb, self.lsb, self.code699

