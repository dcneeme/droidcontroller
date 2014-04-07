''' aichannels.py
    communication with analogue I/O registers via ModbusRTU
'''
# last change 09.01.2014

from pymodbus.client.sync import ModbusTcpClient as ModbusClient # modbusTCP
client = ModbusClient(method='rtu', stopbits=1, bytesize=8, parity='E', baudrate=19200, timeout=0.2, port='/dev/ttyAPP0') # change if needed


class AI:
    """ Communication with analogue data registers via ModbusRTU link.
    """

    def __init__(self, unit, register, table = 'aichannels'):
        self.unit = unit
        self.register = register
        self.table = table # sql table to read analogue channels setup from
        self.ref_register = 270
        self.ref_value = 0x0030
        self.mode_register = 275
        self.mode_value = get_value(self.mode_register) & ((2**self.register - 2) + 2**self.register + 6) # one bit masking LSB, one MSB
        
    def configure(self): 
        """  Configures ai channels bitwise for one unit and one address based on current setup and entries in aichannels table.
        The analogue channels setup should not conflict with dichannels. That approach should make the setup table obsolete!
        """
        # read / calculate conf bits for reg 270, 271, 275
        # write modified config words into 270, 271, 275
        
        result = client.write_register(address = self.register, value = setPoint, unit = self.unit)
        return result
        
    def get_value(register = self.register): # content of the ai register, save to aichannels table
        ''' check error register '''
        value = client.read_holding_registers(address = self.register, count = 1, unit = self.unit) #
        return value
        
    
    