# process commands received from uniscada server. to be imported by uniscada.py
#instance udp should be created.
# FIXME + regular svc and cmd ERV send out of historical queue!

import subprocess
import os, sys
import socket, struct, fcntl
import psutil

from droidcontroller.sqlgeneral import * # SQLgeneral  / vaja ka time,mb, conn jne
s=SQLgeneral() 

import logging
log = logging.getLogger(__name__)


class Commands(SQLgeneral): # p
    ''' Checks the incoming datagram members (key,value) for commands and setup variables.
        Outputs TODO for execution and ...
    '''

    def __init__(self, OSTYPE):
        ''' PSTYPE not used since 22.6.2015. vpnon and vpnoff must be present in curr dir! '''
        self.todocode = 0 # todo_proc() retries
        self.vpn_start = '/root/d4c/vpnon' 
        self.vpn_stop = '/root/d4c/vpnoff'
        


    def free(path='./'): #returns free MB and percentage of given fs (can be current fs './' as well) # FIXME!
        #shold return free MB both for RAM and filesystem (with home dir included)
        info = os.statvfs(path)
        return info[3]*info[1]/1048576,100*info[3]/info[2] # returns free [MB,%]

    def subexec(self, exec_cmd, submode = 1): # submode 0 returns exit code only
        ''' shell command execution. if submode 0-, return exit staus.. if 1, exit std output produced. '''
        try:
            if submode == 0: # return exit status, 0 or more
                returncode = subprocess.call(exec_cmd) # ootab kuni lopetab
                return returncode  # return just the subprocess exit code
            elif submode == 1: # return everything from sdout
                proc=subprocess.Popen(exec_cmd, shell=True, stdout=subprocess.PIPE)
                result = proc.communicate()[0]
                return result
            elif submode == 2: # forks to background, does not wait for output
                returncode = subprocess.Popen(exec_cmd, shell=True) #
                return 0 # no idea how it really ends
        except:
            print('subexec failure')


    def parse_udp(self, data_dict): # #search for special commands
        ''' Incoming datagram members are dictionary members as key:value.
        If there is match with known command, the key:value is immediately returned to prevent repeated sending from server.
        Unknown commands are ignored. Setup values starting with B W or S are possible.
        A dictionary member may also present a service value, in which case the according sql table is updated.
        The dictionary members that are not recognized, are ignored and not returned.
        Returns string TODO or ''
        
        '''

        TODO = ''
        setup_changed = 0 # flag general setup change, data to be dumped into setup.sql
        msg = ''
        mval = ''
        res = 0
        sendstring = ''

        for key in data_dict:
            value = data_dict[key]
            if (key[0] == 'W' or key[0] == 'B' or key[0] == 'S') and key[-1:] != 'S' and key[-1:] != 'V' and key[-1:] != 'W': # can be general setup value
                if s.change_setup(key,value) == 0: # successful change in memory
                    setup_changed = 1 # flag the change
                    msg='general setup changed to '+key+':'+value
                    print(msg)
                    udp.syslog(msg)

            else: # some program variables to be restored?
                if key == 'TCW': # traffic volumes to be restored
                    try:
                        members = value.split(' ')
                        if len(members) == 4: # member count for traffic: udpin, udpout, tcpin, tcpout in bytes
                            udp.set_traffic(bytes_in=int(float(members[0])), bytes_out=int(float(members[1])))
                            tcp.set_traffic(bytes_in=int(float(members[2])), bytes_out=int(float(members[3])))
                            log.debug('restored traffic volumes to udp '+str(udp.get_traffic)+' tcp '+str(udp.get_traffic))
                        else:
                            log.warning('invalid number of members in value from server: '+key+':'+value)
                    except:
                        log.warning('failure in traffic restoration from '+key+':'+value)

                elif key == 'cmd': # commands
                    msg='remote command '+key+':'+value+' detected'
                    log.info(msg)
                    #udp.syslog(msg)
                    if TODO == '': # no change if not empty
                        TODO = value # command content to be parsed and executed
                        
                #return immediately the cmd to avoid unnecessary repeated execution
                sendstring = key+':'+value+'\n' # return exactly the same what we got to clear newstate. must NOT be forwarded to nagios
                udp.udpsend(sendstring) # no buffering here
                



        if setup_changed == 1: #there were some changes done  to setup, dump setup.sql!
            res = s.dump_table('setup') # dump into setup.sql, ends the trtans
            if res == 0:
                setup_changed = 0 #back to normal
                TODO = 'VARLIST' # let's report the whole setup just in case due to change. not really needed.
                log.info('setup changed, setup sql dumped')
            else:
                msg='setup change failure!'

        return TODO




    def todo_proc(self, TODO = ''):
        ''' Various commands execution based on TODO if set '''
        pulltry = 0
        todocode = 0
        sendstring = ''
        if TODO != '': # seems there is something to do
            self.todocode=self.todocode+1 # try count
            print('going to execute cmd',TODO)

            if TODO == 'VARLIST':
                todocode=s.report_setup() # general setup from asetup/setup
                #todocode=todocode+report_channelconfig() # iochannels setup from modbus_channels/dichannels, aichannels, counters* - ???
                if todocode == 0:
                    print(TODO,'execution success')
                    #TODO='' # do not do it here! see the if end

            elif TODO == 'GSMBREAK': # external router power break do8
                msg = 'power cut for communication device due to command'
                print(msg)
                udp.syslog(msg) # log message to file
                #setbit_dochannels(15,0) # gsm power down, do8
                ts_gsmbreak = ts
                gsmbreak = 1
                todocode = 0

            elif TODO.split(',')[0] == 'free': # finding the free MB and % of current or stated path, return values in ERV
                free = []
                msg = 'checking free space due to command'
                print(msg)
                udp.syslog(msg) # log message to file
                try:
                    free = free(TODO.split(',')[1]) # the parameter can be missing
                    todocode = 0
                except:
                    todocode = 1

            elif TODO == 'REBOOT': # stop the application, not the system
                #todocode=0
                msg = 'stopping, for possible script autorestart via appd.sh' # chk if appd.sh is alive?
                print(msg)
                udp.syslog(msg)
                sys.stdout.flush()
                time.sleep(1)
                sys.exit()  # STOPPING THE APPLICATION.

            elif TODO == 'FULLREBOOT': # full reboot, NOT just the application but the system!
                #stop=1 # cmd:FULLREBOOT
                try:
                    msg = 'started full reboot due to command, dumped send buffer' #
                    udp.syslog(msg)
                    udp.dump_buffer()
                    print(msg)
                    print('going to reboot now!')
                    time.sleep(2)
                    #returncode=self.subexec(['reboot'],0) # FIXME! error, no p??

                except:
                    todocode = 1
                    msg = 'full reboot failed!'
                print(msg)
                udp.syslog(msg) # log message to file

            elif TODO == 'CONFIG': #
                todocode=s.channelconfig() # configure modbus registers according to W... data in setup


            elif TODO == 'VPNON': # ovpn start
                todocode=self.subexec(self.vpn_start,2) # start vpn


            elif TODO == 'VPNOFF': # ovpn stop
                todocode=self.subexec(self.vpn_stop,2) # stop vpn


            elif TODO.split(',')[0] == 'pull':
                print('going to pull') # debug
                if len(TODO.split(',')) == 3: # download a file (with name and size given)
                    filename = TODO.split(',')[1]
                    filesize = int(TODO.split(',')[2])

                    if pulltry == 0: # first try
                        pulltry = 1 # partial download is possible, up to 10 pieces!
                        startnum = 0
                        todocode = 1 # not yet 0

                    if pulltry < 10 and todocode >0: # NOT done yet
                        if pulltry == 1: # there must be no file before the first try
                            try:
                                os.remove(filename+'.part')
                            except:
                                pass
                        else: # second and so on try
                            try:
                                filepart=filename+'.part'
                                startnum=os.stat(filepart)[6]
                                msg='partial download size '+str(dnsize)+' on try '+str(pulltry)
                            except:
                                msg='got no size for file '+os.getcwd()+'/'+filepart+', try '+str(pulltry)
                                startnum=0
                                #traceback.print_exc()
                            print(msg)
                            udp.syslog(msg)

                        if tcp.pull(filename,filesize,startnum)>0:
                            pulltry = pulltry+1 # next try will follow
                            todocode = 1
                        else: # success
                            pulltry = 0
                            todocode = 0
                else:
                    todocode = 1
                    print('wrong number of parameters for pull')

            elif TODO.split(',')[0] == 'push': # upload a file (with name and passcode given)
                try:
                    filename = TODO.split(',')[1]
                    log.info('starting push with '+filename)
                    todocode=tcp.push(filename) # no automated retry here
                except:
                    msg = 'invalid cmd syntax for push'
                    log.warning(msg)
                    #udp.syslog(msg)
                    todocode=99

            elif TODO.split(',')[0] == 'sqlread':
                if len(TODO.split(',')) == 2: # cmd:sqlread,aichannels (no extension for sql file!)
                    tablename = TODO.split(',')[1]
                    if '.sql' in tablename:
                        msg = 'invalid parameters for cmd '+TODO
                        log.warning(msg)
                        #udp.syslog(msg)
                        pulltry = 88 # need to skip all tries below
                    else:
                        todocode = s.sqlread(tablename) # hopefully correct parameter (existing table, not sql filename)
                        if tablename == 'setup' and todocode == 0: # table refreshed, let's use the new setup
                            s.channelconfig() # possibly changed setup data to modbus registers
                            s.report_setup() # let the server know about new setup
                else: # wrong number of parameters
                    todocode = 1

            elif TODO.split(',')[0] == 'RMLOG': # delete log files in working directory (d4c)
                files = glob.glob('*.log')
                try:
                    for filee in files:
                        os.remove(filee)
                        todocode = 0
                except:
                    todocode = 1 # failure to delete *.log

            elif TODO.split(',')[0] == 'pic_update': # update pic fw
                if len(TODO.split(',')) == 3: # cmd:pic_update,1,IOplaat.hex
                    try:
                        todocode = s.pic_update(TODO.split(',')[1:3])
                    except:
                        todocode = 1 # failure to update
                else:
                    log.warning('INVALID parameter count for cmd '+TODO)
                    todocode = 2
                    
            # start scripts in parallel (with 10s pause in this channelmonitor). cmd:run,nimi,0 # 0 or 1 means bg or fore
            # use background normally, the foreground process will open a window and keep it open until closed manually (in android)
            elif TODO.split(',')[0] == 'run': # FIXME! below is for android only
                if len(TODO.split(',')) == 3: # run a script in the d4c directory, no parameters allowed
                    script = TODO.split(',')[1]
                    fore = TODO.split(',')[2] # 0 background, 1 foreground
                    if os.path.exists('/sdcard/sl4a/scripts/d4c'+script): # file exists, android
                        extras = {"com.googlecode.android_scripting.extra.SCRIPT_PATH":"/sdcard/sl4a/scripts/d4c/%s" % script}
                        joru1 = "com.googlecode.android_scripting"
                        joru2 = "com.googlecode.android_scripting.activity.ScriptingLayerServiceLauncher"
                        if fore == '1': # see jatab akna lahti, pohiprotsess kaib aga edasi
                            myintent = droid.makeIntent("com.googlecode.android_scripting.action.LAUNCH_FOREGROUND_SCRIPT", None, None, extras, None, joru1, joru2).result
                        else: # see ei too mingit muud jura ette, toast kaib ainult labi
                            myintent = droid.makeIntent("com.googlecode.android_scripting.action.LAUNCH_BACKGROUND_SCRIPT", None, None, extras, None, joru1, joru2).result
                        try:
                            droid.startActivityIntent(myintent)
                            msg = 'tried to start'+script
                            if fore == 1:
                                msg = msg+' in foreground'
                            else:
                                msg = msg+' in background'
                            print(msg)
                            udp.syslog(msg)
                            todocode=0
                        except:
                            msg = 'FAILED to execute '+script+' '+str(sys.exc_info()[1])
                            log.warning(msg)
                            #udp.syslog(msg)
                            #traceback.print_exc()
                            todocode=1
                        time.sleep(10) # take a break while subprocess is active just in case...
                    elif os.path.exists('/root/d4c/'+script): # linux, file exists
                        try:
                            self.subexec('/root/d4c/'+script, submode = fore)
                            todocode = 0
                        except:
                            pass
                    else:
                        msg='file not found: '+script
                        log.warning(msg)
                        todocode = 1
                        #time.sleep(2)

                else:
                    log.warning('wrong number of parameters for cmd '+TODO)
                    todocode = 1 # wrong number of parameters

            elif TODO.split(',')[0] == 'size': # get the size of filename (cmd:size,setup.sql)
                script = TODO.split(',')[1]
                try:
                    dnsize = os.stat(script)[6]
                    todocode = 0
                except:
                    todocode = 1

            else:
                log.warning('UNIMPLEMENTED cmd '+cmd)
                
                
                
            # common part for all commands
            if todocode == 0: # success with TODO execution
                msg = 'remote command '+TODO+' successfully executed'
                log.info(msg)
                sendstring += 'ERS:0\n'
                TODO='' # no more execution
                
            else: # no success
                msg='remote command '+TODO+' execution failed or incomplete on try '+str(pulltry)
                sendstring += 'ERS:2\n'
                if TODO.split(',')[0] == 'size':
                    msg=msg+', file not found'
                if 'pull,' in TODO and pulltry<5: # pull must continue
                    msg=msg+', shall try again TODO='+TODO+', todocode='+str(todocode)
                    log.warning(msg)
                else: # no pull or enough pulling
                    msg = msg+', giving up TODO='+TODO+', todocode='+str(todocode)
                    TODO=''
                log.warning(msg)
                
            #udp.syslog(msg)
            sendstring += 'ERV:'+msg+'\n' # msh cannot contain colon or newline
            udp.udpsend(sendstring) # SEND AWAY. this can go directly, omitting buffer

            sys.stdout.flush()
            #time.sleep(1)
        else:
            pulltry = 0 # next time like first time

           

