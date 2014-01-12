from droidcontroller.comm import Comm

from pymodbus.register_read_message import *

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
