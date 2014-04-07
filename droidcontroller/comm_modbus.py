# additional modules by neeme in the end!

from droidcontroller.comm import Comm
from pymodbus import * # from pymodbus.register_read_message import *
import traceback

class CommModbus(Comm):
    ''' Implementation of Modbus communications
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

        Optional parameters:
        :param indata: optional InData object
        :param scheduler: optional PollScheduler object

        '''

        if ('host' in kwargs):
            from pymodbus.client.sync import ModbusTcpClient as ModbusClient
            self.client = ModbusClient(
                    host=kwargs.get('host', '127.0.0.1'),
                    port=kwargs.get('port', 502))
        else:
            from pymodbus.client.sync import ModbusSerialClient as ModbusClient
            self.client = ModbusClient(**kwargs)
        Comm.__init__(self, **kwargs)

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
        ''' Read Modbus register(s), either holding, iinput or coils

        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'count': Modbus register count
        :param 'type': Modbus register type, h = holding, i = input, c = coil
        
        '''
        dummy=0
        if type == 'h':
            res = self.client.read_holding_registers(address=reg, count=count, unit=mba) 
            try: #if (isinstance(res, ReadHoldingRegistersResponse)): # ei funka!
                dummy=res.registers[0]
                return res.registers
            except:
                print('modbus read failed from',mba,reg,count)
                return None
        elif type == 'i':
            try:
                res = self.client.read_input_registers(address=reg, count=count, unit=mba) 
                return res.registers
            except:
                traceback.print_exc() # self.on_error(id, **kwargs)
                return None
        elif type == 'c':
            try:
                #FIXME #res = self.client.read_input_registers(address=reg, count=count, unit=mba) 
                return res.registers
            except:
                traceback.print_exc() # self.on_error(id, **kwargs)
                return None
        else:
            print('unknown type',type)
            return None
            

            
    def write(self, mba, reg, type = 'h', **kwargs):
        ''' Write Modbus register(s), either holding or coils

        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'type': Modbus register type, h = holding, c = coil
        :param kwargs['count']: Modbus registers count for multiple register write
        :param kwargs['value']: Modbus register value to write
        :param kwargs['values']: Modbus registers values array to write
        ''' 
        try:
            values = kwargs['values']
            count = len(values)
        except:
            try:
                value = kwargs['value']
                count = 1
            except:
                print('write parameters problem')
                return None
            
        if type == 'h': # holding
            if count == 1:
                try:
                    self.client.write_register(address=reg, value=value, unit=mba) 
                    return 0
                except:
                    traceback.print_exc() # self.on_error(id, **kwargs)
                    return None
            else:
                try:
                    res = self.client.write_registers(address=reg, count=count, unit=mba, values = values) 
                    return 0
                except:
                    traceback.print_exc() # self.on_error(id, **kwargs)
                    return 1
            
        elif type == 'c': # coil
            try:
                #FIXME #res = self.client.read_input_registers(address=reg, count=count, unit=mba) 
                return 0
            except:
                traceback.print_exc() # self.on_error(id, **kwargs)
                return 1
        else:
            print('unknown type',type)
            return 2
            