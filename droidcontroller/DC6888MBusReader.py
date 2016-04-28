# 
# Copyright 2016-> BaseN Corporation
# See http://www.basen.net
#
# A generic M-Bus reader for DC6888 droid4linux and IT6888 IO board. Configuration specifies which slaves and which registers
# to read. Supports long, float and generic 16bit input and holding registers.
#This allows single reader to read multiple different devices with different slaves, so there is
#only one master on the bus.
#

import sys
from os import path
from configparser import SafeConfigParser
import InformerBase
import logging.handlers
import signal
import httplib2
import InformerBase
import time
from mbus.MBus import MBus
import xmltodict
# import traceback

SENDCONFFN = path.join("config", "DC6888MBusReader.cfg")
NAME = "DC6888MBusReader"


class Reader(InformerBase.InformerBase):
    """The sender."""

    def __init__(self, config):
        self.init(config)
        """Creates a new Sender.

        Args:
          config: Sender configuration (ConfigParser).
        """

    def initVariable(self,config):
        self.port = config.get(NAME, "port")
        self.slaveids = config.get(NAME, "slaveid")
        self.config = config

    def run(self):
        """Run the task and send/store result."""

        ids = self.slaveids.split(",")
    
        origPath = self.path
        #loop over all known slave ids, each is stored in a separate subpath
        for id in ids:
            id = int(id)
            
            self.path = origPath+"."+str(id)
            result = self.measure(str(id))
            asJson = self.createJSON(result)
            if asJson == None:
                quit()
            saveOk = self.sendmessage(asJson)
            if saveOk:
                """Do nothing"""
            else:
                self.store(asJson)
         
    def measure(self,slaveid):
        
        origPath = self.path
        msg = InformerBase.JSONMessage()
        timestamp = self.getTimestamp()
        row = msg.addRow(timestamp)
        row.setSubPath('log')

        debug = False
        
        svclist=[['XYW',1,1,'undefined']]
        #self.svclist = svclist # svc, member, id, name

        try:
            mbus = MBus(device=self.port)
            mbus.connect()
        except:
            row.addString("Error", 'Mbus connection NOT possible, probably no suitable USB port found!',"","")
            logging.error('Mbus connection NOT possible, probably no suitable USB port found!')
            return msg

        try:
            mbus.send_request_frame(0xFE) # Wrong address, MBUS_ADDRESS_BROADCAST_REPLY
            reply = mbus.recv_frame()
            reply_data = mbus.frame_data_parse(reply)
            xml = mbus.frame_data_xml(reply_data)
            mbus.disconnect()
            if debug:
                print(xml)
        except:
            row.addString("Error", 'FAILED to get data from mbus',"","")
            logging.error('FAILED to get data from mbus')
            return msg

        try:
            dict = xmltodict.parse(xml)
        except Exception as ex:
            logging.error("parse error: %s" % ex)
            row.addString("Error", "parse error: %s" % ex,"","")
            return msg

        # Parse SlaveInformation
        row = msg.addRow(timestamp)
        row.setSubPath("slaveinformation")
        try:
            si = dict['MBusData']['SlaveInformation']
            row.addString('Id',si['Id'],'','')
            row.addString('Manufacturer',si['Manufacturer'],'','')
            row.addLong('Version',si['Version'],'','')
            row.addString('ProductName',si['ProductName'],'','')
            row.addString('Medium',si['Medium'],'','')
            row.addLong('AccessNumber',si['AccessNumber'],'','')
            row.addLong('Status',si['Status'],'','')
            row.addLong('Signature',si['Signature'],'','')
        except Exception as ex:
            logging.error("SlaveInformation parse error: %s" % ex)
            row.addString("Error", "SlaveInformation parse error: %s" % ex,"","")
            return msg
            
        # Parse each DataRecord
        for x in dict['MBusData']['DataRecord']:
            row = msg.addRow(timestamp)
            row.setSubPath("id"+x['@id'])
            try:
                row.addLong('id',x['@id'],'','')
                row.addString('Function',x['Function'],'','')
                row.addLong('StorageNumber',x['StorageNumber'],'','')
                row.addString('Unit',x['Unit'],'','')
                row.addLong('Value',x['Value'],'','')
                #row.addString('Timestamp',x['Timestamp'],'','')
            except Exception as ex:
                logging.error("DataRecord parse error: %s" % ex)
                row.addString("Error", "DataRecord parse error: %s" % ex,"","")
                return msg

        logging.debug("Done")
        return msg

def sigtermhandler(signum, frame):
    """Default SIGTERM handler."""
    logging.debug( "Received SIGTERM, terminating..." )
    sys.exit(0)

def main():
    
    sendconf = SafeConfigParser()
    sendconf.read(SENDCONFFN)
    try:
        sender = Reader(sendconf)
        sender.run()
    except Exception as e:
        logging.error("Died of an exception: %s: %s" % (
                e.__class__.__name__, str(e)))
        raise

if __name__ == "__main__":
    main()
