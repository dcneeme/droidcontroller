# neeme 2016 lopetamata!
# marko libmbus, python-mbus
import sys, traceback, time # , tornado
#from droidcontroller.mbus import * # neeme old
from mbus.MBus import MBus # by marko
import xmltodict

try:
    import tornado.ioloop
except:
    log.warning('no tornado, only sync mbus comm!')
    
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
    def __init__(self, msgbus=None, model='kamstrup402', svclist=[['XYW',1,1,'undefined']]): # svc2publish, member, id, name
        self.msgbus = msgbus # all communication via msgbus, not to ac  directly!
        self.svclist = svclist # svc, member, id, name
        self.dict = {} # used by read()
        self.errors = 0 # FIXME / currently used for read_sync only!
        self.model = model
        self.xml = '' # use for new model debugging
        try:
            self.mbus = MBus(device="/dev/ttyUSB0") ##
            self.mbus.connect() ##
            log.info('mbus instance created, output to msgbus: '+str(svclist))
        except:
            log.error('Mbus connection NOT possible, probably no suitable USB port found!')
            traceback.print_exc()
            time.sleep(3)
        self.modeldata = {} # define only  what's important, based on xml
        self.modeldata.update({'kamstrup402': 
            {1:['Energy (kWh)',1,'kWh'], 2:['Volume (1e-2  m^3)',0.01,'m3'], 4:['Flow temperature (1e-2 deg C)',0.1,'ddegC'], 
            5:['Return temperature (1e-2 deg C)',0.1,'ddegC'], 7:['Power (100 W)',100,'W'], 9:['Volume flow (m m^3/h)',1,'l/h']}})

    def read_sync(self, debug = False):
        ''' Query mbus device, waits for reply, lists all if debug == True '''
        log.info('sending out a sync mbus query')
        try:
            self.mbus.send_request_frame(254)
            reply = self.mbus.recv_frame()
            reply_data = self.mbus.frame_data_parse(reply)
            self.xml = self.mbus.frame_data_xml(reply_data)
            #print(self.xml) ##
        except:
            log.error('FAILED to get data from mbus')
            self.errors += 1
            return 1

        try:
            d = xmltodict.parse(self.xml)
        except Exception as ex:
            print("parse error: %s" % ex)
            sys.exit()
        return d

    def get_xml(self): # use read_sync(); get_xml() for debugging
        return self.xml
        
        
    def get_errors(self):
        return self.errors
    
    def get_models():
        '''return supported models '''
        return self.modeldata # dict
    
    def parse_publish(self, dict, debug = False):
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
        #print("    mbus result: " + str(result))
        self.parse_publish(result)

    ######## compatibility with main_karla  ####
    
    def read(self): # into self.dict, sync!
        ''' stores info self.dict variable '''
        try:
            self.dict = self.read_sync()
            log.info('mbus read dict: '+str(self.dict))
            return 0
        except:
            traceback.print_exc()
            return 1
    
    def parse1(self, id):
        ''' Return one value with matching id from self.dict '''
        for x in self.dict['MBusData']['DataRecord']:
            if int(x['@id']) == id:
                return int(round(int(x['Value']) * self.modeldata[self.model][id][1],0)) # FIXME some data needs other conversion (timestamps, units)

    def get_energy(self):
        return self.parse1(1) # kWh

    def get_power(self):
        return self.parse1(7) # W

    def get_volume(self):
        return self.parse1(2) # l

    def get_flow(self):
        return self.parse1(9) # l/h

    def get_temperatures(self):
        ton = self.parse1(4) # ddegC
        tret = self.parse1(5) # ddegC
        return ton, tret
        
