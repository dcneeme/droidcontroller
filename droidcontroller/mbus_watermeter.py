# neeme 2015
import traceback, time, tornado
from droidcontroller.mbus import *

import logging
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

class MbusWaterMeter(object): # FIXME averaging missing!
    ''' to be used with iomain with tornado IOloop. writes values into services. '''
    def __init__(self, msgbus, model, svc_cum, svc_avg, avg_win = 3600):
        #self.ac = ac # aicochannels
        self.msgbus = msgbus # all communication via msgbus, not to ac  directly!
        
        self.svc_cum = svc_cum # where to write reading from meter
        self.svc_avg = svc_avg # where to write average consumption in time window
        self.avg_win = avg_win # sliding time window length s 
        try:
            self.mbus = Mbus(model='cyble_v2') # vaikimisi port auto, autokey FTDI  # port='/dev/ttyUSB0') #
            log.info('mbus instance created, output to msgbus: '+svc_cum)
        except:
            log.warning('Mbus connection NOT possible, probably no suitable USB port found!')
            traceback.print_exc()
        
    def read(self):
        ''' Reads and returns cumulative and average sliding window values in meter units '''
        try:
            self.mbus.read()
            volume = int(self.mbus.get_volume())
            log.info('got value from water meter: '+str(volume)+', going to save into svc '+self.svc_cum)
            self.msgbus.publish(self.svc_cum, {'values': [ volume ], 'status': 0}) # msgbus.publish(val_reg, {'values': values, 'status': status})
            #res = self.ac.set_aivalue(self.svc_cum, 1, volume) # moved to iomain or whatever listener (based on sqlgeneral?)
        except:
            log.warning('watermeter read FAILED')
            traceback.print_exc()