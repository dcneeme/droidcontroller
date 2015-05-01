# This Python file uses the following encoding: utf-8

''' Send out Nagios passive check messages as UDP, translation based on 
register name and service table as in uniscada server.
'''
import time, sys, traceback, sqlite3
from socket import *
import logging
log = logging.getLogger(__name__)

#class NagiosMessage(SQLgeneral):
class NagiosMessage(object):
    ''' Generate Nagios passive check commands for parallel notification and send as UDP '''
    def __init__(self, host_id, table, nagios_ip='10.0.0.253', nagios_port=50000):
        self.table = table
        self.host_id = host_id
        self.conn = sqlite3.connect(':memory:')
        self.cur = self.conn.cursor()
        self.sqlread() # read in service translation table from sql file

        self.nagaddr = (nagios_ip, nagios_port) # tuple
        self.UDPnagSock = socket(AF_INET,SOCK_DGRAM)
        self.UDPnagSock.settimeout(None) # no answer from nagios

        log.info('init done')


    def sqlread(self): # drops table and reads from file <table>.sql that must exist
        ''' Reads service description table to be used in translation into nagios passive check format '''
        sql=''
        filename=self.table+'.sql' # the file to read from
        try:
            #with open(filename, 'r', encoding="utf-8", errors="surrogateescape") as f:
            with open(filename, 'r', encoding="utf-8") as f:
                sql = f.read()
                msg='found '+filename
                log.info(msg)
        except:
            msg='FAILURE in opening '+filename+': '+str(sys.exc_info()[1])
            print(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1

        Cmd='drop table if exists '+self.table
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.commit()
            self.conn.executescript(sql) # read table into database
            self.conn.commit()
            msg='sqlread: successfully created table '+self.table
            log.info(msg)
            print(msg)
            #udp.syslog(msg)
            return 0

        except:
            msg='sqlread() problem for table '+self.table+': '+str(sys.exc_info()[1])
            log.warning(msg)
            print(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1


    def output(self, sendtuple):    # sendtuple = [sta_reg,status,val_reg,lisa]
        ''' Returns Nagios passive check message based on sendtuple '''
        sta_reg = sendtuple[0]
        status = sendtuple[1]
        val_reg = sendtuple[2]
        value = sendtuple[3]
        timestamp = int(time.time())
        svc_name = 'UndefSvc'
        conv_coef = ''
        desc = 'UndefDesc'
        multiperf = []
        out_unit = 'UndefUnit'
        #cur = self.conn.cursor()

        Cmd="select svc_name,out_unit,conv_coef,desc0,desc1,desc2,multiperf from "+self.table+" where sta_reg = '"+sta_reg+"' or val_reg = '"+val_reg+"'"
        #log.info(Cmd)
        #print(Cmd)
        self.cur.execute(Cmd)
        self.conn.commit()
        notfound = 1
        for row in self.cur:
            notfound = 0
            #print(repr(row))
            svc_name = row[0]
            out_unit = row[1]
            conv_coef = row[2]
            desc = row[3+status]
            multiperf = row[6].split(' ') # list

        if notfound > 0:
            print('translation for sendtuple '+str(sendtuple)+' not found in table '+self.table)
            return '' # will not send this service 

        if svc_name[0] == '_': # skip, not needed for another nagios
            log.debug('skipped sending debug service '+svc_name)
            return ''
        
        nagstring = "["+str(timestamp)+"] PROCESS_SERVICE_CHECK_RESULT;"+self.host_id+";"+svc_name+";"+str(status)+";"+desc+"|"
        # siia otsa perfdata
        perfdata = ''
        #print('multiperf '+str(multiperf))
        
        if len(multiperf) > 1 and conv_coef != '': # multimember value
            for i in range(len(multiperf)):
                if len(perfdata) > 0:
                    perfdata += ' '
                perfdata += multiperf[i] + '='+str(round(1.0 * int(value.split(' ')[i]) / int(conv_coef),2)) + out_unit

        elif len(multiperf) == 1 and conv_coef != '': # single member numeric value
            perfdata += svc_name + '='+str(round(1.0 * int(value) / int(conv_coef),2)) + out_unit
            
        else: # single member string value
            if value != None and value != '':
                perfdata += svc_name + '='+str(value)+out_unit
            else:
                perfdata += svc_name + '='+str(status)
        nagstring += perfdata+"\n"

        return nagstring


    def send(self, msg):
        ''' Send Nagios passive check as udp message to self.nagaddr '''
        if len(msg) > 20: # nagios passive check message cannot be too short
            try: #
                self.UDPnagSock.sendto(msg.encode('utf-8'),self.nagaddr)
                dnsize=len(msg) # udp out increase, payload only
                #print('sent nagios message to '+repr(self.nagaddr)+': '+msg)
                log.debug('sent nagios message to '+repr(self.nagaddr))
                return dnsize
            except:
                print('could NOT send nagios message to '+repr(self.nagaddr))
                log.warning('could NOT send nagios message to '+repr(self.nagaddr))
                traceback.print_exc()
            return 0

            
    def output_and_send(self, sendtuple):
        ''' Format and send Nagios passive chk. Called from UDPchannel on every uniscada notification '''
        self.send(self.output(sendtuple))
        
    #END
