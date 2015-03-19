from droidcontroller.convert import Convert

class ConvertDS18B20(Convert):
    ''' Implementation of DS1820 temperature converter
    '''

    def convert(self, name, indata):
        outdata = [1]
        if indata[0] & 0b1000000000000000:
            indata[0] = ((~indata[0] & 0b1111111111111111) + 1) * -1
        outdata[0] = "%0.1f" % (indata[0] / 16.0)
        if (outdata[0] == '256.0'):
            outdata[0] = 'N/A'
        elif (outdata[0] == '85.0'):
            outdata[0] = 'ERR'
        return outdata
