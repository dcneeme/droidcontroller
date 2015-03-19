import time
import threading

class PollScheduler(threading.Thread):
    ''' Implementation of serialized scheduler thread
    '''

    def __init__(self, **kwargs):
        ''' Initialize timers and start scheduler
        '''
        if 'timers' in kwargs:
            self.timers = kwargs['timers']
            self.id = 0
            for timer in self.timers:
                if (timer > self.id):
                    self.id = timer
        else:
            self.timers = {}
            self.id = 0
        self.lock = threading.Lock()
        self.ev = threading.Event()
        self.running = False
        self.starttime = None
        self.thread = threading.Thread.__init__(self)

    def schedule(self, interval, func, **kwargs):
        ''' Schedule func(**kwargs) to run in every interval sec

        :param interval: function run interval in sec
        :param func: function
        :param **kwargs: arguments for function
        :return: timer id

        '''
        self.lock.acquire()
        self.id += 1
        self.timers[self.id] = {}
        self.timers[self.id]['id'] = self.id
        self.timers[self.id]['interval'] = interval
        self.timers[self.id]['schedule_time'] = time.time()
        self.timers[self.id]['last_run'] = 0
        self.timers[self.id]['next_run'] = 0
        self.timers[self.id]['run_count'] = 0
        self.timers[self.id]['func'] = func
        self.timers[self.id]['args'] = kwargs
        self.lock.release()
        self.ev.set()
        return self.id

    def cancel_timer(self, id):
        ''' Cancel one timer

        :param id: timer id

        '''
        self.lock.acquire()
        if id in self.timers:
            del self.timers[id]
            self.lock.release()
        else:
            self.lock.release()
            raise Exception('No scheduled timer with id=' + str(id))

    def cancel_all_timers(self):
        ''' Cancel all timers
        '''
        self.lock.acquire()
        self.timers = {}
        self.lock.release()

    def run(self):
        ''' Scheduler thread run() method
        '''
        self.running = True
        self.starttime = time.time()
        while self.running:
            waitingtasks = 0
            runtask = None
            maxwaitedtime = 0
            # FIXME time.time() is not monothonic
            currentclock = time.time()

            # find the longest waiting task and run it
            self.lock.acquire()
            for id in self.timers:
                value = self.timers[id]
                nextrun = self.timers[id]['next_run']
                if nextrun > currentclock:
                    continue
                waitingtasks += 1
                waitedtime = currentclock - nextrun
                if waitedtime > maxwaitedtime:
                    maxwaitedtime = waitedtime
                    runtask = self.timers[id]
            if (runtask != None):
                runtask['last_run'] = currentclock
                runtask['next_run'] = currentclock + runtask['interval']
                runtask['func'](runtask['id'], **runtask['args'])
                runtask['run_count'] += 1
            # TODO do not hold lock during long function run
            self.lock.release()

            # run other waiting tasks immediately
            if (waitingtasks > 1):
                continue

            # find minumum sleep time
            currentclock = time.time()
            minwaittime = 10	# just in case do not sleep more than 10 sec
            self.lock.acquire()
            for id in self.timers:
                value = self.timers[id]
                sleeptime = self.timers[id]['next_run'] - currentclock
                if (sleeptime < minwaittime):
                    minwaittime = sleeptime
            self.lock.release()

            if (minwaittime > 0):
                self.ev.wait(minwaittime)
                self.ev.clear()

    def stop(self):
        ''' Stop scheduler thread
        '''
        self.cancel_all_timers()
        self.running = False
        self.ev.set()

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        self.lock.acquire()
        newtimers = self.timers.copy()
        self.lock.release()
        return PollScheduler(timers=newtimers)

    def __str__(self):
        timers = self.__copy__().timers
        curtime = time.time()
        s = ''
        if self.running:
            s += 'timer is running\n'
        if self.starttime is not None:
            s += 'timer runtime=' + str(curtime - self.starttime) + '\n'
        for id in timers:
            value = timers[id]
            s += ' id=' + str(id)
            s += ' int=' + str(timers[id]['interval'])
            s += ' runcount=' + str(timers[id]['run_count'])
            runtime = curtime - timers[id]['schedule_time']
            s += ' runtime=' + str(runtime)
            if (timers[id]['run_count'] > 1):
                s += ' actualint=' + str(runtime
                        / (timers[id]['run_count'] - 1))
            s += '\n'
        return s

    def __del__(self):
        self.stop()
