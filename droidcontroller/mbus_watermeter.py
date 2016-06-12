# neeme 2015..2016
# marko libmbus, python-mbus
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
m.read_sync() # sync read, async is also possible using future. 
m.parse(debug=True) # to list all possible values from the meter
m.parse() # to get the needed value only
'''

class MbusWaterMeter(object): # FIXME averaging missing!
    ''' Publish values to services via msgbus '''  # FIXME use IOloop too
    def __init__(self, id = 4, msgbus=None, svclist=[['XYW',1,1,'undefined']]): # svc, member, id, name
        ''' id=4 for itron, id=1 for HRI-B '''
        self.id = id
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

    def read_sync(self, addr=254, debug = False):
        ''' Query mbus device, waits for reply, lists all if debug == True '''
        if debug:
            log.info('sending out a sync mbus query')
        try:
            self.mbus.send_request_frame(addr) # 254 is broadcats, see accessnumber in xml reqading one by one
            reply = self.mbus.recv_frame()
            reply_data = self.mbus.frame_data_parse(reply)
            self.xml = self.mbus.frame_data_xml(reply_data)
            if debug:
                print(self.xml)
        except:
            log.error('FAILED to get data from mbus')
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
        print("    mbus result: " + str(result))
        self.parse()

