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

            
    @staticmethod
    def hex_reverse(hstring):
        ''' Return bytes in opposite order '''
        if not 'str' in str(type(hstring)):
            log.warning('string expected as argument')
            return None
        
        if len(hstring)%2 != 0: # odd number of halfbytes
            hstring = '0'+hstring
            
        res = ''
        for i in range(len(hstring), 0, -2):
            res += hstring[i-2:i]
        return res
        
        
    @staticmethod
    def onewire_hexid(reglist, groupsize=4): # read result from id registers, grouped for each id
        ''' Return onewire hex id list '''
        if len(reglist) % groupsize != 0:
            log.warning('invalid number of registers, not multiple of groupsize '+str(groupsize)+'!')
            
        res = []
        for j in range(int(len(reglist) / groupsize)):
            idstring = ''
            for reg in range(groupsize):
                idstring += hex(reglist[ (j * groupsize) + reg]).split('x')[1].zfill(4) # UN.hex_reverse()
            if idstring != '0000000000000000':
                res.append(UN.hex_reverse(idstring).upper()) # change order and make upper case
        return res
        
    @staticmethod
    def bit_replace(word, bit, value): # changing word with single bit value
        ''' Replaces bit in 2byte word. Examples:
            #bit_replace(255,7,0) # 127
            #bit_replace(0,15,1) # 32k
            #bit_replace(0,7,1) # 128
        '''
        #print('bit_replace var: ',format("%04x" % word),bit,value,format("%04x" % ((word & (65535 - 2**bit)) + (value<<bit)))) # debug
        return ((word & (65535 - 2**bit)) + (value<<bit))

    @staticmethod
    def comparator(invalue1, invalue2): # changing word with single bit value
        ''' Returns 1 if invalue1 > invalue2, 0 if vice versa  '''
        if invalue1 > invalue2:
            out = 1
        else:
            out = 0
        return out