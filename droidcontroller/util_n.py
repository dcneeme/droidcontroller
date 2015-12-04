import logging
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

class UN(object): # Utilities Neeme, use like UN.val2int(14.4)
    ''' Use the methods here as classname.methodname() without cretaing a class instance '''

    @staticmethod
    def interpolate(x, x1=0, y1=0, x2=0, y2=0):
        ''' Returns linearly interpolated value y based on x and
            two known points defined by x1,y1 and x2,y2
        '''
        if x1 == y2:
            log.warning('invalid interpolation attempt')
            # return average in case ponts have the same x coordinate
            return (y1+y2)/2.0
        else:
            return y1+(y2-y1)*(x-x1)/(x2-x1)


    @staticmethod
    def val2int(value, coeff=1):
        ''' Multiply with coeff, returns rounded integer '''
        if value != None and coeff != None:
            return int(round(coeff * value, 0))
        else:
            log.warning('INVALID parameters! value '+str(value)+' and coeff '+str(coeff)+' must NOT be None?')
            return None

            
