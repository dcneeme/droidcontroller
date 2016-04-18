# This Python file uses the following encoding: utf-8

''' Send out Nagios passive check messages as UDP, translation based on 
    register name and service table as in uniscada server.
    
>>> import sys, logging
>>> from droidcontroller.nagios import *
>>> n = NagiosMessage('000101100000','service_ho_koogu20_ee', debug_svc=True)
sqlread: successfully created table service_ho_koogu20_ee
>>> n.output(['D2S',0,'D2W','0 0 0 0 0 0 0 0'])
'[1460920743] PROCESS_SERVICE_CHECK_RESULT;000101100000;_DoDebug;0;DO kanalid (1..8):|_DoDebug=0 0 0 0 0 0 0 0\n'
>>> n.output(['ETS',1,'',''])
'[1460920752] PROCESS_SERVICE_CHECK_RESULT;000101100000;ElektriToide;1;Vahelduvtoide kahtlane|ElektriToide=1\n'

'''

import time, sys, traceback, sqlite3
from socket import *
import logging
log = logging.getLogger(__name__)

#class NagiosMessage(SQLgeneral):
class NagiosMessage(object):
    ''' Generate Nagios passive check commands for parallel notification and send as UDP '''
    def __init__(self, host_id, table, nagios_ip='10.0.0.253', nagios_port=50000, debug_svc = False):
        self.debug_svc = debug_svc # alakriipsuga algavaid ei edasta, kui see on False
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
            log.warning(msg)
            traceback.print_exc()
            return 1

        Cmd='drop table if exists '+self.table
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.commit()
            self.conn.executescript(sql) # read table into database
            self.conn.commit()
            msg='sqlread: successfully created table '+self.table
            log.info(msg)
            return 0

        except:
            msg='sqlread() problem for table '+self.table+': '+str(sys.exc_info()[1])
            log.warning(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1


    def floatfromhex(self, input_float):
        '''  hex float string to decimal float conversion ''' 
        sign = int(input_float[0:2],16) & 128
        exponent = (int(input_float[0:3],16) & 2047)  - 1023
        if sign == 128:
            return float.fromhex('-0x1.'+input_float[3:16]+'p'+str(exponent))
        return float.fromhex('0x1.'+input_float[3:16]+'p'+str(exponent))

        
    def output(self, sendtuple):    # sendtuple = ['sta_reg',status,'val_reg','value']
        ''' Returns Nagios passive check message based on sendtuple. 
            Value can be missing, text, number or number array separated with spaces
        '''
        (sta_reg, status, val_reg, value) = sendtuple
        if val_reg == '':
            val_reg = sta_reg
        
        timestamp = int(time.time())
        svc_name = None
        conv_coef = ''
        desc = 'UndefDesc'
        multiperf = []
        out_unit = 'UndefUnit'
        
        Cmd="select svc_name,out_unit,conv_coef,desc0,desc1,desc2,multiperf,multivalue from "+self.table+" where sta_reg = '"+sta_reg+"' or val_reg = '"+val_reg+"'"
        #log.info(Cmd)
        self.cur.execute(Cmd)
        self.conn.commit()
        notfound = 1
        for row in self.cur:
            svc_name = row[0]
            out_unit = row[1]
            conv_coef = row[2]
            desc = row[3+status]
            multiperf = row[6].split(' ') # liikmete nimetuste list, perf datasse vordusmargi ette
            multivalue = row[7].split(' ') # liikmete jrk numbrite list, selle alusel vaartused desc loppu kooloni taha

        if not svc_name:
            log.warning('translation for sendtuple '+str(sendtuple)+' not found in table '+self.table)
            return '' # will not send this service 

        if not self.debug_svc and svc_name[0] == '_': # skip, not needed in starman
            log.debug('skipped sending debug service '+svc_name)
            return ''
        
        log.info('svc_name '+svc_name+', multiperf '+str(multiperf)+', multivalue '+str(multivalue)+', value '+str(value)) 
        perfdata = '' 
        descvalue = '' # values to desc end after colon, if any, according to multivalue
        if out_unit == '':
                out_unit = '_' # to align diagrmans with and without unit
        
        if len(multiperf) > 1: # multimember value
            log.info('num members')
            for i in range(len(multiperf)):
                if conv_coef != '':
                    valmember = round(1.0 * int(value.split(' ')[i]) / int(conv_coef),2)
                else: # int, not to divide
                    valmember = int(value.split(' ')[i])
                if len(perfdata) > 0:
                    perfdata += ' '
                perfdata += multiperf[i] + '='+str(valmember) + out_unit
                if desc[-1:] == ':' and str(i + 1) in multivalue:
                    descvalue += str(valmember) + ' '
            if desc[-1:] == ':':
                descvalue += out_unit # unit after the members
                
        elif len(multiperf) == 1 and value != '': # single member numeric value
            if (svc_name == 'FlowTotal' or svc_name == 'PumbatudKogus'  or sta_reg[-1:] == 'F'): # hex float
                value = floatfromhex(value)
                log.info('hex float to decimal conversion done, new value='+str(value))
            else:
                if conv_coef != '':
                    log.info('single num to be converted')
                    value = round(1.0 * int(value) / int(conv_coef),2)
                else: #leave value as it is
                    log.info('single num NOT to be converted due to no conf_coef, value='+str(value))
                    
            perfdata += svc_name + '='+str(value) + out_unit
            
        #elif multiperf == '' and multivalue == '' and conv_coef == '' and out_unit == '_': # status only service!
        elif val_reg == sta_reg: # status only service!
            log.info('status as perfdata')
            perfdata += svc_name + '='+str(status)+out_unit
        else:
            log.error('INVALID service configuration, svc_name '+svc_name+', multiperf '+str(multiperf)+', multivalue '+str(multivalue)+', value "'+str(value)+'"')
        
        nagstring = "["+str(timestamp)+"] PROCESS_SERVICE_CHECK_RESULT;"+self.host_id+";"+svc_name+";"+str(status)+";"+desc+descvalue+"|"+perfdata+"\n"
        
        return nagstring


    def send(self, msg):
        ''' Send Nagios passive check as udp message to self.nagaddr '''
        if len(msg) > 20: # nagios passive check message cannot be too short
            try: #
                self.UDPnagSock.sendto(msg.encode('utf-8'),self.nagaddr)
                dnsize=len(msg) # udp out increase, payload only
                log.info('sent nagios message to '+repr(self.nagaddr)+': '+msg)
                #log.debug('sent nagios message to '+repr(self.nagaddr))
                return dnsize
            except:
                log.error('could NOT send nagios message to '+repr(self.nagaddr))
                traceback.print_exc()
            return 0

            
    def output_and_send(self, sendtuple):
        ''' Format and send Nagios passive chk. Called from UDPchannel on every uniscada notification '''
        self.send(self.output(sendtuple))
        
    #END
