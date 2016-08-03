# 
# Copyright 2016-> BaseN Corporation
# See http://www.basen.net
#
# A generic M-Bus reader.

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
from mbus.MBusLowLevel import MBUS_ADDRESS_NETWORK_LAYER
import xmltodict
import os

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
        self.baudrate = config.get(NAME, "baudrate")
        self.host = config.get(NAME, "host")
        self.config = config

    def gpioRed(self,state):
        os.system('sudo /usr/local/bin/gpioleds.sh RED '+str(state))

    def gpioGreen(self,state):
        os.system('sudo /usr/local/bin/gpioleds.sh GREEN '+str(state))

    def run(self):
        """Run the task and send/store result."""

        self.gpioRed(0)
        ids = self.slaveids.split(",")
    
        origPath = self.path
        #loop over all known slave ids, each is stored in a separate subpath
        for id in ids:
            # id = int(id)
            
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
        tcpConn = False
        if(len(self.host)>0):
            tcpConn = True
            tcpHost = self.host.split(":")[0]
            tcpPort = self.host.split(":")[1]
                
        if(tcpConn):
            try:
                mbus = MBus(host=str(tcpHost),port=int(tcpPort))
                mbus.connect()
            except:
                row.addString("Error", 'MBus TCP connection failed, '+host+':'+str(port),"","")
                logging.error('MBus TCP connection failed, '+host+':'+str(port))
                self.gpioRed(1)
                return msg
        else:   
            try:
                mbus = MBus(device=self.port)
                mbus.connect()
            except:
                row.addString("Error", 'Mbus connection NOT possible, probably no suitable USB port found!',"","")
                logging.error('Mbus connection NOT possible, probably no suitable USB port found!')
                self.gpioRed(1)
                return msg

        try:
            if(tcpConn==False):
                os.system("stty " + str(self.baudrate) + " < " + self.port)
                # print(os.system("stty -a < /dev/ttyUSB0"))
            reply=mbus.recv_frame()
        except:
            pass

        loops=0
        reply=None
        while loops<2:
            if(tcpConn==False):
                os.system("stty " + str(self.baudrate) + " < " + self.port)
            try:
                if( len(slaveid) == 16 ):
                    # secondary
                    mbus.select_secondary_address(slaveid)
                    mbus.send_request_frame(MBUS_ADDRESS_NETWORK_LAYER)
                else:
                    # primary
                    mbus.send_request_frame(int(slaveid))
                reply = mbus.recv_frame()
                loops=2
            except:
                loops+=1

        if reply==None:
            row.addString("Error", 'Nothing received from slave, '+str(slaveid),"","")
            logging.error('Nothing received from slave, '+str(slaveid))
            self.gpioRed(1)
            return msg
                
        try:       
            reply_data = mbus.frame_data_parse(reply)
            xml = mbus.frame_data_xml(reply_data)
            mbus.disconnect()
            if debug:
                print(xml)
        except:
            row.addString("Error", 'M-Bus data parse failure',"","")
            logging.error('M-Bus data parse failure')
            self.gpioRed(1)
            return msg

        try:
            dict = xmltodict.parse(xml)
        except Exception as ex:
            logging.error("parse error: %s" % ex)
            row.addString("Error", "parse error: %s" % ex,"","")
            self.gpioRed(1)
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
            self.gpioRed(1)
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
                self.gpioRed(1)
                return msg

        logging.debug("Done")
        # self.gpioGreen(0)
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
