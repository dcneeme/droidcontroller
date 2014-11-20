# keep connectivity or any other state together with up or down timestamps
import logging, time
log = logging.getLogger(__name__)

class StateKeeper: #
    ''' Keep the state and the timestamp of the last state change.
        The state falls down if no up() actions are coming before timeout.
        Toggle input toggle() forces immediate state change.
        Timeout 0 turns state down on next get_state(), tout None means never time out.
        TODO: add upfilter, time to get another up, must be smaller than off_tout
        '''

    def __init__(self, off_tout = 300, in_tout = 30): # falls to down (connstate = 0) after no setting up for off_tout
        ''' First up() while in state 0 does not change state unless in_tout == 0.
            If the second up() arrives before in_tout, state will go up.
        '''
        self.off_tout = off_tout
        self.neverup = 1 #goes down with first up
        self.ts_up = 0
        self.ts_uplast = 0
        self.ts_dn = time.time()
        self.ts_dnlast = time.time()
        self.state = 0 # down initially
        log.info('StateKeeper instance created')

    def up(self):
        ''' Turns state up, next similar signal must arrive before timeout to keep it up '''
        if self.state == 0:
            self.state = 1
            self.ts_up = time.time()
            if self.neverup == 1:
                log.info('conn state changed to up for the first time')
                self.neverup = -1
            else:
                log.info('conn state changed to up')
        else:
            log.debug('conn state was already up, no change')
        self.ts_uplast = time.time()

    def dn(self):
        if self.state == 1:
            self.state = 0
            self.ts_dn = time.time()
            log.info('state changed to down')
        else:
            log.debug('state was already down, no change')
        self.ts_dnlast = time.time()


    def toggle(self):
        ''' State change '''
        if self.state == 1:
            self.state = 0
            self.ts_dn = time.time()
            self.ts_dnlast = time.time()
            log.info('state changed to down by toggle signal')
        elif self.state == 0:
            self.state = 1
            self.ts_up = time.time()
            self.ts_uplast = time.time()

            if self.neverup == 1:
                log.info('state changed to first-time up by the toggle signal')
                self.neverup = -1
            else:
                log.info('state changed to up by toggle signal')

    def get_state(self):
        ''' Returns state and the age of this state since last state change '''
        if self.state == 0:  # conn state down
            age = round(time.time() - self.ts_dn,0) # s
            time2down = 0
        else: # up
            if self.off_tout != None:
                age = round(time.time() - self.ts_up,0) # s
                time2down = round(self.off_tout + self.ts_uplast -time.time(), 0)
                if time.time() - self.ts_uplast > self.off_tout:
                    self.dn()
                    age = 0
                    time2down = 0
                    log.info('state changed to down due to timeout')


        if self.neverup == -1 and self.state == 1: # generate pulse to restore variables from the server
            firstup = 1
            self.neverup = 0
        else:
            firstup = 0
        return self.state, age, self.neverup, firstup, time2down # tuple

