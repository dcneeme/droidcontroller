#!/usr/bin/python3

# old ver from 257 = 580, new 616
# 498

modbus_port = '/dev/ttyUSB0'
modbus_speed = 19200
serial_timeout = 0.1
slave_addr = 1

basen_subpath = 'tempdemo'
basen_aid = 'itvilla'
basen_uid = b'itvilla'
basen_passwd = 'MxPZcbkjdFF5uEF9'
basen_url = 'https://mybasen.pilot.basen.com/_ua/' + basen_aid + '/v0.1/data'

mybasen_device = 'it5888'

from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.register_read_message import ReadHoldingRegistersResponse

import time

import tornado
import tornado.ioloop

import logging
logging.basicConfig()
log = logging.getLogger("")
log.setLevel(logging.DEBUG)

class ModbusRead(object):
    def __init__(self, modbus_port, modbus_speed, serial_timeout, slave_addr):
        self.client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=modbus_speed, timeout=serial_timeout, port=modbus_port)
        self.slave_addr = slave_addr
        # channels/addresses to query could be defined as dictionary here

    def read(self, address=2, count=1): # this is not yet async (blocks until response). pymodbus serial async version is ready, tcp async coming.
        res = self.client.read_holding_registers(address=address, count=count, unit=self.slave_addr)
        if isinstance(res, ReadHoldingRegistersResponse):
            log.info("READ: %0.2f", res.registers[0])
            return res.registers[0]
        else:
            return
            log.error("ERROR reading register: %s", str(res))

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
        self.mr = ModbusRead(modbus_port, modbus_speed, serial_timeout, slave_addr)
        self.ms = MyBaseN(basen_uid, basen_passwd)
        self.loop = tornado.ioloop.IOLoop.instance()
        self.runner = tornado.ioloop.PeriodicCallback(self.run, 1000, io_loop = self.loop) # measure and send every second, no waiting for response
        self.runner.start()

    def run(self):
        temp = self.mr.read()
        self.ms.write('tutorial/testing/test/it5888', temp)


x = Controller()
tornado.ioloop.IOLoop.instance().start()
