''' average stream of values without sliding window '''

import logging
log = logging.getLogger(__name__)  
#log.addHandler(logging.NullHandler())

class AVG(object):
    def __init__(self, avg_coeff=100, avg_value=0.5):
        self.avg_value = avg_value
        self.avg_coeff = avg_coeff
        
    def output(self, invalue):
        ''' calculate new avg_value '''
        self.avg_value = ((self.avg_coeff - 1) * self.avg_value + invalue) / self.avg_coeff
        return self.avg_value