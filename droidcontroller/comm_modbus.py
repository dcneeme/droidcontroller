# additional modules by neeme in the end!

from droidcontroller.comm import Comm
from pymodbus import * # from pymodbus.register_read_message import *
import traceback
import subprocess # could not use p.subexec()
import sys # to return sys.exc_info()[1])

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
        self.type = type # empty if not npe_io or /dev/tty
        if ('host' in kwargs):
            self.host=kwargs.get('host','127.0.0.1')
            if kwargs.get('host') == 'npe_io': # npe_io via subexec(), no pymodbus in use
                self.type='n' # npe_io
                print('CommModbus() init1: created CommModbus instance for using npe_read.sh and npe_write.sh instead of pymodbus, type',self.type)
            elif '/dev/tty' in kwargs.get('host'): # direct serial connection defined via host
                from pymodbus.client.sync import ModbusSerialClient as ModbusClient
                self.client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=19200, timeout=0.2, port=kwargs.get('host'))
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
        if self.type == 'n':  # type switch for npe_io
            type=self.type  # this instance does not use modbus at all! for npe_io!
            #print('read type',type) # debug
            
        # actual reading
        if type == 'h':
            #res = self.client.read_holding_registers(address=reg, count=count, unit=mba)
            try: #if (isinstance(res, ReadHoldingRegistersResponse)): # ei funka!
                res = self.client.read_holding_registers(address=reg, count=count, unit=mba)
                #dummy=res.registers[0]
                self.errorcount = 0
                return res.registers
            except:
                print('modbus read (h) failed from mba,reg,count',mba,reg,count,' error: '+str(sys.exc_info()[1]))
                #traceback.print_exc()
                #self.on_error(id, **kwargs) # ei funka
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

        elif type == 'n': # npe_io  ##################### NPE ##################
            #print('npe_io read: reg,count',reg,count) # debug
            try:
                res = self.npe_read(reg, count=count) # mba ignored
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

        else:
            print('unknown type',type)
            self.errorcount += 1
            return None



    def write(self, mba, reg, type = 'h', **kwargs):
        ''' Write Modbus register(s), either holding or coils. Returns exit status.

        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'type': Modbus register type, h = holding, c = coil
        :param kwargs['count']: Modbus registers count for multiple register write
        :param kwargs['value']: Modbus register value to write
        :param kwargs['values']: Modbus registers values array to write
        '''
        if self.type == 'n':  # npe_io
            type=self.type  # this instance does not use modbus at all! for npe_io!

        try:
            values = kwargs['values']
            count = len(values)
        except:
            try:
                value = kwargs['value']
                count = 1
            except:
                print('write parameters problem, no value or values given')
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
        elif type == 'n': # npe_io  ##################### NPE ##################
            try:
                res = self.npe_write(reg, count=count, value= value) # mba ignored
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
            returncode=subprocess.call(exec_cmd) # ootab kuni lopetab
            return returncode  # return just the subprocess exit code
        elif submode == 1: # return everything from sdout
            proc=subprocess.Popen([exec_cmd], shell=True, stdout=subprocess.PIPE)
            result = proc.communicate()[0]
            return result
        elif submode == 2: # forks to background, does not wait for output
            returncode=subprocess.Popen(exec_cmd, shell=True) # 
            return 0 # no idea how it really ends
        


    def npe_read(self,register,count = 1): # mba ignored
        return self.subexec('/mnt/nand-user/d4c/npe_read.sh '+str(register)+' '+str(count),1) # returns values read as string


    def npe_write(self,register, **kwargs): # write register or registers. mba ignored. value or values is needed
        try:
            values = kwargs['values']
            count = len(values)
        except:
            try:
                value = kwargs['value']
                count = 1
            except:
                print('write parameters problem, no value or values given')
                return None

        try:
            if count == 1:
                self.subexec('/mnt/nand-user/d4c/npe_write.sh '+str(register)+' '+str(1&value),1) # returns exit status

            else:
                value=" ".join(values) # list to string, multiple value # FIXME!
                self.subexec('/mnt/nand-user/d4c/npe_write.sh '+str(register)+' '+str(value),1) # returning exit status does not function!
            return 0
        except:
            print('subexec() failed in npe_write()')
            return 1