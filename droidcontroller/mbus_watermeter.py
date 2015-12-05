# neeme 2015
import traceback, time, tornado
#from droidcontroller.util_n import UN
from droidcontroller.mbus import *

import logging
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

class MbusWaterMeter(object): # FIXME averaging
    ''' to be used with iomain with tornado IOloop. writes values into services. '''
    def __init__(self, ac, model, svc_cum, svc_avg, avg_win = 3600):
        self.ac = ac # aicochannels
        self.svc_cum = svc_cum # where to write reading from meter
        self.svc_avg = svc_avg # where to write average consumption in time window
        self.avg_win = avg_win # sliding time window length s 
        try:
            self.mbus = Mbus(model='cyble_v2') # vaikimisi port auto, autokey FTDI  # port='/dev/ttyUSB0') #
            log.info('mbus instance created, ac '+str(self.ac))
            #mbus_present = 1
        except:
            #mbus_present = 0
            log.warning('Mbus connection NOT possible, probably no suitable USB port found!')
       
        
    def read(self):
        ''' Reads and returns cumulative and average sliding window values in meter units '''
        try:
            self.mbus.read()
            volume = int(self.mbus.get_volume())
            log.info('got value from water meter: '+str(volume)+', going to save into svc '+self.svc_cum)
            #self.ac.set_aivalue('self.svc_cum', 1, UN.val2int(volume)) # to report only, in L / problem with val2int??
            res = self.ac.set_aivalue(self.svc_cum, 1, volume) # to report only, in L
            if res == 0:
                self.ac.get_aivalues(self.svc_cum) ##
                return 0
            else:
                log.warning('PROBLEM with writing svc '+self.svc_cum+', trying to read')
                try:
                    self.ac.get_aivalues(self.svc_cum)
                except:
                    traceback.print_exc()
        except:
            log.warning('mbus water meter reading or aicochannels register writing FAILED!')
            traceback.print_exc()
            return 1