class RegularComm(SQLgeneral): # r
    ''' Checks the incoming datagram members (key,value) for commands and setup variables.
        Outputs TODO for execution and ...
    '''

    def __init__(self, interval = 120): #
        self.interval=interval # todo_proc() retries
        self.app_start=int(time.time())
        self.ts_regular=self.app_start - interval # for immediate sending on start
        self.ts=self.app_start
        self.uptime=[0,0,0]
        self.host_ip = 'unknown' # controller ip
        self.cpV = 0 # cpu load
        
        try:
            self.sync_uptime() # sys apptime to uptime[0]
            #uptime[0]=int(self.subexec('cut -f1 -d. /proc/uptime',1)) # should be avoided on npe, use only once
            self.uptime[1] = 0
            self.uptime[2] = self.uptime[0] # counting on using sys uptime instead of ts (time.time())
        except: # not unix&linux
            pass



    def get_host_ip(self, iface = 'auto'):
        ''' returns the actual ip address in use, usage
        get_ip('eth0')
        '10.80.40.234'
        '''
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockfd = sock.fileno()
        SIOCGIFADDR = 0x8915
        ip = None
        
        if iface == 'auto':
            ifacelist = ['tun0','wlan0','eth0'] # for auto
        else:
            ifacelist = [iface] # for NOT auto
            
        for iface in ifacelist:
            ifreq = struct.pack('16sH14s', iface.encode('utf-8'), socket.AF_INET, b'\x00'*14)
            try:
                res = fcntl.ioctl(sockfd, SIOCGIFADDR, ifreq)
                ip = struct.unpack('16sH2x4s8x', res)[2]
                break
            except:
                pass
            
        if ip != None:
            return socket.inet_ntoa(ip)
        else:
            return '127.0.0.1' # no other interface up
        
    
    def subexec(self, exec_cmd, submode = 1): # submode 0 - returns exit code only, 1 - waits for output, 2 - forks to background. use []
        ''' shell command execution. if submode 0-, return exit staus.. if 1, exit std output produced.
            exec_cmd is a list of cmd and parameters! use []
            FIXME: HAD TO COPY subexec HERE BECAUSE I CANNOT USE p.subexec() from here ...
        '''
        if submode == 0: # return exit status, 0 or more
            returncode=subprocess.call(exec_cmd) # ootab kuni lopetab
            return returncode  # return just the subprocess exit code
        elif submode == 1: # return everything from sdout
            proc=subprocess.Popen([exec_cmd], shell=True, stdout=subprocess.PIPE)
            result = proc.communicate()[0]
            return result
        elif submode == 2: # forks to background, does not wait for output
            returncode=subprocess.Popen(exec_cmd, shell=True) #
            return 0 # no idea how it really ends


    def sync_uptime(self):
        with open('/proc/uptime', 'r') as f:
            self.uptime[0] = int(float(f.readline().split()[0]))
        #self.uptime[1] = int(self.ts - self.app_start) # app uptime - app_start can be wrong! use sys uptime instead
        self.uptime[1] = self.uptime[0] - self.uptime[2] # use sys uptime to get app uptime
        log.debug('uptimes sys, app, app_start_uptime '+str(self.uptime))


    def regular_svc(self, svclist = ['UPW','TCW','ipV','cpV', 'mfV', 'd2W']): # baV (buffer age) is always sent, omitting buffer!
        ''' sends regular service messages that are not related to aichannels, dichannels or counters.
            Returns number of bytes sent, None if send queue was not appended at this time.
        '''
        self.ts = time.time()
        res = 0
        status = 0
        valuestring = ''
        sendstring = ''
        age = 0
        agestatus = 0
        
        if self.ts > self.ts_regular + self.interval: # time to send again


            self.sync_uptime()
            sendstring=''
            
            ## udp.send() jaoks servicetuple
            #sta_reg = str(servicetuple[0])
            #status = int(servicetuple[1])
            #val_reg = str(servicetuple[2])
            #value = str(servicetuple[3])
            
            for svc in svclist:
                if svc == 'UTW' or svc == 'TCW': # traffic
                    valuestring = str(udp.traffic[0])+' '+str(udp.traffic[1])+' '+str(tcp.traffic[0])+' '+str(tcp.traffic[1])
                    if udp.traffic[0]+udp.traffic[1]+tcp.traffic[0]+tcp.traffic[1] < 10000000:
                        status = 0 # ok
                    else:
                        status = 1
                    
                elif svc == 'ULW' or svc == 'UPW': # uptime
                    valuestring = str(self.uptime[0])+' '+str(self.uptime[1]) # diagnostic uptimes, add status!
                    if (self.uptime[0] > 1800) and (self.uptime[0] > 1800):
                    #    sendstring += '0\n' # ok
                        status = 0 
                    else:
                        status = 1
                
                elif svc == 'IPV' or svc == 'ip' or svc == 'ipV': # ip address currently in use
                    valuestring = self.get_host_ip() # ip address in use from a list starting with tun0
                
                elif svc == 'mfV': # free memory
                    valuestring = str(psutil.phymem_usage()[2]) # free memory in bytes
                
                elif svc == 'cpV': # free memory
                    self.cpV = (self.cpV + psutil.cpu_percent())/2.0
                    valuestring = str(int(round(self.cpV,0))) # cpu load %
                    
                else:
                    valuestring = 'regular service '+svc+' not yet supported'
                    
                if valuestring != None and len(valuestring) > 0:
                    res += udp.send([svc[:-1]+'S', status, svc, valuestring]) # via buffer. udp.send() adds ts
                    log.info('added to buffer regular service ' + svc+':'+valuestring)
                    ## NB! cmd or ERV responses passing the buffer, see udp.udpsend() uses above and also below.
                else:
                    log.warning('regular svc '+svc+' not supported!')
                    
            self.ts_regular = self.ts
            age = udp.get_age() # send buffer age from uniscada 
            agestatus = 1
            if age < 10 and age >= 0:
                agestatus = 0
            sendstring = 'baV:'+str(age)+'\nbaS:'+str(agestatus)+'\n' # msh cannot contain colon or newline
            udp.udpsend(sendstring) # SEND AWAY directly, omitting buffer

            return res # None if nothing sent

    def alive_fork(self, alivecmd, interval = 0): # spawn a process indicating activity, start via regular actions (not too often)
        ''' to enable checking application activity the process with lifetime of 2*interval is started via subexec() 
            the script name is descriptive and the content is sleep
        '''
        if interval == 0:
            interval = 2 * self.interval  # regular communication will keep about 2 processes alive
        tbs = alivecmd+' '+str(interval) # +' &' # & not needed
        print('alive_fork',tbs) # debug
        if alivecmd != '':
            try:
                self.subexec(tbs,2)
                return 0
            except:
                traceback.print_exc()
                return 1

    def set_host_ip(self, ip): # deprecated, get_host_ip() finds the ip itself dynamically
        return 0
    
    ## END ## 