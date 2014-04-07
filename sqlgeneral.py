#to be imported into modbus_sql. needs mb and conn

import time, datetime
import sqlite3
import traceback
import sys
from pymodbus import *
from comm_modbus import *  # contains CommModbus, .read(), .write()
from uniscada import *

try:
    if udp:
        print('uniscada connection already existing to',host,port)
except: 
    udp=UDPchannel(ip='46.183.73.35')
    print('created uniscada connection')

    
try:
    if mb:
        print('modbus connection already existing to',host,port)
except: 
    mb = CommModbus(host='10.0.0.108', port=10502)
    print('created modbus connection')

        
try:
    if conn:
        print('sqlite connection already existing')
except:
    conn = sqlite3.connect(':memory:')
    print('created sqlite connection')
 
    
            

class SQLgeneral(UDPchannel): # parent class for Achannels, Dchannels, Counters
    ''' Access to io by modbus slave/register addresses and also via services. modbus client must be opened before.
        able to sync input and output channels and accept changes to service members by their sta_reg code
    '''
    def __init__(self): # , host = '127.0.0.1', port = 502):
        #self.mb = CommModbus(self, host, port) # ei funka!
        #self.conn = sqlite3.connect(':memory:')
        pass
    
    def dump_table(self,table):
        ''' reads the content of the table, debugging needs only '''
        ''' reads the content of the table, debugging needs only '''
        Cmd ="SELECT * from "+table
        cur = conn.cursor()
        cur.execute(Cmd)
        for row in cur:
            print(repr(row))

    
    def test_mbread(self, mba, reg, count = 1):
        #return self.mb.read(mba,reg,count)
        return mb.read(mba,reg,count)

    
    def sqlread(self,table): # drops table and reads from file table.sql that must exist
        filename=table+'.sql' # the file to read from
        try:
            sql = open(filename).read()
        except:
            msg='FAILURE in sqlread: '+str(sys.exc_info()[1]) # aochannels ei pruugi olemas olla alati!
            print(msg)
            #syslog(msg)
            #traceback.print_exc()
            time.sleep(1)
            return 1

        Cmd='drop table if exists '+table
        try:
            conn.execute(Cmd) # drop the table if it exists
            conn.executescript(sql) # read table into database
            conn.commit()
            #self.conn.execute(Cmd) # drop the table if it exists
            #self.conn.executescript(sql) # read table into database
            #self.conn.commit()
            msg='sqlread: successfully recreated table '+table
            print(msg)
            #syslog(msg)
            time.sleep(0.5)
            return 0
        except:
            msg='sqlread: '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            #traceback.print_exc()
            time.sleep(1)
            return 1

