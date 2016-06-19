# This Python file uses the following encoding: utf-8

''' Send out Nagios passive check messages or mybasen messages, translation based on 
    register name and service table. usable both in uniscada receiver or uniscada compatible microagent.
    
  possible testing in 10.0.0.14  
>>> import sys, logging
>>> from droidcontroller.nagios import *
>>> n = NagiosMessage('000101100000','service_ho_koogu20_ee', debug_svc=True) or n = NagiosMessage('host_dummy', debug_svc = True)
sqlread: successfully created table service_ho_koogu20_ee
>>> n.output(['D2S',0,'D2W','0 0 0 0 0 0 0 0'])
'[1460920743] PROCESS_SERVICE_CHECK_RESULT;000101100000;_DoDebug;0;DO kanalid (1..8):|_DoDebug=0 0 0 0 0 0 0 0\n'
>>> n.output(['ETS',1,'',''])
'[1460920752] PROCESS_SERVICE_CHECK_RESULT;000101100000;ElektriToide;1;Vahelduvtoide kahtlane|ElektriToide=1\n'
without sql in use>

>>> n.convert(('PWS',0,'PWW','0 1'), ['uks', 'kaks'], ['1','2'], svc_name='Power', out_unit='', conv_coef='', desc='Toite olemasolu:', host_id='000101100000', format=3)
('[1466334424] PROCESS_SERVICE_CHECK_RESULT;000101100000;Power;0;Toite olemasolu: 0 1  |uks=0 kaks=1\n', 
'{"channel":"Power","double":0,"double":1,"comment":"Toite olemasolu"}')

>>> n.convert(('PWS',0,'PWV','0'), svc_name='Power', out_unit='', conv_coef='', desc='Toite olemasolu:', host_id='000101100000', format=3)
('[1466334445] PROCESS_SERVICE_CHECK_RESULT;000101100000;Power;0;Toite olemasolu: 0 |Power_status=0\n', 
'{"channel":"Power","double":0,"comment":"Toite olemasolu"}')

>>> n.convert(('PWS',0,'PWW','190 220'), multiperf=['uks', 'kaks'], multivalue=['1','2'], svc_name='Power', out_unit='kW', conv_coef='10', desc='Toitevoimsus:', host_id='000101100000', format=3)
('[1466334720] PROCESS_SERVICE_CHECK_RESULT;000101100000;Power;0;Toite olemasolu: 19.0 22.0 kW |uks=19.0kW kaks=22.0kW\n', '{"channel":"Power","double":19
.0,"double":22.0,"double":kW,"unit":"kW","comment":"Toite olemasolu"}')
'''

import time, sys, traceback, sqlite3, decimal
from socket import *
import logging
log = logging.getLogger(__name__)

