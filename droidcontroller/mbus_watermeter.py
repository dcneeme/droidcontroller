# neeme 2015
import traceback, time, tornado
#from util_n import * # neeme utils

import logging
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

class MbusWaterMeter(object): # FIXME averaging
    ''' to be used with iomain with tornado IOloop. writes values into services. '''
    def __init__(self, model, svc_cum, svc_avg, avg_win = 3600):
        self.svc_cum = svc_cum # where to write reading from meter
        self.svc_avg = svc_avg # where to write average consumption in time window
        self.avg_win = avg_win # sliding time window length s 

        
    def read(self):
        ''' Reads and returns cumulative and average sliding window values in meter units '''
        try:
            self.mbus.read()
            volume = self.mbus.get_volume()
            log.info('got value from water meter: '+str(volume))
            ac.set_aivalue('self.svc_cum', 1, self.val2int(volume)) # to report only, in L
            #return volume 
        except:
            log.warning('mbus water meter reading or aicochannels register writing FAILED!')
            traceback.print_exc()
            #return None
