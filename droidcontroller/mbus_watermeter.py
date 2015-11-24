# neeme 2015
import droidcontroller.UN, traceback, time

class MbusWaterMeter(object): # FIXME averaging
    def __init__(self, svc_cum, svc_avg, avg_win = 3600):
        self.svc_cum = svc_cum # where to write reading from meter
        self.svc_avg = svc_avg # where to write average consumption in time window
        self.avg_win = avg_win # sliding time window length s 
        self.ts = time.time()
        
    def mbus_watermeter(self):
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
