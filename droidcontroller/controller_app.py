''' This is a class to handle event-based flow of application. Droid4control 2015  '''

import sys, os, traceback
import tornado
import tornado.ioloop
import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger(__name__)

from droidcontroller.acchannels import *
ac = ACchannels(in_sql = 'aicochannels.sql', readperiod = 0, sendperiod = 25) # ai and counters
from droidcontroller.dchannels import *
d = Dchannels(readperiod = 0, sendperiod = 180) # di and do. immediate notification on change, read as often as possible
# the previous block also generated sqlgeneral and uniscada instances, like s, udp, tcp

OSTYPE='archlinux'
print('OSTYPE',OSTYPE)

from droidcontroller.udp_commands import * # sellega alusta, kaivitab ka SQlgeneral
p = Commands(OSTYPE) # setup and commands from server
r = RegularComm(interval=12) # interval needs to be below timer value!

mac = ''
filee = ''
try:
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


class ControllerApp(object):
    ''' '''
    def __init__(self, app):
        self.app = app # client-specific main script
        interval_ms = 1000 # milliseconds
        self.loop = tornado.ioloop.IOLoop.instance()
        udp.add_reader_callback(self.udp_reader)
        
        self.udpcomm_scheduler = tornado.ioloop.PeriodicCallback(self.udp_comm, 1500, io_loop = self.loop) # send udp every 1.5s
        self.regular_scheduler = tornado.ioloop.PeriodicCallback(self.regular_svc, 120000, io_loop = self.loop) # send regular svc
        self.di_scheduler = tornado.ioloop.PeriodicCallback(self.di_reader, 50, io_loop = self.loop) # read DI asap
        self.ai_scheduler = tornado.ioloop.PeriodicCallback(self.ai_reader, 10000, io_loop = self.loop) # ai 10 s
        self.cal_scheduler = tornado.ioloop.PeriodicCallback(self.cal_reader, 3600000, io_loop = self.loop) # gcal 1 h
        
        self.udpcomm_scheduler.start()
        self.regular_scheduler.start()
        self.di_scheduler.start()
        self.ai_scheduler.start()
        self.cal_scheduler.start()
        
        #self.reset_sender_timeout() # to start
        

    def udp_comm(self): # only send
        sys.stdout.write('U') # dot without newline
        sys.stdout.flush()
        udp.iocomm() # chk buff and send to monitoring
        
    def udp_reader(self, udp, fd, events): # no timer!
        ##print('reading udp')
        if events & self.loop.READ:
            got = udp.udpread() # loeb ainult!
            if got != {} and got != None:
                log.info('udp_reader got from server '+str(got))
                self.got_parse(got) # see next def
        if events & self.loop.ERROR:
            log.error('UDP socket error!')
            
    def got_parse(self, got):
        ''' check the ack or cmd from server '''
        if got != {} and got != None: # got something from monitoring server
            ac.parse_udp(got) # chk if setup or counters need to be changed
            d.parse_udp(got) # chk if setup ot toggle for di
            todo = p.parse_udp(got) # any commands or setup variables from server?
            log.info('todo '+todo)
            p.todo_proc(todo) # execute possible commands

    def di_reader(self): # DI reader
        #print('reading di channels')
        sys.stdout.write('D') # dot without newline
        sys.stdout.flush()
        d.doall()
        di_dict = d.get_chg_dict()
        if len(di_dict) > 0: #di_dict != {}: # change in di services
            #print('di change detected: '+str(di_dict))
            log.info('di change detected: '+str(di_dict))
            self.app_main()
                    
    def ai_reader(self): # AICO reader
        #print('reading ai, co')
        sys.stdout.write('A') # dot without newline
        sys.stdout.flush()
        ac.doall()
        self.app_main()

    def udp_sender(self): # UDP sender / not in use, see udp_comm using udp.iocomm
        #print('sending udp')
        udp.buff2server() # ainult saadab!!! ei dumbi jne, kasuta parem udp.comm
        self.reset_sender_timeout()

    def regular_svc(self):
        sys.stdout.write('R') # 
        sys.stdout.flush()
        r.regular_svc() # UPW,UTW, ipV, baV, cpV. mfV are default services.
    
    def cal_reader(self): # gcal  refresh, call ed by customer_app
        print('FIXME cal sync')

    def reset_sender_timeout(self):
        ''' Resetting ioloop timer '''
        ##print('FIXME timer reset')
        ##IOLoop.add_timeout(5000, self.udp_sender) # last line! recalls itself after timeout 5 s


    def app_main(self): # application-specific app() in iomain_xxx.py
        ''' ehk on vaja param anda mis muutus, may call udp_sender '''
        ##print('app_main')
        res = self.app(self) # self selleks, et vahet teha erinevatel kaivitustel, valjakutsutavale lisa param
        # if res... # saab otsustada kas saata vms.
        self.udp_comm() # self.udp_sender()


