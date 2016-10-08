# This Python file uses the following encoding: utf-8
# neeme 2015..2016. usable for one meter for now, using broadcast primary addressing. add settable address, primary or secondary!

import sys, traceback, time # tornado
#from droidcontroller.mbus import * # neeme old
    
import xmltodict

import tornado.ioloop

from functools import partial
from concurrent.futures import ThreadPoolExecutor
EXECUTOR = ThreadPoolExecutor(max_workers=1)

import logging
log = logging.getLogger(__name__)

from mbus.MBus import MBus # by marko
try:
    from mbus.MBusLowLevel import MBUS_ADDRESS_NETWORK_LAYER # sec aadressi jaoks
except:
    log.warning('no secondary addressing possible due to mbus.MbusLowLevel failed import')

''' Usage example
from mbus_watermeter import MbusWaterMeter # libmbus c-library is needed too!
m=MbusWaterMeter(id=1) # meter instance, id=1 for HRI, 4 for itron
m.read_sync(debug=True) # sync read, async is also possible using future. 
m.parse(debug=True) # to list all possible values from the meter
m.parse() # to get the needed value only

find out secondary address> mbus-serial-scan-secondary -b 2400 /dev/ttyUSB0
'''

class MbusWaterMeter(object): 
    ''' Publish values to services via msgbus or return a single value '''
    def __init__(self, id = 4, msgbus=None, svclist=[['XYW',1,1,'undefined']], primary=254, secondary=''): # svc, member, id, name
        ''' id=4 for itron, id=1 for HRI-B. for heat meters, use id list (FIXME!) '''
        self.primary = primary # 254 is broadcast address, usable for single meter on the line
        self.secondary = secondary # hex string, primary addresses can be the same, if secondary addresses used!
        self.id = id # FIXME / data portion from the xml, see debug=True for read_sync()
        self.msgbus = msgbus # publish to msgbus, if not None
        self.svclist = svclist # svc, member, id, name
        self.xml = ''
        self.dict = {}
        try:
            self.mbus = MBus(device="/dev/ttyUSB0") ##
            self.mbus.connect() ##
            log.info('mbus instance created, output to msgbus: '+str(svclist))
        except:
            log.error('Mbus connection NOT possible, probably no suitable USB port found!')
            traceback.print_exc()
            time.sleep(3)

    def read_sync(self, debug=False): # prints xml data if debug True
        ''' Query mbus device using primary address either broadcast 254 or known 1...250, waits for reply, lists all if debug == True 
            DO NOT use primary addressing if more than one meters share the same primary address! sensus watermeters 0 by default! 
        '''
        if self.secondary != '':
            sec = True
        else:
            sec = False
        
        if debug:
            if sec:
                logadd = 'secondary address '+self.secondary
            else:
                logadd = 'primary address '+str(self.primary)
            log.info('sending out a sync mbus query using '+logadd)
        try:
            if sec:
                self.mbus.select_secondary_address(self.secondary)
                self.mbus.send_request_frame(MBUS_ADDRESS_NETWORK_LAYER) # secondary
            else:
                self.mbus.send_request_frame(self.primary) # primary
                self.mbus.send_request_frame(self.primary) # primary
                self.mbus.send_request_frame(self.primary) # primary
            reply = self.mbus.recv_frame()
            reply_data = self.mbus.frame_data_parse(reply)
            self.xml = self.mbus.frame_data_xml(reply_data)
            if debug:
                print(self.xml)
        except:
            log.error('FAILED to get data from mbus')
            traceback.print_exc()
            return 1

        try:
            self.dict = xmltodict.parse(self.xml)
        except Exception as ex:
            print("parse error: %s" % ex)
            sys.exit()
        
    def parse(self, debug = False):
        ''' debug will list all values with any id. 4 is id for itron, use id=1 for HRI-B '''
        found = False
        for x in self.dict['MBusData']['DataRecord']:
            if debug == True:
                print(x)
            for svc in self.svclist:
                if int(x['@id']) == self.id: 
                    vs = x['Value'] 
                    try:
                        val= int(vs)
                        if debug:
                            log.info('got value with id '+str(self.id)+': '+ str(val) ) # str
                        if self.msgbus:
                            self.msgbus.publish(svc[0], {'values': [ val ], 'status': 0}) # msgbus.publish(val_reg, {'values': values, 'status': status})
                        found = True
                    except:
                        log.error('invalid Value data from id '+str(self.id)+': '+vs)
                        traceback.print_exc()
                        
        if found:
            return val
        else:
            return None


    # methods needed for async comm
    def run(self):
        self.read_async(self.async_reply)

    def read_async(self, reply_cb):
        log.info("    mbus_send_request_frame..")
        EXECUTOR.submit(self.read_sync).add_done_callback(lambda future: tornado.ioloop.IOLoop.instance().add_callback(partial(self.callback, future)))
        #eraldi threadis read_sync, mis ootab vastust.

    def callback(self, future):
        result = future.result()
        self.async_reply(result)

    def async_reply(self, result):
        if result != None:
            log.info("  mbus result: " + str(result))
            self.parse()
        else:
            log.error("  mbus result: None!")
        

