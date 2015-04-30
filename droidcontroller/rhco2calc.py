#temp and humidity compensation for humidity and co2 sensor
import traceback
import logging
log = logging.getLogger(__name__)
            
class RhCoCalc:
    ''' Humidity reading depends on temperature.
        CO2 reading depends both on temperature and humidity.
        Return humidity and ppm based on T and raw hum, co2 on AI
        using sensors HIH-5130 and HS-135
            niiskus HIH5130 
            Vout=(Vsup)*(0.00636*RH+0,1515)
            RH=((rawRH*4/4095)/Vsup-0.1515)/0,00636   if 4V ADC ref and 5V supply
            TrueRH= (((rawRH*4/5)-0.1515)/0,00636)/(1.0546-0.00216*T), T in ddegC
            WARNING: the calculation result in Windows is wrong for some reason (negative humidity)!
    '''

    def __init__(self, a=0.41, b=-520, c=0.5, d= 3.35, e= -650, f= -9.3, g= -1.8):
        ''' a = kordaja  niiskuse  y=ax+b
            b = nihe hum
            c = temp moju niiskusele kordaja
            d = kordaja co2 arv 
            f = temp komp kordaja co2
            g = niiskuse komp kordaja co2
        '''
        self.set_params(a, b, c, d, e, f, g)
        self.temp = None
        self.rawhum = None
        self.rawco2 = None
        self.outhum = None
        self.outco2 = None
        
    def set_params(self, a, b, c, d, e, f, g):
        ''' Sets parameters a, b, c for humidity calculation; d, e, f, g for co2  '''
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f
        self.g = g
        
    def get_params(self):
        return self.a, self.b, self.c, self.d, self.e, self.f, self.g 
  
    def output(self, rawtemp, rawhum, rawco2):
        ''' Calculate compensated values for humidity and CO2. 
            It is possible to calculate humidity without raw co2, but 
            it is not possible to calculate co2 without humidity.
            Temperature is always needed, in decidegrees of C.
        '''
        self.temp = rawtemp
        self.rawhum = rawhum
        self.rawco2 = rawco2
        if self.temp is None:
            return None
            
        self.outhum = int(round(self.rawhum*self.a+self.b+self.c*self.temp, 0))
        #try:
        #    self.outhum= int(round(10 * ((((self.rawhum * 4 / 4095) / 5) - 0.1515) / 0.00636) / (1.0546 - 0.000216 * self.temp),0))  # d%
            # formula composed according to the honeywell data sheet. works on linux only??
        #except:
        #    self.outhum = None
        #    traceback.print_exc()
            
        log.info('rawtemp '+str(self.temp)+', rawhum '+str(self.rawhum)+', rawco2 '+str(self.rawco2))
        print('hum calc', round(self.rawhum*self.a), round(self.b), round(self.c*self.temp)) # kordaja, nihe, temp moju
        if self.outhum != None:
            self.outco2 = int(round(self.rawco2*self.d+self.e+self.f*self.temp+self.g*self.outhum, 0))
            print('co2 calc', round(self.rawco2*self.d), round(self.e), round(self.f*self.temp), round(self.g*self.outhum))
        return self.outhum, self.outco2
        