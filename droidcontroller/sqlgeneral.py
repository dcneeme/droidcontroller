#to be imported into modbus_sql. needs mb and conn

import time, datetime
import sqlite3
import traceback
import sys
from pymodbus import *
from droidcontroller.comm_modbus import CommModbus  # contains CommModbus, .read(), .write()
from uniscada import *

try:
    if udp:
        print('uniscada connection already existing to',host,port)
except:
    udp=UDPchannel()
    print('created uniscada UDP connection instance')
    tcp=TCPchannel()
    print('created uniscada TCP connection instance')


try:
    if conn:
        print('sqlite connection already existing')
except:
    conn = sqlite3.connect(':memory:')
    print('created sqlite connection')


try:
    if mb:
        print('modbus connection(s) already existing')
except:
    # several connections may be needed, tuple of modbus connections! also direct rtu, rtu via tcp-serial or tcp-modbustcp
    sql=open('devices.sql').read() # (num integer,rtuaddr integer,tcpaddr)
    conn.executescript(sql) # read table into database 
    conn.commit()
    mb=[]
    Cmd="select mbi, tcpaddr from devices group by mbi"
    cur=conn.cursor()
    cur.execute(Cmd)
    conn.commit()
    for row in cur:
        if ':' in row[1]:
            mb.append(CommModbus(host=row[1].split(':')[0], port=int(row[1].split(':')[1]))) # tcp
        #FIXME handle serial or xport connections too!
    print('created modbus connection(s)')



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


    def test_mbread(self, mba, reg, count = 1, mbi=0): # mbi only defines mb[] to be used
        return mb[mbi].read(mba,reg,count)


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

