import time

class InData():
    ''' Implementation of data buffer to store last controller readings
    '''

    def __init__(self):
        ''' Initialize buffer
        '''

        self.data = {}

    def write(self, key, value):
        ''' Write value to the buffer

        :param key: The register id
        :param value: The value

        '''
        self.data[key] = {}
        self.data[key]['timestamp'] = time.time()
        self.data[key]['value'] = value

    def read(self, key):
        ''' Read timestamp,value pair from the buffer

        :param key: The register id
        :return: [ timestamp, value ] list

        '''
        if key in self.data:
            return {
                    'timestamp': self.data[key]['timestamp'],
                    'value': self.data[key]['value']}
        else:
            raise Exception('key not exists')
