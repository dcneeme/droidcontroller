from droidcontroller.indata import InData
from droidcontroller.pollscheduler import PollScheduler

class Comm():
    ''' Implementation of communication interface
    '''

    def __init__(self, **kwargs):
        ''' Initialize communication module

        :param indata: optional InData object
        :param scheduler: optional PollScheduler object

        '''

        self.indata = kwargs.get('indata', InData())
        self.scheduler = kwargs.get('scheduler', PollScheduler())
        self.scheduler.daemon = True
        self.scheduler.start()


    def add_poll(self, interval, **kwargs):
        ''' Schedule data reader

        :param interval: poll interval in seconds
        :param kwargs['statuscb']: optional callback function for status info
        :param kwargs['convertcb']: optional callback function for data conversion
        :param **kwargs: other arguments to the poller

        '''
        id = self.scheduler.schedule(
                interval,
                self._poller,
                **kwargs)

    def on_data(self, id, data, **kwargs):
        if ('convertcb' in kwargs and kwargs['convertcb'] != None):
            newdata = kwargs['convertcb'](kwargs['name'], data)
            data = newdata

        olddata = {}
        try:
            olddata = self.indata.read(kwargs['name'])['value']
        except Exception:
            pass

        self.indata.write(kwargs['name'], data)

        if (olddata != data):
            self._cb_status('onChange', **kwargs)
        else:
            self._cb_status('onRead', **kwargs)

    def on_error(self, id, **kwargs):
        self._cb_status('onError', **kwargs)

    def _cb_status(self, status, **kwargs):
        if ('statuscb' in kwargs and kwargs['statuscb'] != None):
            kwargs['statuscb'](kwargs['name'], status)

    def __del__(self):
        try:
            self.scheduler.stop()
            self.scheduler.join()
        except AttributeError:
            pass
