#!/usr/bin/python3

''' 
    This is example of async communication with mybasen server, where no blocking until response is happening.
    Modbus register read can be used in async mode too, but the delay there is smaller.
    This is a simple example with only one address to read, feel free to modify.
    
    Example of delayed response, that does not stop the program flow:
    2015-12-28 07:29:59,447 INFO PUT data to myBaseN
    2015-12-28 07:30:00,409 INFO HTTP RESPONSE: b'[{"info":"Wrote 1 rows","duration":0,"error":0}]'
    2015-12-28 07:30:01,460 INFO PUT data to myBaseN
    2015-12-28 07:30:03,499 INFO PUT data to myBaseN
    2015-12-28 07:30:03,609 INFO HTTP RESPONSE: b'[{"info":"Wrote 1 rows","duration":0,"error":0}]' # delayed response
    2015-12-28 07:30:04,481 INFO HTTP RESPONSE: b'[{"info":"Wrote 1 rows","duration":0,"error":0}]' # delayed response
    2015-12-28 07:30:05,447 INFO PUT data to myBaseN
    2015-12-28 07:30:06,397 INFO HTTP RESPONSE: b'[{"info":"Wrote 1 rows","duration":0,"error":0}]'

'''  

modbus_port = '/dev/ttyAPP0' # /dev/ttyUSB0
modbus_speed = 19200
serial_timeout = 0.5
slave_addr = 1
register = 2 # ai1
count = 1

basen_subpath = 'tempdemo'
basen_aid = 'itvilla'
basen_uid = b'itvilla'
basen_passwd = 'MxPZcbkjdFF5uEF9'
basen_url = 'https://mybasen.pilot.basen.com/_ua/' + basen_aid + '/v0.1/data'

mybasen_device = 'it5888'

from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.register_read_message import ReadHoldingRegistersResponse

import time
import traceback

import tornado
import tornado.ioloop

import logging
#logging.basicConfig()
logging.basicConfig(format='%(name)-30s: %(asctime)s %(levelname)s %(message)s') # with time
log = logging.getLogger("")
log.setLevel(logging.INFO)

class ModbusRead(object):
    def __init__(self, modbus_port, modbus_speed, serial_timeout, slave_addr, register, count):
        self.client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=modbus_speed, timeout=serial_timeout, port=modbus_port)
        self.slave_addr = slave_addr
        # channels/addresses to query could be defined as dictionary here

    def read(self, address=2, count=1): # this is not yet async (blocks until response). pymodbus serial async version is ready, tcp async coming.
        res = self.client.read_holding_registers(address=address, count=count, unit=self.slave_addr)
        try:
            if isinstance(res, ReadHoldingRegistersResponse):
                #log.info("READ: %0.2f", res.registers[0])
                log.info("READ: %d", res.registers[0]) # integer from there!
                return res.registers[0]
            else:
                log.error("ERROR reading register: %s", str(res))
                return
        except:
            traceback.print_exc()
            
import tornado.httpclient
import json

class MyBaseN(object):
    def __init__(self, user, password):
        self.user = user
        self.password = password

    def write(self, path, temp): # temp is the measurement result (single value for now)
        '''
            compose request and send to my.BaseN server

            request will look like this:

            req = [{
                "dstore": {
                    "path": path,
                    "rows": [
                        {
                            "channels": [
                                {
                                    "channel": "temp",
                                    "double": temp
                                },
                            ]
                        },
                    ]
                },
            }]
        '''

        channels = []
        channels.append({ "channel": "temp", "double": temp })
        rows = []
        rows.append({ "channels": channels })
        dstore = { "path": path, "rows": rows }
        req = []
        req.append({ "dstore": dstore })

        headers = { "Content-Type": "application/json; charset=utf-8" }
        log.info("PUT data to myBaseN")
        tornado.httpclient.AsyncHTTPClient().fetch(basen_url, self._httpreply, method='PUT', headers=headers, body=json.dumps(req), 
            auth_mode="basic", auth_username=self.user, auth_password=self.password) # response to httpreply whern it comes, without blocking

    def _httpreply(self, response):
        if response.error:
            log.error("HTTP ERROR: %s", str(response.error))
        else:
            log.info("HTTP RESPONSE: %s", response.body)


class Controller(object):
    def __init__(self):
        self.mr = ModbusRead(modbus_port, modbus_speed, serial_timeout, slave_addr, register, count)
        self.ms = MyBaseN(basen_uid, basen_passwd)
        self.loop = tornado.ioloop.IOLoop.instance()
        self.runner = tornado.ioloop.PeriodicCallback(self.run, 2000, io_loop = self.loop) # measure and send every 2 seconds
        self.runner.start()

    def run(self):
        temp = self.mr.read()
        self.ms.write('tutorial/testing/test/it5888', temp)


x = Controller()
tornado.ioloop.IOLoop.instance().start()
