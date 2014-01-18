import time
import threading

class InData():
    ''' Implementation of data buffer to store last controller readings
    '''

    def __init__(self, **kwargs):
        ''' Initialize buffer
        '''

        if 'data' in kwargs:
            self.data = kwargs['data']
        else:
            self.data = {}
        self.lock = threading.Lock()

    def write(self, key, value):
        ''' Write value to the buffer

        :param key: The register id
        :param value: The value

        '''
        self.lock.acquire()
        if key in self.data:
            self.data[key]['old_timestamp'] = self.data[key]['timestamp']
            self.data[key]['old_value'] = self.data[key]['value']
        else:
            self.data[key] = {}
        self.data[key]['timestamp'] = time.time()
        self.data[key]['value'] = value
        self.lock.release()

    def read(self, key):
        ''' Read timestamp,value pair from the buffer

        :param key: The register id
        :return: [ timestamp, value ] list

        '''
        return self.__read(key, '')

    def read_old(self, key):
        ''' Read previous timestamp,value pair from the buffer if exists

        :param key: The register id
        :return: [ timestamp, value ] list

        '''
        return self.__read(key, 'old_')

    def __read(self, key, prefix):
        self.lock.acquire()
        if key in self.data:
            if (prefix + 'timestamp') in self.data[key]:
                res = {
                        'timestamp': self.data[key][prefix + 'timestamp'],
                        'value': self.data[key][prefix + 'value']}
                self.lock.release()
                return res
            else:
                self.lock.release()
                raise Exception('previous data for key not exists')
        else:
            self.lock.release()
            raise Exception('key not exists')
        self.lock.release()

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        self.lock.acquire()
        newdata = self.data.copy()
        self.lock.release()
        return InData(data=newdata)

    def __str__(self):
        data = self.__copy__().data
        s = ''
        for key in data.keys():
            s += 'key=\"' + str(key) + '\"'
            for var in (['value', 'timestamp', 'old_value', 'old_timestamp']):
                if var in data[key]:
                    s += ' ' + var + '=' + str(data[key][var])
            s += '\n'
        return s