#class NagiosMessage(SQLgeneral):
class NagiosMessage(object):
    ''' Generate Nagios passive check commands for parallel notification and send as UDP '''
    def __init__(self, host_id, table=None, nagios_ip='10.0.0.253', nagios_port=50000, debug_svc = False):
        self.debug_svc = debug_svc # alakriipsuga algavaid ei edasta, kui see on False
        self.decget = decimal.getcontext().copy()
        if table != None:
            self.table = table
            self.conn = sqlite3.connect(':memory:')
            self.cur = self.conn.cursor()
            self.sqlread() # read in service translation table from sql file
        else:
            log.warning('sqlite not used')
            
        self.host_id = host_id
        
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
        value = value.strip(' ')
        if val_reg == '':
            val_reg = sta_reg # status-only service
        
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
            multiperf = row[6].strip(' ').split(' ') if row[6] != None else [svc_name] # liikmete nimetuste list, perf datasse vordusmargi ette
            multivalue = row[7].strip(' ').split(' ') if row[7] != None else [] # liikmete jrk numbrite list, selle alusel vaartused desc loppu kooloni taha

        self.convert(sendtuple, svc_name, out_unit, conv_coef, desc, multiperf, multivalue)
        
        if not svc_name:
            log.warning('translation for sendtuple '+str(sendtuple)+' not found in table '+self.table)
            return '' # will not send this service 

        if not self.debug_svc and svc_name[0] == '_': # skip, not needed in starman
            log.debug('skipped sending debug service '+svc_name)
            return ''
        
        log.info('svc_name '+svc_name+', multiperf '+str(multiperf)+', multivalue '+str(multivalue)+', value '+str(value)) 
        
        if out_unit == '':
                out_unit = '_' # to align diagrams with and without unit
        
        return self.convert(sendtuple, svc_name=svc_name, out_unit=out_unit, conv_coef=conv_coef, desc=desc, multiperf=multiperf, multivalue=multivalue, host_id=self.host_id)
        
        
        
    def convert(self, sendtuple, multiperf=[], multivalue=[], svc_name='SvcName', out_unit='', conv_coef='1', desc='kirjeldus:', host_id='host?', ts=None, format=1): #1 nagios, 2 basen, 3 both
        ''' creates nagios or mybasen message based on sendtuple and configuration data. ts '''
        if not 'list' in str(type(multiperf)) or not 'list' in str(type(multivalue)):
            log.error('invalid multiperf of multivalue parameter')
            return None
            
        (sta_reg, status, val_reg, value) = sendtuple
        perfdata = '' 
        descvalue = '' # values to desc end after colon, if any, according to multivalue
        descunit = ''
        value = value.strip(' ') # str, from sendtuple[3]
        mvalues = None
        
        if val_reg == '' and sta_reg != None:
            val_reg = sta_reg # status-only service
            value = str(status)
            mvalues = [value] # status to value for mybasen
            
        if sta_reg == None and val_reg != '' and val_reg != None:   # status probably in the different datagram from older controllers!
            sta_reg = val_reg[:-1]+'S' # restore status
            status = 0

        mtype = val_reg[-1] # generally, expect T
        
        if host_id == None or svc_name == None or desc == None or host_id == None:
            log.error('invalid parameters for convert: host_id '+str(host_id)+' or svc_name '+str(svc_name)+' or desc '+str(desc))
            return None
            
        if ts != None:
            timestamp = ts
        else:
            timestamp = int(time.time()) # used for ts if None
        
        if val_reg == sta_reg: # status only service!
            if len(multiperf) > 1:
                log.error('INVALID service configuration for sta_reg '+sta_reg+', multiperf '+str(multiperf)+', multivalue '+str(multivalue)+', stopped processing '+val_reg+' for host '+host_id)
                return None
            else:
                log.debug('using status as perfdata for '+sta_reg)
                perfdata += svc_name + '='+str(status)+out_unit
    
        #elif len(multiperf) > 1: # multimember num values
        elif val_reg[-1] == 'W': # multimember num values
            mvalues = value.strip(' ').split(' ') # list on str value members
            if len(multiperf) == len(mvalues):
                membercountOK = True # member count ok, matches with dataset count
            else:
                membercountOK = False
                log.warning('non-matching count of dataset names and members ('+str(len(multiperf))+' and '+str(len(mvalues))+'): '+str(multiperf)+', value '+str(value)+', host '+host_id+', svc '+svc_name)
                
            for i in range(len(mvalues)): # loop for member adding
                try:
                    if conv_coef != '':
                        #valmember = round(1.0 * int(value.split(' ')[i]) / int(conv_coef),2)
                        valmember = round(1.0 * int(mvalues[i]) / float(conv_coef),2)
                    else: # int, not to divide
                        valmember = int(mvalues[i])
                    if len(perfdata) > 0:
                        perfdata += ' '
                    
                    if membercountOK:
                        perfdata += multiperf[i]
                    else:
                        perfdata += 'ds'+str(i+1) + out_unit
                    
                    perfdata += '='+str(valmember) + out_unit
                    mvalues[i] = str(valmember)
                    
                    if desc[-1] == ':' and str(i + 1) in multivalue:
                        descvalue += ' '+ str(valmember) # + out_unit ## siit vota out_unit ara
                except:
                    log.warning('INVALID svc '+val_reg+' '+svc_name)
                    break
                    
            if desc[-1:] == ':': # tsykkel labi, liikmevaartuste joru taha yhik
                descvalue += ' ' + out_unit # unit after the members
                
        elif (val_reg[-1] == 'V' or val_reg[-1] == 'F') and len(multiperf) < 2 and value != '': # single member numeric or string value
            # if dataset name is not given, use service name for perf data
            if (svc_name == 'FlowTotal' or svc_name == 'PumbatudKogus'  or sta_reg[-1:] == 'F'): # hex float
                value = self.floatfromhex(value)
                mvalues = [ str(value) ] # mybasen jaoks
                log.debug('hex float to decimal conversion done, new value='+str(value))
            else: ## AGA kui on string siis perf datasse olek!
                if conv_coef != '' and conv_coef != None: # single num
                    log.debug('single num to be converted')
                    #value = round(1.0 * int(value) / int(conv_coef),2)
                    value = round(1.0 * int(value) / float(conv_coef),2)
                    mvalues = [ str(value) ] # mybasen jaoks
                else: # str, add value to desc if colon, use status as value
                    mtype = 'T'
                    mvalues = [ value ] # value jaab mis oli algselt, str
                    #log.debug('value as string due to no conf_coef, value='+str(value))
                    
                    
            #perfdata += svc_name + '='+str(value) + out_unit
            if not 'str' in str(type(value)): # None?
                if multiperf == [''] or multiperf == []:  # ds nimi teenuse nimest
                    multiperf = [ svc_name ]
                perfdata += multiperf[0] + '='+str(value) + out_unit
            else:
                perfdata += svc_name + '_status='+str(status) + out_unit
            
            if desc[-1] == ':':
                descvalue += ' '+ str(value)
                if not 'str' in str(type(value)):
                    #descvalue += out_unit
                    descunit = out_unit
            
        else:
            log.error('INVALID service, svc_name '+svc_name+', sta_reg '+str(sta_reg)+', status '+str(status)+', val_reg '+str(val_reg)+', multiperf '+str(multiperf)+', multivalue '+str(multivalue)+', value "'+str(value)+'", host '+host_id)
            return None
        
        
        nagstring = "["+str(timestamp)+"] PROCESS_SERVICE_CHECK_RESULT;"+host_id+";"+svc_name+";"+str(status)+";"+desc+descvalue+' '+descunit+"|"+perfdata+"\n"
        if mvalues != None:
            mybasen_row = self.format_mybasen_row(svc_name, status, mvalues, multiperf=multiperf, comment=desc.strip(':'), unit=out_unit, mtype=mtype) # koik value liikmed lahevad kui double. yhine unit ja comment.
        else:
            log.error('missing mvalue from processing '+svc_name)
            mybasen_row = ''
        
        if format == 1:
            return nagstring
        elif format == 2:
            return mybasen_row
        elif format == 3:
            return nagstring, mybasen_row
        else:
            log.error('undefined format '+str(format))
            return None


    def format_mybasen_row(self, channel, status, mvalues, multiperf = [], comment='', unit='', mtype='V'): # possible types: S V W F T
        ''' Format mybasen channel dict. status not used yet! value as string! '''
        if not 'list' in str(type(multiperf)):
            log.error('INVALID multiperf type, must be list!')
            return None
        if not 'list' in str(type(mvalues)) or len(mvalues) == 0:
            log.error('INVALID mvalues type, must be list or str members!')
            return None
        if not 'str' in str(type(mvalues[0])):
            log.error('INVALID mvalue member type, must be str!')
            return None
        row = ''
        
        #print('formatting mybasen row type '+mtype+' for '+channel)
        if mtype == 'T': # text value
            row += "{"
            row += "\"channel\":\"" + channel + "\"," 
            row += "\"string\":\"" + mvalues[0] + "\","
            if unit != '' and unit != None:
                row += "\"unit\":\"" + unit + "\","
            if comment != '' and comment != None:
                row += "\"comment\":\"" + comment + "\""
            row = row.strip(',') # no comma in the end
            row += "}"
        
        else: # num, possibly multivalue
            for i in range(len(mvalues)):
                row += "{"
                if len(mvalues) > 1: # subchannels needed
                    if len(multiperf) >= i+1:
                        subchannel = channel + '.'+multiperf[i]
                    else:
                        subchannel = channel + '.'+str(i+1)
                    row += "\"channel\":\"" + subchannel + "\"," 
                else:
                    row += "\"channel\":\"" + channel + "\"," 
                
                row += "\"double\":" + mvalues[i] + "," 
                if unit != '' and unit != None:
                    row += "\"unit\":\"" + unit + "\","
                if comment != '' and comment != None:
                    row += "\"comment\":\"" + comment + "\""
                row = row.strip(',') # no comma in the end
                row += "},"
            row = row.strip(',') # no comma in the end
        return row
    
    
    def convert2mybasen(self, sendtuple, multiperf, multivalue, svc_name='SvcName', out_unit='', conv_coef='1', desc='kirjeldus:', host_id='host?', ts=None): # for mybasen, one svc for now
        ''' 
            {
                "channel": "Temperature",
                "double": 10.0,
                "unit": "degC",
                "comment": "Room temperature"
            }
        '''
        (sta_reg, status, val_reg, value) = sendtuple
        perfdata = '' 
        descvalue = '' # values to desc end after colon, if any, according to multivalue
        value = value.strip(' ')
        
        if val_reg == '' and sta_reg != None:
            val_reg = sta_reg # status-only service
            value = str(status) 
        if sta_reg == None and val_reg != '' and val_reg != None:   # status probably in the different datagram from older controllers!
            sta_reg = val_reg[:-1]+'S' # restore status
            status = 0
        
        if host_id == None or svc_name == None or desc == None or host_id == None:
            log.error('invalid parameters for convert: host_id '+str(host_id)+' or svc_name '+str(svc_name)+' or desc '+str(desc))
            return None
            
        if ts != None:
            timestamp = ts
        else:
            timestamp = int(time.time()) # used for ts if None
        
        if val_reg == sta_reg: # status only service!
            if len(multiperf) > 1:
                log.error('INVALID service configuration for sta_reg '+sta_reg+', multiperf '+str(multiperf)+', multivalue '+str(multivalue)+', stopped processing '+val_reg+' for host '+host_id)
                return None
            else:
                log.debug('using status as perfdata for '+sta_reg)
                perfdata += svc_name + '='+str(status)+out_unit

        if (val_reg[-1] == 'V' or val_reg[-1] == 'F' or val_reg[-1] == 'S') and value != '': # single member numeric or string value, possibly created from status alone
            if (svc_name == 'FlowTotal' or svc_name == 'PumbatudKogus'  or sta_reg[-1:] == 'F'): # hex float
                value = self.floatfromhex(value)
                log.debug('hex float to decimal conversion done, new value='+str(value))
            else: ## AGA kui on string siis perf datasse olek!
                if conv_coef != '' and conv_coef != None:
                    log.debug('single num to be converted')
                    value = round(1.0 * int(value) / float(conv_coef),2)
                        
            row = "{"
            row += "\"channel\":\"" + svc_name + "\","
            row += "\"double\":" + str(value) + ","
            if out_unit != '':
                row += "\"unit\":\"" + out_unit + "\","
            row += "\"comment\":\"" + desc.strip(':') + "\""
            row += "}"
            #log.debug(row)
            return row
        else:
            log.error('INVALID data to convert2mybasen()')
            
    
    def send(self, msg): # to nagios
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
