# neeme 2016 lopetamata!
# marko libmbus, python-mbus
import sys, traceback, time # , tornado
#from droidcontroller.mbus import * # neeme old
from mbus.MBus import MBus # by marko
#import xmltodict # vajab eraldi installi, soltub py versioonist! selle asemel jargmine
from xml.dom.minidom import parseString

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
    def __init__(self, msgbus=None, port='/dev/ttyUSB0', model='kamstrup402', svclist=[['XYW',1,1,'undefined']]): # svc2publish, member, id, name
        self.msgbus = msgbus # all communication via msgbus, not to ac  directly!
        self.svclist = svclist # svc, member, id, name
        self.dict = {} # used by read()
        self.errors = 0 # FIXME / currently used for read_sync only!
        self.model = model
        self.xml = '' # use for new model debugging
        self.nodes = ''
        try:
            self.mbus = MBus(device=port) ##
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
        self.modeldata.update({'kamstrup602': 
            {1:['Energy (kWh)',1,'kWh'], 2:['Volume (1e-2  m^3)',0.01,'m3'], 4:['Flow temperature (1e-2 deg C)',0.1,'ddegC'], 
            5:['Return temperature (1e-2 deg C)',0.1,'ddegC'], 7:['Power (100 W)',100,'W'], 9:['Volume flow (m m^3/h)',1,'l/h']}})
        self.modeldata.update({'axisSKU03': 
            {5:['Energy (kWh)',1,'kWh'], 6:['Volume (l)',0.001,'m3'], 9:['Flow temperature (deg C)',10,'ddegC'], 
            10:['Return temperature (deg C)',10,'ddegC'], 7:['Power (W)',1000,'W'], 8:['Volume flow (l/h)',1000,'l/h']}})
        self.modeldata.update({'cyble': {4:['Volume (l)',1,'l']}}) # water meter
         
         
    def set_model(self, invar):
        self.model = invar
        
    def read_sync(self, debug = False):
        ''' Query mbus device, waits for reply, lists all if debug == True '''
        log.info('sending out a sync mbus query')
        try:
            self.mbus.send_request_frame(254)
            reply = self.mbus.recv_frame()
            reply_data = self.mbus.frame_data_parse(reply)
            self.xml = self.mbus.frame_data_xml(reply_data)
            
        except:
            log.error('FAILED to get data from mbus')
            self.errors += 1
            return 1
       
        try:
            ##d = xmltodict.parse(self.xml)
            self.dom = parseString(self.xml)
        except Exception as ex:
            print("parse error: %s" % ex)
            sys.exit()
        return 0

    def get_xml(self): # use read_sync(); get_xml() for debugging
        return self.xml
        
        
    def get_errors(self):
        return self.errors
    
    def get_models():
        '''return all supported models '''
        return self.modeldata # dict
    
    def get_model():
        '''return currently selected model '''
        return self.model # dict
    
    def parse_publish(self, dict, debug = False):
        ''' Publish all  '''
        return 1 # FIXME
        
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
            res = self.read_sync()
            if res == 0:
                self.nodes = self.dom.getElementsByTagName('Value')
                return 0
            else:
                log.error('mbus read failed')
                return 1
        except:
            traceback.print_exc()
            return 2
    
    def parse1(self, id):
        ''' Return one Value with matching id from self.nodes '''
        if id < len(self.nodes):
            return int(round(float(self.nodes[id].firstChild.nodeValue) * self.modeldata[self.model][id][1],0))
        else:
            log.error('invalid id '+str(id)+' while self.nodes len '+str(len(self.nodes)))
            return None
        
    def find_id(self, name): # name is 'Energy' or smthg...
        for i in range(len(self.modeldata)):
            if name in self.modeldata[self.model][i][0]:
                break
            return i
        
    def get_energy(self):
        id=1 #5 # id = self.find_id('Energy')
        return self.parse1(id) # kWh

    def get_power(self):
        id = 7 # self.find_id('Power')
        return self.parse1(id) # W

    def get_volume(self):
        id = 2 # 6 #  self.find_id('Volume')
        return self.parse1(id) # l

    def get_flow(self):
        id = 9 # 8 # self.find_id('Volume flow')
        return self.parse1(id) # l/h

    def get_temperatures(self):
        id = 4 # 9 # self.find_id('ow temperature')
        ton = self.parse1(id) # ddegC
        id = 5 # 10 # self.find_id('Return temp')
        tret = self.parse1(id) # ddegC
        return ton, tret
        
    def get_all(self): # kogu info nagemiseks vt self.xml
        out = {}
        conf = self.modeldata[self.model]
        for id in conf:
            value = self.parse1(id)
            out.update({id:[conf[id][0], value]})
        
        return out
        