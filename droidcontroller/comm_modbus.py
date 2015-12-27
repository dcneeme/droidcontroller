# This Python file uses the following encoding: utf-8

# additional modules by neeme in the end!

from droidcontroller.comm import Comm
from pymodbus import *
from pymodbus.exceptions import *
from pymodbus.transaction import * # needed for ModbusRtuFramer but also ModbusTcpFramer?
#from pymodbus.transaction import ModbusRtuFramer
from pymodbus.register_read_message import ReadHoldingRegistersResponse, ReadInputRegistersResponse
from pymodbus.register_write_message import WriteMultipleRegistersResponse, WriteSingleRegisterResponse
import traceback
import subprocess # could not use p.subexec()
import sys # to return sys.exc_info()[1])
import time # had no effect in init for type 'u' only

import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

# USE FAST VERSION OF PYMODBUS! 0.5 s timepout for RTU

class CommModbus(Comm):
    ''' Implementation of Modbus communications
        also reads and writes io via subprocess, like
        >>> mb[0].read(1,100,4)
        [0, 0, 0, 0]

        Use improved by cougar ModbusClient package with expected response length calculation!
        Otherwise 0.5 s tout is used for every transaction!!
    '''

    def __init__(self, **kwargs):
        ''' Initialize Modbus client

        For Modbus serial client use:
        :param method: The method to use for serial connection (ascii, rtu, binary)
        :param stopbits: The number of stop bits to use
        :param bytesize: The bytesize of the serial messages
        :param parity: Which kind of parity to use
        :param baudrate: The baud rate to use for the serial device
        :param timeout: The timeout between serial requests (default 3s)
        :param port: The serial port to attach to

        For ModbusTCP client use:
        :param host: The host to connect to (default 127.0.0.1)
        :param port: The modbus port to connect to (default 502)
        : framer=ModbusRtuFramer   # if rtu over tcp

        Optional parameters:
        :param indata: optional InData object
        :param scheduler: optional PollScheduler object
        :param type can be 'n'. 'h', 'i' or 'c' to define the type of register or access channel (subexec() in case of n).

        '''

        self.errorcount = 0 # add here modbus problems, related to mba
        self.errors = {} # {mba:errcount}, per modbus address
        self.type = '' # normal modbus, may be changed to n or u for npe
        self.port = None # only for tcp or rtu over tcp, numeric not com port name!
        self.host = None # can be com port name or ip address
        self.speed = kwargs.get('speed','19200') # default speed 19200
        self.parity = kwargs.get('parity','E') # default EVEN
        
        self.mba_keepalive = kwargs.get('mba_keepalive',1) # this address must work, recreates mb[] if not
        #print(kwargs) # debug
            
        if ('host' in kwargs): # tcp or serial
            self.host = kwargs.get('host','127.0.0.1')
            if '/dev/tty' in self.host: # direct serial connection defined via host
                self.port = kwargs.get('host')
                self.do_serialclient(port = self.port, speed = self.speed, parity = self.parity)
                #from pymodbus.client.sync import ModbusSerialClient as ModbusClient
                #self.client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=19200, timeout=0.5, port=kwargs.get('host'))
                #log.info('CommModbus() init2: created CommModbus instance for ModbusRTU over RS485 using params '+str(kwargs))
                
            elif ('port' in kwargs): # both host and port - must be tcp, but possibly rtu over tcp
                self.port = kwargs.get('port')
                
                from pymodbus.client.sync import ModbusTcpClient as ModbusClient
                
                if self.port == 23 or (self.port > 10000 and self.port<10003): # xport, rtu over tcp, port 23 for esp8266
                    try:
                        self.client = ModbusClient(
                            host = self.host,
                            port = self.port,
                            framer = ModbusRtuFramer)
                        log.info('CommModbus() init3: created CommModbus instance for ModbusRTU over TCP using params '+str(kwargs))
                        print('CommModbus() init3: created CommModbus instance for ModbusRTU over TCP using params '+str(kwargs))
                    except:
                        log.warning('failed to create CommModbus instance for ModbusRTU over TCP using params '+str(kwargs))
                        traceback.print_exc()
                        
                else: # normal modbustcp
                    self.type='' # normal modbus
                    self.client = ModbusClient(
                            host = self.host,
                            port = self.port )
                    log.info('CommModbus() init4: created CommModbus instance for ModbusTCP over TCP using params '+str(kwargs))
            
        else: # serial - siin port COM...?
            try:
                self.port = kwargs.get('port')
                self.do_serialclient(port = self.port, speed = self.speed, parity = self.parity) # change params later if needed via set_serial()
                #from pymodbus.client.sync import ModbusSerialClient as ModbusClient
                #self.client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=19200, timeout=0.5, port=port)
                #print('CommModbus() init5: created CommModbus instance for ModbusRTU over RS485 using params '+str(kwargs))
                #log.info('CommModbus() init5: created CommModbus instance for ModbusRTU over RS485 using using params '+str(kwargs))
            except:
                log.warning('failed to create CommModbus instance for ModbusRTU over RS485using params '+str(kwargs))
                traceback.print_exc()
                

    def do_serialclient(self, port, speed=19200, parity='E', timeout=0.5, bytesize=8, stopbits=1):
        ''' create self.client of correct type for serial connections only '''
        from pymodbus.client.sync import ModbusSerialClient as ModbusClient
        self.port = port
        self.speed = speed
        self.parity = parity
        self.timeout = timeout
        self.timeout = bytesize
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.client = ModbusClient(method='rtu', stopbits=stopbits, bytesize=bytesize, parity=parity, baudrate=speed, timeout=timeout, port=port)
        log.info('serial ModbusClient (re)created with params '+str(self.port)+', '+str(self.speed)+' '+str(bytesize)+parity+str(stopbits))
                

    def set_serial(self, port='/dev/ttyAPP0', speed=19200, parity = 'E', timeout = 0.5,  bytesize=8, stopbits=1):
        ''' to change the speed and other params '''
        # FIXME / kontrolli et host jms alusel ikka serial...
        self.do_serialclient(port, speed, parity, timeout, bytesize, stopbits)
        
        
    def get_serial(self):
        ''' returns serial params like port 8N1 '''
        params = str(self.port)+' '+str(self.speed)+' '+str(self.bytesize)+self.parity+str(self.stopbits)
        # better to return the data directly usable by set_serial... FIXME
        return params
        
        
    def get_mba_keepalive(self):
        ''' returns mba to keep accessible by recreating mb instance by dcannels or acchannels ''' 
        return self.mba_keepalive # by default 1
        
    def get_errorcount(self):
        ''' returns number of errors, becomes 0 after each successful modbus transaction '''
        return self.errorcount # one simple number, does not say anything about individual devices


    def get_errors(self):
        ''' returns array of errorcounts per modbua aadress, becomes 0 after each successful modbus transaction '''
        return self.errors # array mba:errcount


    def set_errorcount(self,invar):
        ''' Sets number of errors '''
        self.errorcount = invar
        return 0


    def get_type(self):
        ''' returns type, to mark special comm channels to be used if not empty. n - npe_io '''
        return self.type


    def get_host(self):
        ''' returns type, to mark special comm channels to be used if not empty. n - npe_io '''
        return self.host


    def get_port(self):
        ''' returns type, to mark special comm channels to be used if not empty. n - npe_io '''
        return self.port


    def _poller(self, id, **kwargs):
        ''' Read Modbus register and write to storage

        :param id: scheduled timer id
        :param kwargs['name']: storage entry name
        :param kwargs['mba']: Modbus device address
        :param kwargs['reg']: Modbus register address
        :param kwargs['count']: Modbus register count
        :param kwargs['statuscb']: optional callback function for status info
        :param kwargs['convertcb']: optional callback function for data conversion

        After every read call first the data conversion callback function
            name:   storage entry name
            datain: data array

        read new data from it and then call the status callback function with:
            name:   storage entry name
            action:
                    onRead - normal read
                    onChange - old storage entry was different
                    onError - Modbus read error
        '''
        try:
            res = self.client.read_holding_registers(
                    address=kwargs['reg'],
                    count=kwargs['count'],
                    unit=kwargs['mba'])
        except:
            self.on_error(id, **kwargs)
            return

        if (not isinstance(res, ReadHoldingRegistersResponse)):
            self.on_error(id, **kwargs)
            return

        self.on_data(id, res.registers, **kwargs)


    def add_error(self, mba, error):
        ''' Updates directory member, resets if 0 or adds if 1 '''
        if error == 0: # ok
            if mba in self.errors:
                self.errors[mba] = 0
            else:
                self.errors.update({ mba:0 })
        else:
            if mba in self.errors:
                self.errors[mba] += 1
            else:
                self.errors.update({ mba:1 })


    def read(self, mba, reg, count = 1, type = 'h', format='dec'): # FIXME format
        ''' Read Modbus register(s), either holding (type h), input (type i) or coils (type c).
            Exceptionally can be npe_io too, type n then!
        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'count': Modbus register count
        :param 'type': Modbus register type, h = holding, i = input, c = coil
        :param 'format': output word format, 'hex' or 'dec'

        '''
        #dummy=0
        if self.type == 'n' or self.type == 'u':  # type switch for npe_io
            type=self.type  # this instance does not use modbus at all! for npe_io!

        # actual reading
        if type == 'h':
            #res = self.client.read_holding_registers(address=reg, count=count, unit=mba)
            try:
                res = self.client.read_holding_registers(address=reg, count=count, unit=mba)
                if isinstance(res, ReadHoldingRegistersResponse):
                    self.errorcount = 0
                    self.add_error(mba, 0)
                    return res.registers
                else:
                    log.warning('got no response to read (h) from mba '+str(mba)+', reg '+str(reg)+', count '+str(count))
                    self.errorcount += 1
                    self.add_error(mba, 1)
                    return None
            except:
                log.warning('modbus read (h) failed from mba '+str(mba)+', reg '+str(reg)+', count '+str(count))
                traceback.print_exc()
                self.errorcount += 1
                self.add_error(mba, 1)
                return None

        elif type == 'i':
            try:
                res = self.client.read_input_registers(address=reg, count=count, unit=mba)
                if isinstance(res, ReadInputRegistersResponse):
                    self.errorcount = 0
                    self.add_error(mba, 0)
                    return res.registers
                else:
                    log.warning('got no response to read (i) from mba '+str(mba)+', reg '+str(reg)+', count '+str(count))
                    self.errorcount += 1
                    self.add_error(mba, 1)
                    return None

            except:
                log.warning('modbus read (i) failed from mba '+str(mba)+', reg '+str(reg)+', count '+str(count))
                traceback.print_exc()
                self.errorcount += 1
                self.add_error(mba, 1)
                return None

        elif type == 'c':
            try:
                #FIXME #res = self.client.read_input_registers(address=reg, count=count, unit=mba)
                #self.errorcount = 0
                return res.registers
            except:
                traceback.print_exc()
                #self.on_error(id, **kwargs)
                self.errorcount += 1
                self.add_error(mba, 1)
                return None

        elif type == 'n': # npe_io  ##################### NPE subprocess() READ ##################
            #print('npe_io read: reg,count',reg,count) # debug
            try:
                res = self.npe_read(reg, count) # mba ignored
                #print('npe_read() returned:', res) # debug
                if len(res)>0:
                    registers=[int(eval(i)) for i in res.split(' ')] # possible str to int
                    self.errorcount = 0
                    return registers
                else:
                    log.warning('no data from npe_read.sh, error: '+str(sys.exc_info()[1]))
                    return None
            except:
                traceback.print_exc() # self.on_error(id, **kwargs)
                self.errorcount += 1
                return None

        elif type == 'u': # npe_io over udp ##################### NPE socat READ ##################
            #print('npe_io read over udp: reg,count',reg,count) # debug
            # for types b or p use udpcomm() directly
            try:
                res = self.udpcomm(reg, count, 'rs') # use 'rs' to get current (not previous) reading, delayed! use rs for now
                # FIXME - using type is able NOT to update 200,4...
                #print('udpcomm() returned:', res,'for reg',reg) # debug
                if res != None and len(res)>0:
                    #registers=[int(eval(i)) for i in res.split(' ')] # possible str to int
                    self.errorcount = 0
                    return res
                else:
                    #print('no fresh data from npe_io.sh yet, returning previous!') # debug
                    #return self.datadict[reg]
                    self.errorcount += 1 # if high enough, do something
                    return None
            except:
                traceback.print_exc() # self.on_error(id, **kwargs)
                self.errorcount += 1
                return None

        else:
            log.warning('unknown type '+str(type))
            self.errorcount += 1
            return None



    def write(self, mba, reg, type = 'h', **kwargs): # add value or values tuple to write them!
        ''' Write Modbus register(s), either holding or coils. Returns exit status.

        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'type': Modbus register type, h = holding, c = coil
        :param kwargs['count']: Modbus registers count for multiple register write
        :param kwargs['value']: Modbus register value to write
        :param kwargs['values']: Modbus registers values array to write
        '''
        res = 0

        #if self.type == 'n' or self.type == 'u':  # type switch for npe_io
        #    type=self.type  # this instance does not use modbus at all! for npe_io!

        value = kwargs.get('value', None)
        values = kwargs.get('values', None)
        
        if value == None and values == None:
            log.error('write FAILED: no required parameters value or values! mba '+str(mba)+', reg '+str(reg))
            return 2
        else:
            log.debug('going to write register mba '+str(mba)+', reg '+str(reg)+', value '+str(value)+', values '+str(values)+', type '+str(type)) 

        if type == 'h': # holding
            if value != None: # vaartus 0 annab sama tulemuse kui None!
                try:
                    res = self.client.write_register(address=reg, value=value, unit=mba)
                    if isinstance(res, WriteSingleRegisterResponse): # ok
                        self.errorcount = 0
                        self.add_error(mba, 0)
                        return 0
                    else:
                        self.add_error(mba, 1)
                        if isinstance(res, ModbusException): # viga
                            log.warning('write single register error: '+str(res))
                        else:
                            log.warning('UNKNOWN write single register error (neither response or exception), address '+str(mba)+', register '+str(reg))
                        return 2
                except:
                    log.warning('write single register error: '+str(sys.exc_info()[1]))
                    traceback.print_exc()
                    self.errorcount += 1
                    self.add_error(mba, 1)
                    return 1
            elif values != None: # and 'list' in str(type(values)): # multiple register write
                try:
                    res = self.client.write_registers(address=reg, count=len(values), unit=mba, values = values)
                    if isinstance(res, WriteMultipleRegistersResponse): # ok
                        self.errorcount = 0
                        self.add_error(mba, 0)
                        return 0
                    else:
                        self.add_error(mba, 1)
                        if isinstance(res, ModbusException): # viga
                            log.warning('write multiple register error: '+str(res))
                        else:
                            log.warning('UNKNOWN write multiple register error')
                        return 2
                except:
                    log.warning('write multiple registers error: '+str(sys.exc_info()[1]))
                    traceback.print_exc() # self.on_error(id, **kwargs)
                    self.errorcount += 1
                    self.add_error(mba, 1)
                    return 1
            else:
                log.warning('FAILED write, no value or values? mba '+str(mba)+', reg '+str(reg)+', kwargs '+str(kwargs))

        elif type == 'c': # coil
            try:
                #FIXME #res = self.client.read_input_registers(address=reg, count=count, unit=mba)
                #self.errorcount = 0
                return 0
            except:
                #traceback.print_exc() 
                self.errorcount += 1
                return 1
        elif type == 'n': # npe_io  ##################### NPE subexec WRITE ##################
            try:
                res = self.npe_write(reg, count=count, value= value) # mba ignored
                self.errorcount = 0
                return 0
            except:
                #traceback.print_exc() # self.on_error(id, **kwargs)
                log.warning('write npe register error: '+str(sys.exc_info()[1]))
                self.errorcount += 1
                return 1
        elif type == 'u': # npe_udpio  ##################### NPE socat WRITE ##################
            try:
                res = self.udpcomm(reg, value, 'w') # mba ignored. single register!
                self.errorcount = 0
                return 0
            except:
                log.warning('write udp register error: '+str(sys.exc_info()[1]))
                #traceback.print_exc() # self.on_error(id, **kwargs)
                self.errorcount += 1
                return 1

        else:
            log.error('unknown type for register to write, '+str(type))
            self.errorcount += 1
            return 2


    def subexec(self, exec_cmd, submode = 1): # submode 0 returns exit code only, 1 returns output.
        ''' shell command execution. if submode 0-, return exit status.. if 1, exit std output produced.
            FIXME: HAD TO COPY subexec HERE BECAUSE I CANNOT USE p.subexec() from here ...
        '''
        if submode == 0: # return exit status, 0 or more
            returncode=subprocess.call(exec_cmd, stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT) # waits for exit, do not care about cmd output
            return returncode  # return just the subprocess exit code
        elif submode == 1: # returns everything from sdout
            proc=subprocess.Popen(exec_cmd, shell=True, stdout=subprocess.PIPE) # shell True is dangerous!
            #proc=subprocess.Popen(exec_cmd, shell=False, stdout=subprocess.PIPE) # do not use path here
            result = proc.communicate()[0]
            return result
        elif submode == 2: # forks to background, does not wait for output
            subprocess.Popen(exec_cmd, shell=True) # dangerous, accept no no exec_cmd from outside
            # Popen(exec_cmd, shell=False) # safer, limited to use shell built-ins, no p[ath can be given. exec_cmd can be a tuple (inc params)
            # Popen(['sleep','15'], shell=False) # example of using parameters
            return 0 # no idea how it really ends



    def udpcomm(self, reg, countvalue, type = 'r'): # type r, ra or w = read or write command. ra returns existing data (async). for npe
        ''' Communicates with (sends and receives data to&from) socat on techbase NPE, where subprocess() usage should be avoided '''
        ureg = None
        i = 0
        if (type != 'r' and type != 'rs' and type != 'w' and type != 'p' and type != 'b' and type != 'bs'):
            print('udpcomm(): invalid type '+str(type))
            return None

        sendstring=str(reg)+' '+str(countvalue)+' '+type[0] # 3 parameters for both npe_write.sh or npe_read.sh
        self.UDPSock.sendto(sendstring.encode('utf-8'),self.saddr)
        #print('udpcomm sent udp msg '+sendstring+' to '+str(self.saddr)) # debug

        if type[0] == 'r' or type[0] == 'b': # some data return is needed
            if type == 'b' and reg == 10 and countvalue != 2:
                log.warning('udpcomm fixing countvalue for reg 10 type b from',countvalue,'to 2')
                countvalue = 2

            #if (not reg in self.datadict.keys() or type[-1] == 's' or (reg in self.datadict.keys() and len(self.datadict[reg]) != countvalue)):
            if type[-1] != 's' and (reg in self.datadict.keys() and len(self.datadict[reg].split(' ')) == countvalue): # give immediate response
                # query with changed parameters must wait for correct result!
                retread = self.udpread() # read buffer but do not use for output, just update datadict
                if retread != None:
                    self.update_datadict(retread)

            else: # wait until actual true response is received
                ureg = ''
                ulen = 0
                while (i<20 and ((ureg != reg) or (ulen != countvalue))): # no more than 2 s here, as socat has 2 s timeout
                    #print('wait before read') # debug - read in loop until data for right reg arrives
                    time.sleep(0.05) # wait until fresh data arrives for answer. without delay the previous read data may be returned
                    retread = self.udpread() # [data], reg. after delay the fresh one should arrive for the
                    if retread != None:
                        #print('udpcomm got from udpread:',retread) # debug
                        try:
                            ureg=int(eval(retread[0]))
                            self.update_datadict(retread)
                            ulen=len(retread[1].split(' '))
                        except:
                            traceback.print_exc()
                            return None
                    if i == 10: # still no response?
                        log.warning('udpcomm: repeating the query '+sendstring)
                        self.UDPSock.sendto(sendstring.encode('utf-8'),self.saddr) # repeat the query
                    i+=1


            if reg in self.datadict and len(self.datadict[reg].split(' ')) == countvalue: # return data from here
                #print('udpcomm: correct value for '+str(reg)+' exists: '+str(self.datadict[reg])) # debug
                #data=str(rdata.decode("utf-8")).strip('\n').split(' ') # python3 related need due to mac in hex
                if type[0] == 'b':
                    data = self.datadict[reg].split(' ')
                    #print('returning mac_ip',data) # debug
                else: # num values
                    #data=[int(eval(i)) for i in str(rdata.decode("utf-8")).strip('\n').split(' ')] # avoid dots in response too
                    data = [int(eval(i)) for i in self.datadict[reg].split(' ')] # values list
                return data
            else:
                log.warning('not what we need in datadict for reg '+str(reg)+': '+str(self.datadict))
                return None # not ready yet

        else: # write a single register or fork something over npe_io.sh. types w or p
            return None


    def update_datadict(self, retread):
        ''' Update data dictionary with data from socat for registers to be polled, to speed things up '''
        if retread != None:
            #print('going to update datadict with',retread) # debug
            #self.datadict.update({ int(eval(retread[0])) : retread[1:] }) # reg:[data]
            try:
                self.datadict.update({ int(eval(retread[0])) : retread[1:][0] }) # reg:'data'
                #print('updated datadict',self.datadict) # debug
            except:
                log.warning('update_datadict error')
                traceback.print_exc()

    def udpread(self): # not to be called from outside of this method, used only by udpsend() above
        ''' Read npe_io over socat or other udp channel. Register will be returned as the first value, may NOT be the one asked last! '''
        data = ['','']
        #print('udpread: trying to get udp data from '+str(self.saddr)) # debug
        try: # if anything is comes into udp buffer before timeout
            buf = 256
            rdata,raddr = self.UDPSock.recvfrom(buf)
            #print('udpread got rdata: ',rdata) # debug
            data=rdata.replace(' ','|',1).strip('\n').split('|')
            #print('udpread got data to return: ',data) # debug
            return data
        except:
            #print('no new udp data this time') # debug
            #traceback.print_exc() # debug
            return None

        if len(data) > 0: # something arrived
            if raddr[0] != self.ip:
                msg = 'illegal_sender'+str(raddr[0])+' for message: '+str(data)  # ignore the data received!
                print(msg)
                #syslog(msg)
                return None

