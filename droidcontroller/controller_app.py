''' This is a class to handle event-based flow of application. Droid4control 2015  '''

import sys, os, traceback, inspect, datetime
import tornado
import tornado.ioloop
import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

from droidcontroller.udp_commands import * # sellega alusta, kaivitab ka SQlgeneral
from droidcontroller.uniscada import * # UDPchannel, TCPchannel
from droidcontroller.statekeeper import *
from droidcontroller.acchannels import *
from droidcontroller.dchannels import *
# the previous block also generated sqlgeneral and uniscada instances, like s, udp, tcp
from droidcontroller.speedometer import * # cycle speed for statistics


mac = ''
filee = ''
try:
    mac = os.environ['ID'] # env variable ID
    mac = os.environ['ID'] # env variable ID
    filee = 'env var ID'
except:
    if os.path.isfile('host_id.conf'):
        filee = 'host_id.conf' #
    elif os.path.isfile('network.conf'):
        filee = 'network.conf'
    else:
        log.warning('IMPOSSIBLE to find mac as the host_id! using 000000000000...')
        mac = '000000000000'
        time.sleep(10)
    if mac != '000000000000':
        mac = udp.get_conf('mac', filee)
    else:
        filee = 'hardwired last resort ID'

log.info('got mac '+mac+' from '+filee)
udp.setID(mac) # kontrolleri id
tcp.setID(mac) # kas tcp seda kasutabki?

try:
    monip = os.environ['MONIP'] # env variable ID
except:
    monip = '195.222.15.51'
log.info('got monip '+monip)
udp.setIP(monip) # '195.222.15.51') # mon server ip

try:
    monport = os.environ['MONPORT'] # env variable ID
except:
    monport = 44445
log.info('got monport '+str(monport))
udp.setPort(monport)

import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)


