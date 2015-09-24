# This Python file uses the following encoding: utf-8

''' 
to write seneca s401 modbus panel without reading back, to avoid constant reading and delays if panel power off
 '''

import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG) # temporary
log = logging.getLogger(__name__)

class SenecaPanel(object): # parameetriks mb
    ''' Returns new delay to try for register 699, from the allowed range '''
    def __init__(self, mb, mba, mbi = 0, lines=[1000,1001, 1003,1004, 1006,1007,1009]):
        self.mb = mb
        self.mbi = mbi
        self.mba = mba
        self.lines = lines
        log.info(self.__class__.__name__+' instance created with mbi '+str(self.mbi)+',  mba '+str(self.mba))
        
    def send(self,line,data):
        ''' if data is list (max len 2! for seneca), then multiregister write with sequential addresses is used '''
        if line in self.lines:
            if 'list' in str(type(data)):
                if len(data) < 3:
                    res = self.mb[self.mbi].write(self.mba, line, values=data)
                else:
                    log.warning('illegal data length: '+str(data))
                    return 1
            elif 'int' in str(type(data)):
                res = self.mb[self.mbi].write(self.mba, line, value=data)
            else:
                log.warning('illegal data type '+str(type(data))+' for '+str(data))
                return 1
        else:
            log.warning('illegal line register '+str(line))
            return 1
        return res