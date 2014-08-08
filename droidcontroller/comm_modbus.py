# additional modules by neeme in the end!

from droidcontroller.comm import Comm
from pymodbus import * # from pymodbus.register_read_message import *
from pymodbus.register_read_message import ReadHoldingRegistersResponse
import traceback
import subprocess # could not use p.subexec()
import sys # to return sys.exc_info()[1])
import time # had no effect in init for type 'u' only

class CommModbus(Comm):
    ''' Implementation of Modbus communications
        also reads and writes io via subprocess, like
        >>> mb[0].read(1,100,4)
        [0, 0, 0, 0]


    '''

    def __init__(self, type = 'h', **kwargs):
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

        self.errorcount = 0 # add here modbus problems
        self.type = type # default h
        if ('host' in kwargs):
            self.host=kwargs.get('host','127.0.0.1')
            ###############
            if kwargs.get('host') == 'npe_io': # npe_io via subexec(), no pymodbus in use
                self.type='n' # npe_io
                print('CommModbus() init1: created CommModbus instance to use npe_read.sh and npe_write.sh via subprocess(), type',self.type)
            elif kwargs.get('host') == 'npe_udpio': # npe_io via so_comm(), via udp port 444441 to read and 44442 to write.
                self.type='u' # npe_udpio. do not forget to set this as channel type in sql too! FIXME: set up a client for that? ##############
                #from droidcontroller.npechannels import NPEchannel # socat channel to use npe_io.sh for local io
                #npe=NPEchannel(ip='127.0.0.1', port=44441) # universal (socat based udp) channel for both reading and writing
                #self.timeout=timeout  # receive timeout, data in buffer waits for next time if not ready
                #import time
                from socket import socket, AF_INET, SOCK_DGRAM
                self.UDPSock = socket(AF_INET,SOCK_DGRAM)
                self.UDPSock.settimeout(0.1)
                self.ip='127.0.0.1' # FIXME: SHOULD BE BASED ON PORT NUMBER LIKE WITH XPORT
                self.port=44441
                self.saddr = (self.ip,self.port) 
                self.datadict={} # to give instant response from previous reading
                #self.data=[]
                #print('created npe channel to',self.saddr)
                print('CommModbus() init1u: created CommModbus instance to use npe_io.sh over udp to',self.saddr,'type',self.type)
            ###############
            elif '/dev/tty' in kwargs.get('host'): # direct serial connection defined via host
                from pymodbus.client.sync import ModbusSerialClient as ModbusClient
                self.client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=19200, timeout=0.2, port=kwargs.get('host'))
                # timeout 0.2 oli enne, tekkis vastuste nihe vahel
                print('CommModbus() init2: created CommModbus instance for ModbusRTU over RS485 using port',kwargs)
            else: #tcp, possibly rtu over tcp
                from pymodbus.client.sync import ModbusTcpClient as ModbusClient
                if kwargs.get('port') > 10000 and kwargs.get('port')<10003: # xport, rtu over tcp. use port 10001 or 10002
                    self.port=kwargs.get('port')
                    self.client = ModbusClient(
                        kwargs.get('host', '127.0.0.1'),
                        port=kwargs.get('port'),
                        framer=ModbusRtuFramer)
                    print('CommModbus() init3: created CommModbus instance for ModbusRTU over TCP',kwargs)
                else: # normal modbustcp
                    self.type='' # normal modbus
                    self.port=kwargs.get('port')
                    self.client = ModbusClient(
                            host=kwargs.get('host', '127.0.0.1'),
                            port=kwargs.get('port', 502))
                    print('CommModbus() init4: created CommModbus instance for ModbusTCP over TCP',kwargs)
        else:
            from pymodbus.client.sync import ModbusSerialClient as ModbusClient
            self.client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=19200, timeout=0.2, port=kwargs.get('host'))
            print('CommModbus() init5: created CommModbus instance for ModbusRTU over RS485 using port',kwargs)
        Comm.__init__(self, **kwargs)


    def get_errorcount(self):
        ''' returns number of errors, becomes 0 after each successful modbus transaction '''
        return self.errorcount
    
    
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


    def read(self, mba, reg, count = 1, type = 'h'):
        ''' Read Modbus register(s), either holding (type h), input (type i) or coils (type c).
            Exceptionally can be npe_io too, type n then!
        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'count': Modbus register count
        :param 'type': Modbus register type, h = holding, i = input, c = coil

        '''
        #dummy=0
        if self.type == 'n' or self.type == 'u':  # type switch for npe_io
            type=self.type  # this instance does not use modbus at all! for npe_io!
             
        # actual reading
        if type == 'h':
            #res = self.client.read_holding_registers(address=reg, count=count, unit=mba)
            try: #if (isinstance(res, ReadHoldingRegistersResponse)): # ei funka!
                res = self.client.read_holding_registers(address=reg, count=count, unit=mba)
                if isinstance(res, ReadHoldingRegistersResponse):
                    self.errorcount = 0
                    return res.registers
                else:
                    print('modbus read (h) failed from mba,reg,count',mba,reg,count,' - no registers')
                    self.errorcount += 1
                    return None
            except:
                print('modbus read (h) failed from mba,reg,count',mba,reg,count,' error: '+str(sys.exc_info()[1]))
                self.errorcount += 1
                return None

        elif type == 'i':
            try:
                res = self.client.read_input_registers(address=reg, count=count, unit=mba)
                self.errorcount = 0
                return res.registers
            except:
                print('modbus read (i) failed from',mba,reg,count,' error: '+str(sys.exc_info()[1]))
                #traceback.print_exc() 
                #self.on_error(id, **kwargs)
                self.errorcount += 1
                return None

        elif type == 'c':
            try:
                #FIXME #res = self.client.read_input_registers(address=reg, count=count, unit=mba)
                #self.errorcount = 0
                return res.registers
            except:
                #traceback.print_exc()
                #self.on_error(id, **kwargs)
                self.errorcount += 1
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
                    print('no data from npe_read.sh, error: '+str(sys.exc_info()[1]))
                    return None
            except:
                #traceback.print_exc() # self.on_error(id, **kwargs)
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
            print('unknown type',type)
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
        if self.type == 'n' or self.type == 'u':  # type switch for npe_io
            type=self.type  # this instance does not use modbus at all! for npe_io!
        
        try:
            values = kwargs['values']
            count = len(values)
        except:
            try:
                value = kwargs['value']
                count = 1
            except:
                #traceback.print_exc() # debug
                print('write parameters problem, no value or values given, params',kwargs)
                return 2

        if type == 'h': # holding
            if count == 1:
                try:
                    self.client.write_register(address=reg, value=value, unit=mba)
                    self.errorcount = 0
                    return 0
                except:
                    #traceback.print_exc() # self.on_error(id, **kwargs)
                    #self.on_error(id, **kwargs)
                    self.errorcount += 1
                    return 2
            else:
                try:
                    res = self.client.write_registers(address=reg, count=count, unit=mba, values = values)
                    self.errorcount = 0
                    return 0
                except:
                    #traceback.print_exc() # self.on_error(id, **kwargs)
                    #self.on_error(id, **kwargs)
                    self.errorcount += 1
                    return 1

        elif type == 'c': # coil
            try:
                #FIXME #res = self.client.read_input_registers(address=reg, count=count, unit=mba)
                #self.errorcount = 0
                return 0
            except:
                #traceback.print_exc() # self.on_error(id, **kwargs)
                self.errorcount += 1
                return 1
        elif type == 'n': # npe_io  ##################### NPE subexec WRITE ##################
            try:
                res = self.npe_write(reg, count=count, value= value) # mba ignored
                self.errorcount = 0
                return 0
            except:
                #traceback.print_exc() # self.on_error(id, **kwargs)
                self.errorcount += 1
                return 1
        elif type == 'u': # npe_udpio  ##################### NPE socat WRITE ##################
            try:
                res = self.udpcomm(reg, value, 'w') # mba ignored. single register!
                self.errorcount = 0
                return 0
            except:
                #traceback.print_exc() # self.on_error(id, **kwargs)
                self.errorcount += 1
                return 1

        else:
            print('unknown type',type)
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
        

