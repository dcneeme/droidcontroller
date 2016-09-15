# neeme 2016 universaalne, mbus_heatmeter alusel, peaks kolbama molema asemele
# marko libmbus, python-mbus
## find out secondary address> mbus-serial-scan-secondary -b 2400 /dev/ttyUSB0
#1501372977041407 koogu 20 water

import sys, traceback, time # , tornado
#from droidcontroller.mbus import * # neeme old
from mbus.MBus import MBus # by marko, in d4c
try:
    from mbus.MBusLowLevel import MBUS_ADDRESS_NETWORK_LAYER # sec aadressi jaoks
except:
    log.warning('no secondary addressing possible due to mbus.MbusLowLevel failed import')

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

class MbusMeter(object):
    ''' Publish values to services via msgbus '''  # FIXME use IOloop too
    def __init__(self, msgbus=None, port='/dev/ttyUSB0', model='kamstrup402', svclist=[['XYW',1,1,'undefined']], primary=254, secondary=''): # svc2publish, member, id, name
        self.primary = primary # 254 is broadcast address, usable for single meter on the line
        self.secondary = secondary # hex string, primary addresses can be the same, if secondary addresses
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
            5:['Return temperature (1e-2 deg C)',0.1,'ddegC'], 6:['Temperature Difference (1e-2 deg C)',0.1,'ddegC'], 7:['Power (100 W)',100,'W'], 9:['Volume flow (m m^3/h)',1,'l/h']}})
        self.modeldata.update({'kamstrup602':
            {1:['Energy (kWh)',1,'kWh'], 2:['Volume (1e-2  m^3)',0.01,'m3'], 4:['Flow temperature (1e-2 deg C)',0.1,'ddegC'],
            5:['Return temperature (1e-2 deg C)',0.1,'ddegC'], 7:['Power (100 W)',100,'W'], 9:['Volume flow (m m^3/h)',1,'l/h']}})
        self.modeldata.update({'axisSKU03':
            {5:['Energy (kWh)',1,'kWh'], 6:['Volume (l)',0.001,'m3'], 9:['Flow temperature (deg C)',10,'ddegC'],
            10:['Return temperature (deg C)',10,'ddegC'], 7:['Power (W)',1000,'W'], 8:['Volume flow (l/h)',1000,'l/h']}})
        self.modeldata.update({'cyble': {4:['Volume (l)',1,'l']}}) # water meter koogu20
        self.modeldata.update({'APA': {2:['Volume (l)',1,'l'], 3:['Volume flow (l/h))',1,'l']}}) # water meter vaatsakool


    def set_model(self, invar):
        self.model = invar

    def read_sync(self, debug = False):
        ''' Query mbus device, waits for reply, lists all if debug == True '''
        log.info('sending out a sync mbus query')
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

    def parse(self, dict, debug = False):
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
        log.info("  mbus_send_request_frame..")
        EXECUTOR.submit(self.read_sync).add_done_callback(lambda future: tornado.ioloop.IOLoop.instance().add_callback(partial(self.callback, future)))
        #eraldi threadis read_sync, mis ootab vastust.

    def callback(self, future):
        result = future.result()
        self.async_reply(result)

    def async_reply(self, result):
        #print("    mbus result: " + str(result))
        self.parse(result)

    ######## compatibility with main_karla, use this without msgbus  ####
    def read(self): # into self.dict, sync!
        ''' stores info self.dict variable. use read() before get_all() '''
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
        try:
            value = int(round(float(self.nodes[id].firstChild.nodeValue) * self.modeldata[self.model][id][1],0))
        except:
            value = self.nodes[id].firstChild.nodeValue
        return value

    def find_id(self, name): # name is 'Energy', 'Volume flow' or smthg...
        found = 0
        idlist = list(self.modeldata[self.model].keys())
        for id in idlist:
            if name in self.modeldata[self.model][id][0]:
                found = 1
                break

        if found == 1:
            return id
        else:
            return None

    def get_energy(self):
        if self.xml != '':
            id = self.find_id('Energy')
        else:
            log.error('use read() first'); id = None
        if id != None:
            return self.parse1(id) # kWh
        else:
            return None

    def get_power(self):
        if self.xml != '':
            id = self.find_id('Power')
        else:
            log.error('use read() first'); id = None
        if id != None:
            return self.parse1(id) # W
        else:
            return None

    def get_volume(self):
        if self.xml != '':
            id = self.find_id('Volume')
        else:
            log.error('use read() first'); id = None
        if id != None:
            return self.parse1(id) # litres
        else:
            return None

    def get_flow(self):
        if self.xml != '':
            id = self.find_id('Volume flow')
        else:
            log.error('use read() first'); id = None
        if id != None:
            return self.parse1(id) # l/h
        else:
            return None

    def get_temperatures(self):
        ''' returns a tuple of onflow and return temperatures, kamtrup402 also diff_temp '''
        tdif = None
        if self.xml != '':
            id = self.find_id('Flow temperature')
            ton = self.parse1(id) #
            id = self.find_id('Return temperature')
            tret = self.parse1(id) #
            if self.model == 'kamstrup402':
                id = self.find_id('Temperature Difference')
                tdif = self.parse1(id) #
            return ton, tret, tdif
        else:
            log.error('use read() first')
        return None


    def get_all(self): # kogu info nagemiseks vt self.xml
        out = {}
        conf = self.modeldata[self.model]
        if self.xml != '':
            for id in conf:
                name = ''
                member = None
                value = self.parse1(id)
                for svc in self.svclist:
                    if svc[2] == id:
                        #print('matching svc and id',svc,id)
                        name, member = svc[0:2]
                out.update({id:[conf[id][0], value, name, member]})
            return list(out.values())
        else:
            log.error('use read() first')
        return None
