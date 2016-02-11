# neeme 2016 lopetamata!
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
''' lisa meetodid et sobituks olemasolevatesse

m.get_energy()
m.get_power()
m.get_volume()
m.get_flow()
10.0 * m.get_temperatures()[0] # on
10.0 * m.get_temperatures()[1] # return

'''

class MbusHeatMeter(object): # FIXME averaging missing!
    ''' Publish values to services via msgbus '''  # FIXME use IOloop too
    def __init__(self, msgbus=None, svclist=[['XYW',1,1,'undefined']]): # svc, member, id, name / =[['WVCV',1,4,'water']]
        self.msgbus = msgbus # all communication via msgbus, not to ac  directly!
        self.svclist = svclist # svc, member, id, name
        self.dict = {} # used by read()
        
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
            xml_buff = self.mbus.frame_data_xml(reply_data)
            print(xml_buff) ##
        except:
            log.error('FAILED to get data from mbus')
            return 1

        try:
            d = xmltodict.parse(xml_buff)
        except Exception as ex:
            print("parse error: %s" % ex)
            sys.exit()
        return d

    def parse(self, dict, debug = False):
        ''' Publish all  '''
        found = 0
        for x in dict['MBusData']['DataRecord']:
            if debug == True:
                print(x)
            for svc in self.svclist:
                if int(x['@id']) == svc[2]:
                    vs = x['Value'] # , x['Unit']) ## key 'Unit' not found?
                    log.info('found value with id '+str(svc[2])+': '+vs ) # str
                    if self.msgbus:
                        self.msgbus.publish(svc[0], {'values': [ int(vs) ], 'status': 0}) # msgbus.publish(val_reg, {'values': values, 'status': status})
                    found += 1
        if found > 0:
            return 0
        else:
            return 1

    
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

    ######## compatibility with main_karla  ####
    # svclist=[['XYW',1,1,'undefined'], ]
    def read(self): # into self.dict
        ''' stores info self.dict variable '''
        self.dict = read_sync()
    
    def parse1(self, id):
        ''' Return one value with matching id '''
        for x in self.dict['MBusData']['DataRecord']:
            if int(x['@id']) == id:
                return x['Value']

    def m.get_energy(self):
        return parse1(1)

    def m.get_power(self);
        return parse1(2)

    def m.get_volume(self):
        return parse1(3)

    def m.get_flow(self):
        return parse1(4)

    def get_temperatures(self):
        ton = parse1(5)
        tret = parse1(6)
        return ton, tret
        