class ControllerApp(object): # default modbus address of io in controller = 1
    ''' '''
    def __init__(self, app, ostype='archlinux', mba=1, mbi=0):
        self.app = app # client-specific main script
        self.mba = mba # controller io modbus address if dc6888
        self.mbi = mbi # io channel for controller
        self.ac = ACchannels(in_sql = 'aicochannels.sql', readperiod = 0, sendperiod = 25) # ai and counters
        self.d = Dchannels(readperiod = 0, sendperiod = 180) # di and do. immediate notification on change, read as often as possible
        self.p = Commands(ostype) # setup and commands from server
        self.r = RegularComm(interval=12) # interval needs to be below timer value!

        self.running = 0 # 999 feed enabled if running only
        self.spm = SpeedoMeter(windowsize = 100) # to see di speed
        self.get_AVV(inspect.stack()[1]) # caller name and hw version

        self.loop = tornado.ioloop.IOLoop.instance()
        udp.add_reader_callback(self.udp_reader)

        self.udpcomm_scheduler = tornado.ioloop.PeriodicCallback(self.udp_comm, 2000, io_loop = self.loop) # do not send udp more often than once in 2 sec
        self.regular_scheduler = tornado.ioloop.PeriodicCallback(self.regular_svc, 60000, io_loop = self.loop) # send regular svc
        self.di_scheduler = tornado.ioloop.PeriodicCallback(self.di_reader, 10, io_loop = self.loop) # read DI asap. was 50 ms
        self.ai_scheduler = tornado.ioloop.PeriodicCallback(self.ai_reader, 10000, io_loop = self.loop) # ai 10 s
        self.cal_scheduler = tornado.ioloop.PeriodicCallback(self.cal_reader, 3600000, io_loop = self.loop) # gcal 1 h

        self.udpcomm_scheduler.start()
        self.regular_scheduler.start()
        self.di_scheduler.start()
        self.ai_scheduler.start()
        self.cal_scheduler.start()
        log.info('ControllerApp instance created. '+self.AVV)


    def get_AVV(self, frm):
        ''' Get the name of calling customer-specific script and controller hw version as self.AVV '''
        #frm = inspect.stack()[1]
        mod = inspect.getmodule(frm[0])
        modname = str(mod).split("'")[3]
        filename = os.path.basename(modname)
        self.rescue = 0
        if 'rescue' in str(mod):
            self.rescue = 1
            log.warning('rescue application starting!')
        t = os.path.getmtime(filename)
        mod_mtime = datetime.datetime.fromtimestamp(t).strftime(' %Y-%m-%d')
        try:
            hw = hex(mb[self.mbi].read(self.mba,257,1)[0]) # assuming it5888, mba 1!
        except:
            hw = 'n/a'
        self.AVV = 'AVV:HW '+hw+', APP '+filename+mod_mtime+'\nAVS:'
        if self.rescue != 0:
            self.AVV += '2\n' # critical status
        else:
            self.AVV += '0\n'


    def udp_comm(self): # only send
        sys.stdout.write('U') # dot without newline
        sys.stdout.flush()
        udp.iocomm() # chk buff and send to monitoring
        # chk for udb receive ability
        send_state = udp.sk_send.get_state()
        receive_state = udp.sk.get_state()
        #self.reset_sender_timeout() # FIXME
        if send_state[0] == 1 and send_state[1] > 30 and receive_state[0] == 0 and receive_state[1] > 30: ## receive problem
            log.warning('** udp send ok but no answer. reading buffer until empty! **') # if read buff not empty then no event from new data!
            udp.sk.up()
            udp.sk.dn() # to restart timer
            got = udp.udpread()
            while got != None and got != {}:
                self.got_parse(got)
                got = udp.udpread()
            log.debug('*** read buffer until empty done wo IOLoop!!!')
            #time.sleep(1)
            

    def udp_reader(self, udp, fd, events): # no timer! on event!
        ##return None ## test reaction on udp input wo ioloop event
        self.running = 1 # ioloop must be running if udp_reader was called
        if events & self.loop.ERROR:
            log.error('UDP socket error!')
        elif events & self.loop.READ:
            got = udp.udpread() # loeb ainult!
            while got != None and got != {}:
                self.got_parse(got)
                got = udp.udpread()

            if udp.sk.get_state()[3] == 1: # firstup
                self.firstup()

    def firstup(self):
        ''' Things to do on the first connectivity establisment after startup '''
        udp.udpsend(self.AVV) # AVV only, the rest go via buffer
        udp.send(['TCS',1,'TCW','?']) # restore via buffer
        self.ac.ask_counters() # restore values from server
        log.info('******* uniscada connectivity up, sent AVV and tried to restore counters ********')
        self.app(sys._getframe().f_code.co_name, attentioncode = 1) # app() should ask some more variables?

    def powerbreak(self):
        # age and neverup taken into account from udp.sk statekeeper instance
        ''' 5V power break for cold reboot '''
        msg = '**** going to cut power NOW (at '+str(int(time.time()))+') via 0xFEED in attempt to restore connectivity ***'
        log.warning(msg)
        udp.dump_buffer() # save unsent messages as file

        with open("/root/d4c/appd.log", "a") as logfile:
            logfile.write(msg)
        try:
            self.p.subexec('/usr/bin/sync', 0) # to make sure power will be cut in the end
            time.sleep(1)
            mb[self.mbi].write(self.mba, 277, value = 9) # length of break in s
            time.sleep(1)
            mb[self.mbi].write(self.mba, 999, value = 0xFEED) # ioboard ver > 2.35 cuts power to start cold reboot (see reg 277)
            #if that does not work, appd and python main* must be stopped, to cause 5V reset without 0xFEED functionality
        except:
            traceback.print_exc()

        try:
            self.p.subexec('/root/d4c/killapp',0) # to make sure power will be cut in the end
        except:
            log.warning('executing /root/d4c/killapp failed!')

    def got_parse(self, got):
        ''' check the ack or cmd from server '''
        if got != {} and got != None: # got something from monitoring server
            log.info('parsing got '+str(got)) # voimalik et mitu jarjest?
            self.ac.parse_udp(got) # chk if setup or counters need to be changed
            self.d.parse_udp(got) # chk if setup ot toggle for di
            todo = self.p.parse_udp(got) # any commands or setup variables from server?
            if todo != '':
                log.info('todo '+todo)
                self.p.todo_proc(todo) # execute possible commands

    def di_reader(self): # DI reader
        self.spm.count() # di speed metering via speedometer
        reslist = self.d.doall() # returns di, do, svc signals 0 1 2 = nochg chg err
        di_dict = self.d.get_chg_dict()
        if reslist == [0, 0, 0]:
            sys.stdout.write('d') # no flush
            sys.stdout.flush() # debugging flush on no chg as well
        else:
            sys.stdout.write('D') # some change
            sys.stdout.flush() # flush now, when something was changed
        
        if (reslist[0] & 1):  # change in di services
            di_dict = self.d.get_chg_dict()
            log.info('di change detected: '+str(di_dict)+', reslist '+str(reslist)) # mis siin on , chg voi svc?
            self.app(sys._getframe().f_code.co_name, attentioncode = 1) # d, a attention bits
        if (reslist[1] & 1):  # change in do services
            di_dict = self.d.get_chg_dict()
            log.info('do change detected: '+str(di_dict)+', reslist '+str(reslist)) # mis siin on , chg voi svc?
            self.app(sys._getframe().f_code.co_name, attentioncode = 1) # d, a attention bits
        if (reslist[2] & 1):  # change in di services
            di_dict = self.d.get_chg_dict()
            log.info('svc to send: '+str(di_dict)+', reslist '+str(reslist))
            self.udp_comm() # should reset timer too!
            

    def ai_reader(self): # AICO reader
        #print('reading ai, co')
        sys.stdout.write('A') # dot without newline
        sys.stdout.flush()
        self.ac.doall()
        self.app(sys._getframe().f_code.co_name, attentioncode = 2) # d, a attention bits

    
    def regular_svc(self): # FIXME - send on change too! pakkida?
        sys.stdout.write('R') #
        sys.stdout.flush()
        self.r.regular_svc() # UPW, UTW, ipV, baV, cpV. mfV are default services.
        skstate = udp.sk.get_state() # udp conn statekeeper
        if self.running != 0 and skstate[0] == 0 and skstate[1] > 300 + skstate[2] * 300: # total 10 min down, cold reboot needed
            self.powerbreak() # 999 feed to restart via 5V break

    def cal_reader(self): # gcal  refresh, call ed by customer_app
        print('FIXME cal sync')


    def reset_sender_timeout(self): # FIXME
        ''' Resetting ioloop timer '''
        ##print('FIXME timer reset')
        ##IOLoop.add_timeout(5000, self.udp_sender) # last line! recalls itself after timeout 5 s


    #def app_main(self, attentioncode=0): # application-specific app() in iomain_xxx.py
    #    ''' ehk on vaja param anda mis muutus, may call udp_sender '''
    #   ##print('app_main')
    #    res = self.app(sys._getframe().f_code.co_name, attentioncode) # self selleks, et vahet teha erinevatel kaivitustel, valjakutsutavale lisaparam
    #    #attentioncode on = bitmap d, a muutuste/tootlusvajaduste kohta
    #    # if res... # saab otsustada kas saata vms.
    #    self.udp_comm() ## kas on vaja siin?

    def commtest(self):
        ''' Use for testing from iomain_xxx, cua.ca.commtest() '''
        log.info('testing modbus and udp communication')
        self.di_reader()
        self.ai_reader()
        self.udp_comm()
        time.sleep(1)
        #self.udp_reader(udp, fd, events) # see nii ei toimi kui loop ei kai
        got = udp.udpread() # loeb ainult!
        if got != None: ## at least ack received
            if got != {}:
                log.info('udp_reader got from server '+str(got))
                self.got_parse(got) # see next def
            if udp.sk.get_state()[3] == 1: # firstup
                self.firstup()

       
    #def apptest(self):
    #    ''' testing app part in the iomain script'''
    #    self.app(inspect.currentframe().f_code.co_name, attentioncode = 3)
        
    def apptest(self): # kiireim 
        #testides python -m timeit -s 'import inspect, sys' 'inspect.stack()[0][0].f_code.co_name'
        ''' testing app part in the iomain script'''
        self.app(sys._getframe().f_code.co_name, attentioncode = 2)