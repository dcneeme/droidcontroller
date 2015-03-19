from droidcontroller.convert import Convert

class ConvertIP(Convert):
    ''' Implementation of IP address converter
    '''

    def convert(self, name, indata):
        outdata = [1]
        outdata[0] = str((indata[0] & 0xff00) >> 8) + \
                     "." + \
                     str(indata[0] & 0x00ff) + \
                     "." + \
                     str((indata[1] & 0xff00) >> 8) + \
                     "." + \
                     str(indata[1] & 0x00ff)
        return outdata
