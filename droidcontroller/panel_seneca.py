# This Python file uses the following encoding: utf-8

'''
to write seneca s401 modbus panel without reading back, to avoid constant reading and delays if panel power off

testing:
from main_sauna import *
from droidcontroller.panel_seneca import *
panel=SenecaPanel(mb,1,linedict={400:10, 401:11, 403:13})
panel.set_power(1)
panel.send(400,44)
mb[0].read(1,400,4)
'''

import sys, logging, time
logging.basicConfig(stream=sys.stderr, level=logging.INFO) # temporary
log = logging.getLogger(__name__)

class SenecaPanel(object): # parameetriks mb
    ''' Returns new delay to try for register 699, from the allowed range '''
    def __init__(self, mb, mba, mbi = 0, linedict={1000:-999,1001:-999, 1003:-999,1004:-999, 1006:-999,1007:-999,1009:-999}, power = 0):
        self.mb = mb
        self.mbi = mbi
        self.mba = mba
        self.power = power # initially off
        self.ready = 0 # becomes 1 if register read is ok after power -> 1
        self.linedict = linedict
        log.info(self.__class__.__name__+' instance created with mbi '+str(self.mbi)+',  mba '+str(self.mba)+', linedict '+str(self.linedict))


    def get_power(self):
        ''' returns power state 0 or 1 '''
        return self.power


    def get_ready(self):
        ''' returns readiness state 0 or 1 '''
        return self.ready


    def get_data(self):
        ''' returns linedict content '''
        return self.linedict


    def set_power(self, power):
        ''' sets power state 0 or 1 '''
        if power != self.power:
            if power >= 0 and power <= 1:
                self.power = power
                log.info('new power value '+str(self.power)+', not ready!')
                self.ready = 0
            else:
                log.warning('illegal value for power: '+str(power))
                return 1
        return 0


    def send(self, line, data):
        ''' if data is list (max len 2! for seneca), then multiregister write with sequential addresses is used '''
        if self.linedict[line] != data:
            self.linedict.update({line:data})
            log.info('linedict updated') ##
            if self.power == 1:
                if self.ready == 1:
                    res = self.mb[self.mbi].write(self.mba, line, value=data) # inly sends if changed
                    if res != 0:
                        self.ready = 0
                        log.warning('NOT READY any more due to reg '+str(line)+' read failure!')
                    else:
                        log.debug('sent to panel linereg '+str(line)+' new value '+str(data))
                        return 0 # ok
                else: # not ready
                    if self.chk_ready(line) == 0: # check if ready now
                        res = self.mb[self.mbi].write(self.mba, line, value=data)
                        if res == 0:
                            time.sleep(0.1)
                            res = self.mb[self.mbi].read(self.mba, line, 1)[0]
                            if res == data:
                                self.ready = 1
                                log.info('became ready, sending all')
                                res = self.sendall()
                                return res
                            else:
                                log.warning('powered panel not ready, did not returned written data '+str(data))
                                self.ready = 0
                    else:
                        log.warning('panel powered but not ready yet, read '+str(self.mba)+'.'+str(line)+' failed')
                        self.ready = 0
                        return 2
            else:
                log.info('panel not powered')
                return 1
        else: # still checking readiness
            log.info('no linedict change, no send') ##
            if self.ready == 0 and self.power == 1: # powered but not ready yet
                if self.chk_ready() == 0:
                    log.info('powered and ready, sending all')
                    self.ready = 1
                    self.sendall()
            return 0


    def sendall(self):
        ''' sends the linedict content to the panel '''
        res = 0
        for line in self.linedict.keys():
            res += self.mb[self.mbi].write(self.mba, line, value=self.linedict[line])
        return res


    def chk_ready(self, line):
        '''returns 0 on successful read '''
        try:
            self.mb[self.mbi].read(self.mba, line, 1)
            return 0
        except:
            log.warning('panel not ready, tested linereg '+str(line))
            return 1
        return res