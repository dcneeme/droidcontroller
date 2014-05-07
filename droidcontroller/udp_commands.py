# process commands received from uniscada server. to be imported by uniscada.py
#instance udp should be created.

import subprocess
import sys

from sqlgeneral import * # SQLgeneral  / vaja ka time,mb, conn jne
s=SQLgeneral() 


    
class Commands(SQLgeneral): # p
    ''' Checks the incoming datagram members (key,value) for commands and setup variables. 
        Outputs TODO for execution and ... 
    '''
        
    def __init__(self): 
        self.todocode=0 # todo_proc() retries
        #self.uptime=[int(self.subexec('cut -f1 -d. /proc/uptime',1)), 0]
        #print('system uptime',self.uptime[0])
        #s.print_table('setup') # do we have it? access to setup table is needed
        
        
    def subexec(self, exec_cmd, submode = 1): # submode 0 returns exit code only
        ''' shell command execution. if submode 0-, return exit staus.. if 1, exit std output produced. '''
        if submode == 0: # return exit status, 0 or more
            returncode=subprocess.call(exec_cmd) # ootab kuni lopetab
            return returncode  # return just the subprocess exit code
        else: # return everything from sdout
            proc=subprocess.Popen([exec_cmd], shell=True, stdout=subprocess.PIPE)
            result = proc.communicate()[0]
            return result
        
        
    def parse_udp(self, data_dict): 
        ''' Incoming datagram members are dictionary members as key:value. 
        If there is match with known command, the key:value is returned to prevent repeated sending from server.
        Unknown commands are ignored. Setup values starting with B W or S are possible. 
        A dictionary member may also present a service value, in which case the according sql table is updated. 
        The dictionary members that are not recognized, are ignored and not returned.
        Returns string TODO or ''
        '''
    
        TODO=''
        setup_changed = 0 # flag general setup change, data to be dumped into setup.sql
        msg=''
        mval=''
        res=0
        for key in data_dict:
            value=data_dict[key]
            if (key[0] == 'W' or key[0] == 'B' or key[0] == 'S') and key[-1:] != 'S' and key[-1:] != 'V' and key[-1:] != 'W': # can be general setup value
                if s.change_setup(key,value) == 0: # successful change in memory
                    setup_changed = 1 # flag the change
                    msg='general setup changed to '+key+':'+value
                    print(msg)
                    udp.syslog(msg)
                                
            else: # some program variables to be restored?
                if key == 'TCW': # traffic volumes to be restored
                    if len(value.split(' ')) == 4: # member count for traffic: udpin, udpout, tcpin, tcpout in bytes
                        for member in range(2): # udp tcp
                            udp.set_traffic[member]=int(float(value.split(' ')[member]))
                            tcp.set_traffic[member]=int(float(value.split(' ')[member+2]))
                        msg='restored traffic volumes to udp '+str(udp.get_traffic)+' tcp '+str(udp.get_traffic)
                    else:
                        msg='invalid number of members in value from server: '+key+':'+value
                        
                elif key == 'LRW': # lighting state service. no dump to sql file needed. SHOULD BE IN MAIN!
                    if len(value.split(' ')) == 4: # valid message remote control via last member
                        mval=value.split(' ')[3] #  last member
                        res=s.set_membervalue(key,4,mval,'dichannels') # svc,member,value,table='aichannels'. mval as string here!
                        #FIXME: allow any member with cfg true to be changed here, for any xxW key (to become universal)!!!
                        if res == 0: # success if 0
                            msg='set lighting state (value of LRW.3) to '+mval
                        else:
                            msg='set lighting state failure!'
                    else:
                        msg='invalid number of members in value from server: '+key+':'+value
                        
                elif key == 'LSW': # lighting SENSOR SELECTION. SHOULD BE IN MAIN!
                    if len(value.split(' ')) == 3: # valid message remote control via last member
                        mval=value.split(' ')[2] #  last member (0 1 2)
                        res=s.set_membervalue(key,3,mval,'dichannels') # svc,member,value,table='aichannels'. mval as string here!
                        #FIXME: allow any member with cfg true to be changed here, for any xxW key (to become universal)!!!
                        if res == 0: # success if 0
                            msg='set lighting sensor selection value (LSW.3) to '+mval
                        else:
                            msg='set lighting state failure!'
                    else:
                        msg='invalid number of members in value from server: '+key+':'+value
                
                elif key == 'cmd': # commands
                    msg='remote command '+key+':'+value+' detected'
                    print(msg)
                    udp.syslog(msg)
                    if TODO == '': # no change if not empty
                        TODO=value # command content to be parsed and executed
                        print('TODO set to',TODO)
                    else:
                        print('could not set TODO to',value,', TODO still',TODO)
                
                if len(msg)>0:
                    print(msg)
                    udp.syslog(msg)

     
        if setup_changed == 1: #there were some changes done  to setup, dump setup.sql!
            res=s.dump_table('setup') # dump into setup.sql, ends the trtans
            if res == 0:
                setup_changed=0 #back to normal
                TODO='VARLIST' # let's report the whole setup just in case due to change. not really needed.
            else:
                msg='setup change failure!'
            
            
        return TODO

            
            
            
    def todo_proc(self, TODO = ''):        
        ''' Various commands execution based on TODO if set ''' 
        pulltry=0 
        todocode=0
        sendstring=''
        if TODO != '': # seems there is something to do
            self.todocode=self.todocode+1 # try count
            print('going to execute cmd',TODO)
            
            if TODO == 'VARLIST':
                todocode=s.report_setup() # general setup from asetup/setup
                #todocode=todocode+report_channelconfig() # iochannels setup from modbus_channels/dichannels, aichannels, counters* - ???
                if todocode == 0:
                    print(TODO,'execution success')
                    #TODO='' # do not do it here! see the if end
                    
            if TODO == 'REBOOT': # stop the application, not the system
                #todocode=0
                msg='stopping, for possible script autorestart via appd.sh' # chk if appd.sh is alive?
                print(msg)
                udp.syslog(msg) 
                sys.stdout.flush()
                time.sleep(1)
                sys.exit()  # STOPPING THE APPLICATION.
                        
            if TODO == 'GSMBREAK': # external router power break do8
                msg='power cut for communication device due to command'
                print(msg)
                udp.syslog(msg) # log message to file
                #setbit_dochannels(15,0) # gsm power down, do8
                ts_gsmbreak = ts
                gsmbreak = 1
                todocode = 0
                
                
            if TODO.split(',')[0] == 'free': # finding the free MB and % of current or stated path, return values in ERV
                free=[]
                msg='checking free space due to command'
                print(msg)
                udp.syslog(msg) # log message to file
                try:
                    free=free(TODO.split(',')[1]) # the parameter can be missing
                    todocode=0
                except:        
                    todocode=1


            if TODO == 'FULLREBOOT': # full reboot, NOT just the application but the system!
                #stop=1 # cmd:FULLREBOOT
                try:
                    msg='started full reboot due to command' # 
                    udp.syslog(msg)
                    print(msg)
                    print('going to reboot now!')
                    time.sleep(2)
                    #returncode=self.subexec(['reboot'],0) # FIXME! error, no p??
                        
                except:
                    todocode=1
                    msg='full reboot failed!'
                print(msg)
                udp.syslog(msg) # log message to file

            if TODO == 'CONFIG': #
                todocode=s.channelconfig() # configure modbus registers according to W... data in setup

                    
            if TODO.split(',')[0] == 'pull':
                print('going to pull') # debug
                if len(TODO.split(',')) == 3: # download a file (with name and size given)
                    filename=TODO.split(',')[1]
                    filesize=int(TODO.split(',')[2])

                    if pulltry == 0: # first try
                        pulltry=1 # partial download is possible, up to 10 pieces!
                        startnum=0
                        todocode=1 # not yet 0

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

                        if pull(filename,filesize,startnum)>0:
                            pulltry=pulltry+1 # next try will follow
                            todocode=1
                        else: # success
                            pulltry=0
                            todocode=0
                else:
                    todocode=1
                    print('wrong number of parameters for pull')
                    
            if TODO.split(',')[0] == 'push': # upload a file (with name and passcode given)
                try:
                    filename=TODO.split(',')[1]
                    print('starting push with',filename)
                    todocode=push(filename) # no automated retry here
                except:
                    msg='invalid cmd syntax for push'
                    print(msg)
                    udp.syslog(msg)
                    todocode=99

            if TODO.split(',')[0] == 'sqlread':
                if len(TODO.split(',')) == 2: # cmd:sqlread,aichannels (no extension for sql file!)
                    tablename=TODO.split(',')[1]
                    if '.sql' in tablename:
                        msg='invalid parameters for cmd '+TODO
                        print(msg)
                        udp.udp.syslog(msg)
                        pulltry=88 # need to skip all tries below
                    else:
                        todocode=sqlread(tablename) # hopefully correct parameter (existing table, not sql filename)
                        if tablename == 'setup' and todocode == 0: # table refreshed, let's use the new setup
                            s.channelconfig() # possibly changed setup data to modbus registers
                            s.report_setup() # let the server know about new setup
                else: # wrong number of parameters
                    todocode=1
            
            if TODO.split(',')[0] == 'RMLOG': # delete log files in working directory (d4c)
                files=glob.glob('*.log')
                try:
                    for filee in files:
                        os.remove(filee)
                        todocode=0
                except:
                    todocode=1 # failure to delete *.log
                    
            # start scripts in parallel (with 10s pause in this channelmonitor). cmd:run,nimi,0 # 0 or 1 means bg or fore
            # use background normally, the foreground process will open a window and keep it open until closed manually
            if TODO.split(',')[0] == 'run': # FIXME! for linux
                if len(TODO.split(',')) == 3: # run any script in the d4c directory as foreground or background subprocess
                    script=TODO.split(',')[1]
                    if script in os.listdir('/sdcard/sl4a/scripts/d4c'): # file exists
                        fore=TODO.split(',')[2] # 0 background, 1 foreground
                        extras = {"com.googlecode.android_scripting.extra.SCRIPT_PATH":"/sdcard/sl4a/scripts/d4c/%s" % script}
                        joru1="com.googlecode.android_scripting"
                        joru2="com.googlecode.android_scripting.activity.ScriptingLayerServiceLauncher"
                        if fore == '1': # see jatab akna lahti, pohiprotsess kaib aga edasi
                            myintent = droid.makeIntent("com.googlecode.android_scripting.action.LAUNCH_FOREGROUND_SCRIPT", None, None, extras, None, joru1, joru2).result
                        else: # see ei too mingit muud jura ette, toast kaib ainult labi
                            myintent = droid.makeIntent("com.googlecode.android_scripting.action.LAUNCH_BACKGROUND_SCRIPT", None, None, extras, None, joru1, joru2).result
                        try:
                            droid.startActivityIntent(myintent)
                            msg='tried to start'+script
                            if fore == 1:
                                msg=msg+' in foreground'
                            else:
                                msg=msg+' in background'
                            print(msg)
                            udp.syslog(msg)
                            todocode=0
                        except:
                            msg='FAILED to execute '+script+' '+str(sys.exc_info()[1])
                            print(msg)
                            udp.syslog(msg)
                            #traceback.print_exc()
                            todocode=1
                        time.sleep(10) # take a break while subprocess is active just in case...
                    else:
                        msg='file not found: '+script
                        print(msg)
                        todocode=1
                        time.sleep(2)
                    
                else:
                    todocode=1 # wrong number of parameters

            if TODO.split(',')[0] == 'size': # get the size of filename (cmd:size,setup.sql)
                script=TODO.split(',')[1]
                try:
                    dnsize=os.stat(script)[6]
                    todocode=0
                except:
                    todocode=1


            # common part for all commands
            if todocode == 0: # success with TODO execution
                msg='remote command '+TODO+' successfully executed'
                sendstring=sendstring+'ERS:0\n'
                TODO='' # no more execution
            else: # no success
                msg='remote command '+TODO+' execution failed or incomplete on try '+str(pulltry)
                sendstring=sendstring+'ERS:2\n'
                if TODO.split(',')[0] == 'size':
                    msg=msg+', file not found'
                if 'pull,' in TODO and pulltry<5: # pull must continue
                    msg=msg+', shall try again TODO='+TODO+', todocode='+str(todocode)
                else: # no pull or enough pulling
                    msg=msg+', giving up TODO='+TODO+', todocode='+str(todocode)
                    TODO=''
            print(msg)
            udp.syslog(msg)
            sendstring=sendstring+'ERV:'+msg+'\n' # msh cannot contain colon or newline
            udp.udpsend(sendstring) # SEND AWAY. no need for server ack so using 0 instead of inumm

            sys.stdout.flush()
            #time.sleep(1)
        else:
            pulltry=0 # next time like first time
            
     

