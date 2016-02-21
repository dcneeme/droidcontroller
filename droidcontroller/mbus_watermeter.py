# neeme 2015
# marko libmbus, python-mbus
import sys, traceback, time # , tornado
#from droidcontroller.mbus import * # neeme old
from mbus.MBus import MBus # by marko
import xmltodict

import tornado.ioloop

from functools import partial
from concurrent.futures import ThreadPoolExecutor
EXECUTOR = ThreadPoolExecutor(max_workers=1)

import logging
log = logging.getLogger(__name__)

class MbusWaterMeter(object): # FIXME averaging missing!
    ''' Publish values to services via msgbus '''  # FIXME use IOloop too
    def __init__(self, msgbus=None, svclist=[['XYW',1,1,'undefined']]): # svc, member, id, name
        self.msgbus = msgbus # all communication via msgbus, not to ac  directly!
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

    def read_sync(self, debug = False):
        ''' Query mbus device, waits for reply, lists all if debug == True '''
        log.info('sending out a sync mbus query')
        try:
            self.mbus.send_request_frame(254)
            reply = self.mbus.recv_frame()
            reply_data = self.mbus.frame_data_parse(reply)
            self.xml = self.mbus.frame_data_xml(reply_data)
            print(self.xml) ##
        except:
            log.error('FAILED to get data from mbus')
            return 1

        try:
            self.dict = xmltodict.parse(self.xml)
        except Exception as ex:
            print("parse error: %s" % ex)
            sys.exit()
        
    def parse(self, debug = False):
        found = 0
        for x in self.dict['MBusData']['DataRecord']:
            if debug == True:
                print(x)
            for svc in self.svclist:
                if int(x['@id']) == 4: # svc[2]:
                    vs = x['Value'] # , x['Unit']) ## key 'Unit' not found?
                    try:
                        val= int(vs)
                        #log.info('got value with id '+str(svc[2])+': '+val ) # str
                        log.info('got value with id 4: '+ str(val) ) # str
                        if self.msgbus:
                            self.msgbus.publish(svc[0], {'values': [ val ], 'status': 0}) # msgbus.publish(val_reg, {'values': values, 'status': status})
                        found += 1
                    except:
                        log.error('invalid Value data from id 4: '+vs)
                        traceback.print_exc()
                        
        if found > 0:
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
        self.parse(result)