# #############  npe_read.sh and npe_write.sh not used, subprocess() usage is dangerous, socat is better #####
    #def npe_read(self,register,count = 1): # mba ignored
        #return self.subexec('/mnt/nand-user/d4c/npe_io.sh '+str(register)+' '+str(count)+' rs',1) # returns values read as string


    #def npe_write(self,register, **kwargs): # write register or registers. mba ignored. value or values is needed
        #try:
        #    values = kwargs['values']
        #    count = len(values)
        #except:
        #    try:
        #        value = kwargs['value']
        #        count = 1
        #    except:
        #        print('write parameters problem, no value or values given')
         #       return None

       # try:
       #     if count == 1:
        #        self.subexec('/mnt/nand-user/d4c/npe_io.sh '+str(register)+' '+str(1&value)+' w',1) # returns exit status

        #    else:
        #        value=" ".join(values) # list to string, multiple value # FIXME!
        #        return 2 # self.subexec('/mnt/nand-user/d4c/npe_write.sh '+str(register)+' '+str(value),1) # returning exit status does not function!
       #     return 0
       # except:
        #    print('subexec() failed in npe_write()')
         #   return 1
            

    def udpcomm(self, reg, countvalue, type = 'r'): # type r, ra or w = read or write command. ra returns existing data (async). for npe
        ''' Communicates with (sends and receives data to&from) socat on techbase NPE, where subprocess() usage should be avoided '''
        ureg=None
        i=0
        if (type != 'r' and type != 'rs' and type != 'w' and type != 'p' and type != 'b' and type != 'bs'):
            print('udpcomm(): invalid type '+str(type))
            return None
            
        sendstring=str(reg)+' '+str(countvalue)+' '+type[0] # 3 parameters for both npe_write.sh or npe_read.sh
        self.UDPSock.sendto(sendstring.encode('utf-8'),self.saddr)
        #print('udpcomm sent udp msg '+sendstring+' to '+str(self.saddr)) # debug
        
        if type[0] == 'r' or type[0] == 'b': # some data return is needed
            if type == 'b' and reg == 10 and countvalue != 2:
                print('udpcomm fixing countvalue for reg 10 type b from',countvalue,'to 2')
                countvalue=2                
            
            #if (not reg in self.datadict.keys() or type[-1] == 's' or (reg in self.datadict.keys() and len(self.datadict[reg]) != countvalue)):
            if type[-1] != 's' and (reg in self.datadict.keys() and len(self.datadict[reg].split(' ')) == countvalue): # give immediate response
                # query with changed parameters must wait for correct result!
                retread=self.udpread() # read buffer but do not use for output, just update datadict
                if retread != None:
                    self.update_datadict(retread)
                    
            else: # wait until actual true response is received 
                ureg=''
                ulen=0
                while (i<20 and ((ureg != reg) or (ulen != countvalue))): # no more than 2 s here, as socat has 2 s timeout
                    #print('wait before read') # debug - read in loop until data for right reg arrives
                    time.sleep(0.05) # wait until fresh data arrives for answer. without delay the previous read data is returned
                    retread=self.udpread() # [data], reg. after delay the fresh one should arrive for the 
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
                        print('udpcomm: repeating the query',sendstring)
                        self.UDPSock.sendto(sendstring.encode('utf-8'),self.saddr) # repeat the query
                    i+=1

                    
            if reg in self.datadict and len(self.datadict[reg].split(' ')) == countvalue: # return data from here
                #print('udpcomm: correct value for '+str(reg)+' exists: '+str(self.datadict[reg])) # debug
                #data=str(rdata.decode("utf-8")).strip('\n').split(' ') # python3 related need due to mac in hex
                if type[0] == 'b':
                    data=self.datadict[reg].split(' ')
                    #print('returning mac_ip',data) # debug
                else: # num values
                    #data=[int(eval(i)) for i in str(rdata.decode("utf-8")).strip('\n').split(' ')] # avoid dots in response too
                    data=[int(eval(i)) for i in self.datadict[reg].split(' ')] # values list
                return data
            else:
                print('not what we need in datadict for reg',reg,self.datadict)
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
                print('update_datadict error')
                traceback.print_exc()
                
    def udpread(self): # not to be called from outside of this method, used only by udpsend() above
        ''' Read npe_io over socat or other udp channel. Register will be returned as the first value, may NOT be the one asked last! '''
        data=['','']
        #print('udpread: trying to get udp data from '+str(self.saddr)) # debug
        try: # if anything is comes into udp buffer before timeout
            buf=256
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
                msg='illegal_sender'+str(raddr[0])+' for message: '+str(data)  # ignore the data received!
                print(msg)
                #syslog(msg)
                return None
        