class RegularComm(SQLgeneral): # r
    ''' Checks the incoming datagram members (key,value) for commands and setup variables. 
        Outputs TODO for execution and ... 
    '''
        
    def __init__(self, interval = 60): #
        self.interval=interval # todo_proc() retries
        self.app_start=int(time.time())
        self.ts_regular=self.app_start - interval # for immediate sending on start
        self.ts=self.app_start
        self.uptime=[0,0]
        self.sync_uptime()
        
      
    def subexec(self, exec_cmd, submode = 1): # submode 0 returns exit code only
        ''' shell command execution. if submode 0-, return exit staus.. if 1, exit std output produced. 
            FIXME: HAD TO COPY subexec HERE BECAUSE I CANNOT USE p.subexec() from here ...
        '''
        if submode == 0: # return exit status, 0 or more
            returncode=subprocess.call(exec_cmd) # ootab kuni lopetab
            return returncode  # return just the subprocess exit code
        else: # return everything from sdout
            proc=subprocess.Popen([exec_cmd], shell=True, stdout=subprocess.PIPE)
            result = proc.communicate()[0]
            return result
        
     
    def sync_uptime(self):
        #self.uptime[0]=0 # 
        self.uptime[0]=int(self.subexec('cut -f1 -d. /proc/uptime',1))
        self.uptime[1]=int(self.ts - self.app_start) # sys and app uptimes
        print('uptimes sys,app',self.uptime) # debug
        

    def set_host_ip(self, invar):
        self.host_ip=invar
    
    
    def get_host_ip(self):
        #self.host_ip=p.subexec('./getnetwork.sh',1).split(' ')[1] # mac and ip from the system
        self.host_ip=self.subexec('./getnetwork.sh',1).split(' ')[1] # mac and ip from the system
        print('get_host_ip:',self.host_ip)
    
    
    def regular_svc(self, svclist = ['ULW','UTW','ip']): # default are uptime and traffic services
        ''' sends regular service messages that are not related to aichannels, dichannels or counters  '''
        self.ts=time.time()
        if self.ts < self.ts_regular + self.interval: # break
            return None
            
        self.sync_uptime()
        sendstring=''
        for svc in svclist:
            if svc == 'UTW': # traffic
                msg=str(udp.traffic[0])+' '+str(udp.traffic[1])+' '+str(tcp.traffic[0])+' '+str(tcp.traffic[1])+'\nUTS:' # adding status
                if udp.traffic[0]+udp.traffic[1]+tcp.traffic[0]+tcp.traffic[1] < 10000000:
                    sendstring=sendstring+'0\n' # ok
                else:
                    sendstring=sendstring+'1\n' # warning about recent restart
            elif svc == 'ULW': # uptime
                msg=str(self.uptime[0])+' '+str(self.uptime[1])+'\nULS:' # diagnostic uptimes, add status!
                if (self.uptime[0] > 1800) or (self.uptime[0] > 1800):
                    sendstring=sendstring+'0\n' # ok
                else:
                    sendstring=sendstring+'1\n' # warning

            elif svc == 'ip': # own ip
                msg=str(self.host_ip) # refreshing from time to time? via set_host_ip()

            sendstring=sendstring+svc+':'+msg+'\n'
        res=udp.udpsend(sendstring) # loop over, SEND AWAY        
        self.ts_regular=self.ts
        return res # 0 is ok 
                    
                    