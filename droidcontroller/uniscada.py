# This Python file uses the following encoding: utf-8

# send and receive monitoring and control messages to from UniSCADA monitoring system
# able to restore unsent history from buffer2server.sql when connectivity restored
# FIXME - some services should be sent out of general queue! IPV,UPW,cmd,ERV - use udpsend()!

import time, datetime
import sqlite3
import traceback
from socket import *
import sys
import os
import gzip
import tarfile
import requests
import logging
log = logging.getLogger(__name__)

class UDPchannel():
    ''' Sends away the messages, combining different key:value pairs and adding host id and time. Listens for incoming commands and setup data.
    Several UDPchannel instances can be used in parallel, to talk with different servers.

    Used by sqlgeneral.py

    '''

    def __init__(self, id ='000000000000', ip='127.0.0.1', port=44445, receive_timeout=0.1, retrysend_delay=3, loghost='0.0.0.0', logport=514, copynotifier=None): # delays in seconds
        #from droidcontroller.connstate import ConnState
        from droidcontroller.statekeeper import StateKeeper
        self.sk = StateKeeper(off_tout=300, on_tout=0) # conn state with up/down times. 
        # do hard reboot via 0xFEED when changed to down. 
        # what to do if never up? keep hard rebooting?
        
        try:
            from droidcontroller.gpio_led import GPIOLED
            self.led = GPIOLED() # led alarm and conn
        except:
            log.warning('GPIOLED not imported')
                        
        self.set_copynotifier(copynotifier) # parallel to uniscada notification in another format
        self.host_id = id # controller ip as tun0 wlan0 eth0 127.0.0.1
        self.ip = ip # monitoring server
        self.port = port # monitoring server
        self.saddr = (self.ip,self.port)
        
        self.loghost = loghost
        self.logport = logport
        self.logaddr = (self.loghost,self.logport) # tuple

        self.traffic = [0,0] # UDP bytes in, out
        self.UDPSock = socket(AF_INET,SOCK_DGRAM)
        self.UDPSock.settimeout(receive_timeout)
        self.retrysend_delay = retrysend_delay
        self.inum = 0 # sent message counter

        self.UDPlogSock = socket(AF_INET,SOCK_DGRAM)
        self.UDPlogSock.settimeout(None) # for syslog
        self.UDPlogSock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1) # broadcast allowed

        log.info('init: created uniscada and syslog connections to '+ip+':'+str(port)+' and '+loghost+':'+str(logport))
        self.table = 'buff2server' # can be anything, not accessible to other objects WHY? would be useful to know the queue length...
        self.sent = '' # last servicetuple sent to the buffer
        self.age = 0 # unsent history age, also to be queried
        self.Initialize()

    def Initialize(self):
        ''' initialize time/related variables and create buffer database with one table in memory '''
        self.ts = int(round(time.time(),0)) # current time?
        #self.ts_inum = self.ts # inum increase time, is it used at all? NO!
        self.ts_unsent = self.ts # last unsent chk
        self.ts_udpsent = self.ts
        self.ts_udpgot = self.ts
        self.ts_udpunsent = self.ts # failed send timestamp
        
        self.conn = sqlite3.connect(':memory:')
        #self.cur=self.conn.cursor() # cursors to read data from tables / cursor can be local
        self.makebuffer() # create buffer table for unsent messages
        self.linecount = 0 # lines in buffer
        self.undumped = 0 # not yet dumped into buff2server.sql 
        #self.setIP(self.ip)
        #self.setLogIP(self.loghost)


    def get_conf(self, key, filename, delimiter = ' '): # delimiter separated key and string in the file
        ''' Return the string after the key and delimiter from the file '''
        try:
            with open(filename) as f:
                lines = f.read().splitlines()
                for line in lines:
                    if key+delimiter in line[0:len(key)+len(delimiter)]:
                        return line.split(delimiter)[1] # [4:len(key)+1]
        except:
            log.error('no readable file '+filename+' for '+key)
        return None

    
    def get_ip(self): # obsolete, use r.get_host_ip()
        ''' Returns ONE effective ip address, the selection order is: tun0, eth0, wlan0, eth1 '''
        pass # kuidas jalgida ip adr vms olekut pythonist?
        
    
    def getIP(self): 
        ''' returns server ip for this instance '''
        return self.ip
        
    
    def get_age(self):
        ''' age of oldest unsent message in buffer ''' 
        return self.age
        
        
    def set_copynotifier(self, copynotifier):
        self.copynotifier = copynotifier
        
    
    def setIP(self, invar):
        ''' Set the monitoring server ip address '''
        self.ip = invar
        self.saddr = (self.ip,self.port) # refresh needed

    def setLogIP(self, invar):
        ''' Set the syslog monitor ip address '''
        self.loghost = invar
        self.logaddr = (self.loghost,self.logport) # refresh needed


    def setPort(self, invar):
        ''' Set the monitoring server UDP port '''
        self.port = invar
        self.saddr = (self.ip,self.port) # refresh needed


    def setID(self, invar):
        ''' Set the host id '''
        self.host_id = invar


    def setRetryDelay(self, invar):
        ''' Set the monitoring server UDP port '''
        self.retrysend_delay = invar


    def getTS(self):
        ''' returns timestamps for last send trial and successful receive '''
        return self.ts_udpsent, self.ts_udpgot

    def getID(self):
        ''' returns host id for this instance '''
        return self.host_id



    def getLogIP(self):
        ''' returns syslog server ip for this instance '''
        return self.loghost


    def get_traffic(self):
        return self.traffic # tuple in, out


    def set_traffic(self, bytes_in = None, bytes_out = None): # set UDP traffic counters (it is possible to update only one of them as well)
        ''' Restores UDP traffic counter'''
        if bytes_in != None:
            if not bytes_in < 0:
                self.traffic[0] = bytes_in
            else:
                log.warning('invalid bytes_in',bytes_in)

        if bytes_out != None:
            if not bytes_out < 0:
                self.traffic[1] = bytes_out
            else:
                log.warning('invalid bytes_out',bytes_out)


    def set_inum(self,inum = 0): # set message counter
        self.inum=inum


    def get_inum(self):  #get message counter
        return self.inum


    def get_ts_udpgot(self):  #get ts of last ack from monitoring server
        return self.ts_udpgot


    def sqlread(self, table): # drops table and reads from file <table>.sql that must exist
        ''' restore buffer from dump. basically the same as in sqlgeneral.py '''
        sql = ''
        filename=table+'.sql' # the file to read from
        try:
            sql = open(filename).read()
            msg = 'found '+filename
            log.info(msg)
        except:
            return 1 # no dump

        Cmd = 'drop table if exists '+table
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.commit()
            self.conn.executescript(sql) # read table into database
            self.conn.commit()
            msg = 'successfully recreated table '+table
            log.info(msg)
            return 0

        except:
            msg = 'sqlread() problem for '+table+': '+str(sys.exc_info()[1])
            log.warning(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1
            
            
    def makebuffer(self): # rereads buffer dump or creates new empty one if dump does not exist
        ''' Old dumped rows in buffer will be sent first if not empty '''
        
        if self.sqlread(self.table) == 0: # dump read
            log.info('reusing buffer dump to fill the possible gaps')
            return 0
            
        else: # create new table
            Cmd='drop table if exists '+self.table
            self.conn.execute(Cmd) # drop the table if it exists
            sql="CREATE TABLE "+self.table+"(sta_reg,status NUMERIC,val_reg,value,ts_created NUMERIC,inum NUMERIC,ts_tried NUMERIC);" # semicolon needed for NPE for some reason!
            try:
                self.conn.executescript(sql) # read table into database
                self.conn.commit()
                msg='no dump to restore, (re)created table '+self.table
                log.info(msg)
                return 0
            except:
                msg='failed to reread and create buffer table, '+str(sys.exc_info()[1])
                log.warning(msg)
                #syslog(msg)
                #traceback.print_exc()
                time.sleep(1)
                return 1


    def delete_buffer(self): # empty buffer
        Cmd = 'delete from '+self.table
        try:
            self.conn.execute(Cmd)
            self.conn.commit()
            log.debug('buffer content deleted')
            self.dump_buffer() # empty sql file too!
        except:
            traceback.print_exc()

    def dump_buffer(self):
        ''' Writes the buffer table into a SQL-file to keep unsent data '''
        msg=self.table+' dump into '+self.table+'.sql'
        log.info(msg)
        try:
            with open(self.table+'.sql', 'w') as f:
                for line in self.conn.iterdump(): # see dumbib koik kokku!
                    if self.table in line: # needed for one table only! without that dumps all!
                        f.write('%s\n' % line)
            return 0
        except:
            msg = 'FAILURE dumping '+self.table+'! '+str(sys.exc_info()[1])
            log.warning(msg)
            #syslog(msg)
            traceback.print_exc()
            return 1

            

    def send(self, servicetuple): # store service components to buffer for send and resend
        ''' Adds service components into buffer table to be sent as a string message
            the components are sta_reg = '', status = 0, val_reg = '', value = ''
        '''
        if servicetuple == None:
            log.warning('ignored servicetuple with value None')
            return 2
            
        try:
            sta_reg = str(servicetuple[0])
            status = int(servicetuple[1])
            val_reg = str(servicetuple[2])
            value = str(servicetuple[3])
            self.ts = int(round(time.time(),0)) # no decimals
            Cmd = "INSERT into "+self.table+" values('"+sta_reg+"',"+str(status)+",'"+val_reg+"','"+value+"',"+str(self.ts)+",0,0)" # inum and ts_tried left initially empty
            #print(Cmd) # debug
            self.conn.execute(Cmd)
            #self.last = servicetuple
            if self.copynotifier:
                self.copynotifier(servicetuple) # see on nagios.py sees asuv output_and_send
            return 0
        except:
            msg = 'FAILED to write svc into buffer'
            #syslog(msg) # incl syslog
            log.warning(msg)
            traceback.print_exc()
            return 1


    #def get_last(self):
    #    ''' Return last servicetuple sent to the buffer. Can be used for parallel messaging for example. '''
    #    return self.last
    
    
    def unsent(self, maxage=86400):   # 24 hours max history to be kept
        ''' Counts the non-acknowledged messages and removes older than maxage seconds (24h by default). 
            If no more lines in buffer, dump empty table into sql file to avoid rows de ja vue on next start
        '''
            
        self.ts = int(round(time.time(),0))
        self.ts_unsent = self.ts
        mintscreated = 0
        maxtscreated = 0
        delcount = 0
        
        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION"  # buff2server
            self.conn.execute(Cmd)
            #Cmd="SELECT count(sta_reg),min(ts_created),max(ts_created) from "+self.table+" where ts_created+0+"+str(10*self.retrysend_delay)+"<"+str(self.ts) # yle 3x regular notif
            Cmd = "SELECT count(sta_reg),min(ts_created),max(ts_created) from "+self.table+" where ts_created+0+"+str(maxage)+"<"+str(self.ts) # too old to keep
            cur = self.conn.cursor()
            cur.execute(Cmd)
            for rida in cur: # only one line for count if any at all
                delcount = rida[0] # to be removed as too old
                
            if delcount > 0: # something to be removed
                Cmd = "delete from "+self.table+" where ts_created+0+"+str(maxage)+"<"+str(self.ts)
                self.conn.execute(Cmd)
                log.warning('deleted '+str(delcount)+' too old lines from buffer')

            Cmd="SELECT count(sta_reg),min(ts_created),max(ts_created) from "+self.table
            cur.execute(Cmd)
            for rida in cur: # only one line for count if any at all
                linecount = rida[0] # int
                
            msg=''
            #if self.sk.get_state()[0] == 0: # no conn
            if linecount > self.linecount + 100: # dump again while the table keeps increasing
                msg=str(linecount)+' messages to be dumped from table '+self.table+'!'
            elif linecount == 0 and self.linecount > 0: # dump empty table into sql file
                msg='empty buffer to be dumped from table '+self.table+'!'
            
            if msg != '':
                log.info(msg)
                self.dump_buffer() # dump to add more lines into sql file
                self.linecount = linecount # dumped rows
            
            self.undumped = linecount - self.linecount
            self.conn.commit() # buff2server transaction end
            return linecount # 0
            
        except:
            msg='problem with unsent, '+str(sys.exc_info()[1])
            log.warning(msg)
            traceback.print_exc()
            #sys.stdout.flush()
            #time.sleep(1)
            return 1

        #unsent() end
        

    def udpreset(self):
        ''' Reopen socket  s the first measure to reconnect '''
        self.UDPSock = socket(AF_INET,SOCK_DGRAM)
        self.UDPSock.settimeout(self.receive_timeout)
     

    def buff2server(self): # send the buffer content
        ''' ONE UDP monitoring message creation and sending (using self.udpsend).
            Happens based on already existing buff2server data. Only the oldest rows will be sent!
            buff2server rows successfully sent will be later deleted by udpread()
            (based on one or more in: contained in the received  message).
        '''
        timetoretry = 0 # local
        ts_created = 0 # local
        svc_count = 0 # local
        sendstring = ''
        cur = self.conn.cursor()
        cur2 = self.conn.cursor()
        limit = self.sk.get_state()[0] * 49 + 1  ## 1 key:value to try if conn down, 5 if up. 100 is too much, above 1 kB ## 
        age = 0 # the oldest, will be self.age later
        #log.info('...trying to select and send max '+str(limit)+' buffer lines')
        
        #if self.sk.get_state()[0] == 0: # no conn
        #    timetoretry = int(self.ts_udpunsent + 3 * self.retrysend_delay) # try less often during conn break
        #else: # conn ok
        #    timetoretry = int(self.ts_udpsent + self.retrysend_delay)
        if self.ts_udpsent > self.ts_udpunsent:
            log.debug('using shorter retrysend_delay, conn ok') ##
            timetoretry = int(self.ts_udpsent + self.retrysend_delay)
        else:
            log.debug('using longer retrysend_delay, conn NOT ok') ##
            timetoretry = int(self.ts_udpunsent + 3 * self.retrysend_delay) # longer retry delay with no conn
            
        if self.ts < timetoretry: # too early to send again
            log.debug('conn state '+str(self.sk.get_state()[0])+'. wait with buff2server until timetoretry '+str(int(timetoretry))) ##
            return 0 # perhaps next time
        else:
            log.debug('buff2server execution due to time '+str(self.ts-timetoretry)+' s past timetoretry '+str(timetoretry))
        
        self.unsent()  # delete too old lines, count the rest
        
        Cmd = "BEGIN IMMEDIATE TRANSACTION" # buff2server
        try:
            self.conn.execute(Cmd)
            #Cmd = 'select min(ts_created+0) from '+self.table # the oldest timestamp
            Cmd = 'select ts_created+0 from '+self.table+' group by ts_created limit '+str(limit) # find the oldest creation timestamp(s)
            #log.info(Cmd) ##
            cur.execute(Cmd)
            
            for row in cur: # ts alusel, iga ts jaoks oma in
                ts_created = int(round(row[0],0)) if row[0] != '' else 0 # should be int
                
                #if age == 0: # vanim, vaid esimesel lugemisel
                if (self.ts - ts_created) > age:
                    age = int(self.ts - ts_created) # find the oldest in the group
                    
                log.debug('processing ts_created '+str(ts_created)+', age '+str(self.ts - ts_created)+', the oldest age '+str(age))
                #if ts_created > 1433000000: # valid ts AGA kui on vale siis mingu serveri aeg
                self.inum += 1 # increase the message number  for every ts_created
                sendstr = "in:" + str(self.inum) + ","+str(ts_created)+"\n" # start the new in: block    
                Cmd = 'SELECT * from '+self.table+' where ts_created='+str(ts_created)
                log.debug('selecting rows for inum'+str(self.inum)+': '+Cmd) # debug
                cur2.execute(Cmd)
                self.age = age # the oldest in these grouped timestamps
                
                for srow in cur2:
                    svc_count += 1
                    sta_reg = srow[0]
                    status = srow[1] if srow[1] != '' else 0
                    val_reg = srow[2]
                    value = srow[3]
                    if val_reg != '':
                        sendstr += val_reg+":"+str(value)+"\n"
                    if sta_reg != '':
                        sendstr += sta_reg+":"+str(status)+"\n"
                
                if len(sendstr) > 0:
                    sendstring += sendstr
                    log.debug('added to sendstring in related sendstr: '+sendstr.replace('\n',' ')) ###
                    Cmd = "update "+self.table+" set ts_tried="+str(int(self.ts))+",inum="+str(self.inum)+" where ts_created="+str(ts_created)
                    log.debug('buffer update cmd: '+Cmd) # update all rows with this ts_creted together
                    self.conn.execute(Cmd)
                else:
                    log.warning('!! NO svc data for ts selection with limit'+str(limit))
                    
            # ts loop end
            self.conn.commit() # buff2server transaction end
        
            if svc_count > 0: # there is something to be sent!
                #sendstring = "in:" + str(self.inum) + ","+str(ts_created)+"\n" + sendstring # in alusel vastuses toimub puhvrist kustutamine
                sendstring = "id:" + str(self.host_id) + "\n" + sendstring # alustame sellega datagrammi
                log.debug('going to udpsend from buff2server, sendstring : '+sendstring) ##
                self.udpsend(sendstring, self.age) # sending away
            return 0
        
            
        except:
            log.warning('PROBLEM with creating message to be sent based on '+self.table)
            traceback.print_exc()
            return 1



    def udpsend(self, sendstring = '', age = 0): # actual udp sending, no resend. give message as parameter. used by buff2server too.
        ''' Sends UDP data immediately, without buffer, adding self.inum if ask_ack == True. DO NOT MISUSE, prevents gap filling! 
            Only the key:value pairs with similar timestamp are combined into one message!
            Common for all included keyvalue pairs (ts) should be included in the string to send.
        '''
        if sendstring == '': # nothing to send
            log.warning('nothing to send!')
            return 1
        
        if not 'id:' in sendstring: # probably response to command not via buffer
            sendstring = 'id:'+str(self.host_id)+'\n'+sendstring
            log.warning('added id to the sendstring to '+str(self.saddr)+': '+sendstring)
        
        self.traffic[1] = self.traffic[1] + len(sendstring) # adding to the outgoing UDP byte counter

        if 'led' in dir(self):
            self.led.commLED(0) # off, blinking shows sending and time to ack
        
        try:
            sendlen = self.UDPSock.sendto(sendstring.encode('utf-8'),self.saddr) # tagastab saadetud baitide arvu
            self.traffic[1] = self.traffic[1]+sendlen # traffic counter udp out
            msg = '==>> sent ' +str(sendlen)+' bytes with age '+str(age)+' to '+str(repr(self.saddr))+' '+sendstring.replace('\n',' ')   # show as one line
            log.info(msg)
            #syslog(msg)
            sendstring = ''
            self.ts_udpsent = self.ts # last successful udp send
            return sendlen
        except:
            #msg = 'udp send failure to '+str(repr(self.saddr))+' for '+str(int(self.ts - self.ts_udpsent))+' s, '+str(self.linecount)+' rows dumped, '+str(self.undumped)+' undumped' # cannot send, problem with connectivity
            #syslog(msg)
            msg = 'send FAILURE to'+str(self.saddr)
            log.warning(msg)
            self.ts_udpunsent = self.ts # last UNsuccessful udp send
            traceback.print_exc()

            if 'led' in dir(self):
                self.led.alarmLED(1) # send failure
            
            return None


    def read_buffer(self, mode = 0): # 0 prints content, 1 is silent but returns record count, min and max ts
        ''' reads the content of the buffer, debugging needs mainly.
            Returns the number of waiting to be deleted messages, the earliest and the latest timestamps. '''
        if mode == 0: # just print the waiting messages
            Cmd ="SELECT * from "+self.table
            cur = self.conn.cursor()
            cur.execute(Cmd)
            for row in cur:
                print(repr(row))
        elif mode == 1: # stats
            Cmd ="SELECT count(ts_created),min(ts_created),max(ts_created) from "+self.table
            cur = self.conn.cursor()
            cur.execute(Cmd)
            for row in cur:
                return row[0],row[1],row[2] # print(repr(row))


    def datasplit(self, data):
        ''' tykeldab in keyvaluega datagrammi, igas jupois kordab id vaartust '''
        dataout = []
        if "id:" in data:
            lines = data[data.find("id:")+3:].splitlines() 
            id = lines[0] 
            incount = len(data.split('in:')) - 1 # 0 if n is missing
            if incount > 1:
                for i in range(incount):
                    inpos = data.find('in:')
                    inn = data[inpos + 3:].splitlines()[0]
                    appdata = 'id:'+id+'\nin:'+data.split('in:')[1]
                    dataout.append(appdata)
                    data = data[inpos+4+len(inn):]
            else:
                dataout.append(data)
            return dataout # list
        else:
            log.info('invalid data from server, missing id')
        return dataout

    
    def udpread(self):
        ''' Checks received data for monitoring server to see if the data contains key(s) "in:",
            then deletes the rows with this inum in the sql table.
            If the received datagram contains more data, these key:value pairs are
            returned as dictionary.
        '''
        datagram = ''
        indata =[]
        data = ''
        data_dict = {} # possible setup and commands
        sendstring = ''

        try: # if anything is comes into udp buffer before timepout
            buf = 1024
            rdata, raddr = self.UDPSock.recvfrom(buf)
            datagram = rdata.decode("utf-8") # python3 related need due to mac in hex
        except:
            #print('no new udp data received') # debug
            #traceback.print_exc()
            return None

        if len(datagram) > 0: # something arrived
            #log.info('>>> got from receiver '+str(repr(data)))
            self.traffic[0] = self.traffic[0]+len(datagram) # adding top the incoming UDP byte counter
            log.info('<<<< got from server '+str(datagram.replace('\n', ' ')))

            if (int(raddr[1]) < 1 or int(raddr[1]) > 65536):
                msg='illegal remote port '+str(raddr[1])+' in the message received from '+raddr[0]
                log.warning(msg)
                #syslog(msg)

            if raddr[0] != self.ip:
                msg = 'illegal sender '+str(raddr[0])+' of message: '+str(repr(data))+' at '+str(int(self.ts))  # ignore the data received!
                log.warning(msg)
                #syslog(msg)
                data='' # data destroy

            if "id:" in datagram: # first check based on host id existence in the received message, must exist to be valid message!
                in_id = datagram[datagram.find("id:")+3:].splitlines()[0]
                if in_id != self.host_id:
                    log.warning("invalid id "+in_id+" in server message from "+str(raddr[0])) # this is not for us!
                    datagram = ''
                    return {} # error condition, traffic counter was still increased
                else:
                    #log.info('got ack or cmd from server '+str(raddr[0])) #### 
                    self.sk.up()
                    self.ts_udpgot = self.ts # timestamp of last udp received
                    if 'led' in dir(self):
                        self.led.commLED(1) # data from server, comm OK
                    
                indata = self.datasplit(datagram)  # into pieces with separate id and in if exists
                for data in indata:
                    lines=data.splitlines() # split message into key:value lines
                    for i in range(len(lines)): # looking into every member of incoming message
                        if ":" in lines[i]:
                            line = lines[i].split(':')
                            sregister = line[0] # setup reg name
                            svalue = line[1] # setup reg value
                            log.debug('processing key:value '+sregister+':'+svalue)
                            if sregister != 'in' and sregister != 'id': # may be setup or command (cmd:)
                                msg='got setup/cmd reg:val '+sregister+':'+svalue  # need to reply in order to avoid retransmits of the command(s)
                                log.info(msg)
                                data_dict.update({ sregister : svalue }) # in and id are not included in dict
                            
                            else:
                                if sregister == "in": # one such a key in message
                                    instr = data[data.find("in:")+3:].splitlines()[0].split(',')[0]
                                    inumm = int(instr) # loodaks integerit
                                    if inumm > 0:   # valid inum
                                        msg='got ack '+str(inumm)+' in message: '+data.replace('\n',' ')
                                        log.debug(msg)
                                        if inumm > self.inum:
                                            self.inum = inumm
                                            log.info('synced self.inum to '+str(self.inum))

                                        Cmd="BEGIN IMMEDIATE TRANSACTION" # buff2server, to delete acknowledged rows from the buffer
                                        self.conn.execute(Cmd) # buff2server ack transactioni algus, loeme ja kustutame saadetud read
                                        Cmd="DELETE from "+self.table+" WHERE inum='"+str(inumm)+"'"  # deleting all rows where inum matches server ack
                                        log.debug(Cmd)
                                        try:
                                            self.conn.execute(Cmd) # deleted
                                        except:
                                            msg='problem with '+Cmd+'\n'+str(sys.exc_info()[1])
                                            log.warning(msg)
                                            #syslog(msg)
                                            time.sleep(1)
                                        self.conn.commit() # buff2server transaction end

                return data_dict # possible key:value pairs here for setup change or commands. 
                # returns {} in case of ack with no cmd. datadict does not contain id or in values.
        else:
            return None


    def syslog(self, msg,logaddr=()): # sending out syslog message to self.logaddr
        msg = msg+"\n" # add newline to the end
        #print('syslog send to',self.logaddr) # debug
        dnsize = 0
        if self.logaddr == None and logaddr != ():
            self.logaddr = logaddr

        try: #
            self.UDPlogSock.sendto(msg.encode('utf-8'),self.logaddr)
            if not '255.255.' in self.logaddr[0] and not '10.0.' in self.logaddr[0] and not '192.168.' in self.logaddr[0]: # sending syslog out of local network
                dnsize=len(msg) # udp out increase, payload only
        except:
            pass # kui udp ei toimi, ei toimi ka syslog
            print('could NOT send syslog message to '+repr(self.logaddr))
            traceback.print_exc()

        self.traffic[1] += dnsize  # udp traffic
        return 0


    def comm(self): # do this regularly, blocks for the time of socket timeout!
        ''' Communicates with monitoring server, listens to return cmd and setup key:value and sends waiting data. '''
        self.ts = int(round(time.time(),0)) # current time
        self.unsent() # delete too old records, dump buffer also if became empty!
        udpgot = self.udpread() # check for incoming udp data. FIXME: direct ack around buffer??
        self.buff2server() # send away. the ack for this is available on next comm() hopefully
        return udpgot



class TCPchannel(UDPchannel): # used this parent to share self.syslog()
    ''' Communication via TCP (pull, push, calendar)  '''

    def __init__(self, id = '000000000000', supporthost = 'www.itvilla.ee', directory = '/support/pyapp/', uploader='/upload.php', base64string='cHlhcHA6QkVMYXVwb2E='):
        self.supporthost = supporthost
        self.uploader = uploader
        self.base64string = base64string
        self.traffic = [0,0] # TCP bytes in, out
        self.setID(id)
        self.directory = directory
        self.ts_cal = time.time()
        self.conn = sqlite3.connect(':memory:') # for calendar table
        self.makecalendar()


    def setID(self, invar):
        ''' Set the host id '''
        self.host_id = invar


    def getID(self):
        '''returns server ip for this instance '''
        return self.host_id


    def get_traffic(self): # TCP traffic counter
        return self.traffic # tuple in, out


    def set_traffic(self, bytes_in = None, bytes_out = None): # set TCP traffic counters (it is possible to update only one of them as well)
        ''' Restores TCP traffic counter [in, out] '''
        if bytes_in != None:
            if not bytes_in < 0:
                self.traffic[0] = bytes_in
                log.debug('set bytes_in to '+str(bytes_in))
            else:
                log.warning('invalid bytes_in '+str(bytes_in))

        if bytes_out != None:
            if not bytes_out < 0:
                self.traffic[1] = bytes_out
                log.debug('set bytes_out to '+str(bytes_in))
            else:
                print('invalid bytes_out',bytes_out)
                log.warning('invalid bytes_out '+str(bytes_in))

    def get_ts_cal(self): # last time calendar was accessed
        return int(round(self.ts_cal))



    def push(self, filename): # send (gzipped) file to supporthost
        ''' push file filename to supporthost directory using uploader and base64string (for basic auth) '''
        if os.path.isfile(filename):
            pass
        else:
            msg='push: found no file '+filename
            log.warning(msg)
            return 2 # no such file

        if '.gz' in filename or '.tgz' in filename: # packed already
            pass
        else: # lets unpack too
            f_in = open(filename, 'rb')
            f_out = gzip.open(filename+'.gz', 'wb')
            f_out.writelines(f_in)
            f_out.close()
            f_in.close()
            filename = filename+'.gz' # new filename to send
            dnsize=os.stat(filename)[6] # file size to be sent
            msg='the file was gzipped to '+filename+' with size '+str(dnsize) # the original file is kept!
            print(msg)
            #udp.syslog(msg)

        try:
            r = requests.post('http://'+self.supporthost+self.uploader,
                                files={'file': open(filename, 'rb')},
                                headers={'Authorization': 'Basic '+self.base64string},
                                data={'mac': self.directory+self.host_id+'/'}
                             )
            print('post response:',r.text) # nothing?
            msg='file '+filename+' with size '+str(dnsize)+' sent to '+self.directory+self.host_id+'/'
            #udp.syslog(msg)
            print(msg)
            self.traffic[1] += dnsize
            return 0

        except:
            msg='the file '+filename+' was NOT sent to '+self.directory+self.host_id+'/ '+str(sys.exc_info()[1])
            #udp.syslog(msg)
            print(msg)
            #traceback.print_exc()
            return 1




    def pull(self, filename, filesize, start=0):
        ''' Retrieves file from support server via http get, uncompressing
            too if filename contains .gz or tgz and succesfully retrieved.
            Parameter start=0 normally, higher with resume.
        '''
        oksofar=1 # success flag
        filename2='' # for uncompressed from the downloaded file
        filepart=filename+'.part' # temporary, to be renamed to filename when complete
        filebak=filename+'.bak'
        dnsize=0 # size of downloaded file
        if start>filesize:
            msg='pull parameters: file '+filename+' start '+str(start)+' above filesize '+str(filesize)
            log.debug(msg)
            #udp.syslog(msg)
            return 99 # illegal parameters or file bigger than stated during download resume

        req = 'http://'+self.supporthost+self.directory+self.host_id+'/'+filename
        pullheaders={'Range': 'bytes=%s-' % (start)} # with requests

        msg='trying '+req+' from byte '+str(start)+' using '+repr(pullheaders)
        log.info(msg)
        #udp.syslog(msg)
        try:
            response = requests.get(req, headers=pullheaders) # with python3
            output = open(filepart,'wb')
            output.write(response.content)
            output.close()
        except:
            msg='pull: partial or failed download of temporary file '+filepart+' '+str(sys.exc_info()[1])
            log.warning(msg)
            #udp.syslog(msg)
            #traceback.print_exc()

        try:
            dnsize=os.stat(filepart)[6]  # int(float(subexec('ls -l '+filename,1).split(' ')[4]))
        except:
            msg='pull: got no size for file '+os.getcwd()+'/'+filepart+' '+str(sys.exc_info()[1])
            print(msg)
            #udp.syslog(msg)
            #traceback.print_exc()
            oksofar=0

        if dnsize == filesize: # ok
            msg='pull: file '+filename+' download OK, size '+str(dnsize)
            print(msg)
            #udp.syslog(msg)

            try:
                os.rename(filename, filebak) # keep the previous version if exists
                #msg='renamed '+filename+' to '+filebak
            except:
                #traceback.print_exc()
                msg='FAILED to rename '+filename+' to '+filebak+' '+str(sys.exc_info()[1])
                print(msg)
                #udp.syslog(msg)
                oksofar=0


            try:
                os.rename(filepart, filename) #rename filepart to filename2
                #msg='renamed '+filepart+' to '+filename
            except:
                msg='FAILED to rename '+filepart+' to '+filename+' '+str(sys.exc_info()[1])
                print(msg)
                #udp.syslog(msg)
                oksofar=0
                #traceback.print_exc()

            if oksofar == 0: # trouble, exit
                self.traffic[0] += dnsize
                return 1

            if '.gz' in filename: # lets unpack too
                filename2=filename.replace('.gz','')
                try:
                    os.rename(filename2, filename2+'.bak') # keep the previous versioon if exists
                except:
                    #traceback.print_exc()
                    pass

                try:
                    f = gzip.open(filename,'rb')
                    output = open(filename2,'wb')
                    output.write(f.read());
                    output.close() # file with filename2 created
                    msg='pull: gz file '+filename+' unzipped to '+filename2+', previous file kept as '+filebak
                    log.warning(msg)
                except:
                    os.rename(filename2+'.bak', filename2) # restore the previous versioon if unzip failed
                    msg='pull: file '+filename+' unzipping failure, previous file '+filename2+' restored. '+str(sys.exc_info()[1])
                    #traceback.print_exc()
                    log.info(msg)
                    #udp.syslog(msg)
                    self.traffic[0] += dnsize
                    return 1

            if '.tgz' in filename: # possibly contains a directory
                try:
                    f = tarfile.open(filename,'r')
                    f.extractall() # extract all into the current directory
                    f.close()
                    msg='pull: tgz file '+filename+' successfully unpacked'
                    log.info(msg)
                    #udp.syslog(msg)
                except:
                    msg='pull: tgz file '+filename+' unpacking failure! '+str(sys.exc_info()[1])
                    #traceback.print_exc()
                    log.warning(msg)
                    #udp.syslog(msg)
                    self.traffic[0] += dnsize
                    return 1

            # temporarely switching off this chmod feature, failing!!
            #if '.py' in filename2 or '.sh' in filename2: # make it executable, only works with gzipped files!
            #    try:
            #        st = os.stat('filename2')
            #        os.chmod(filename2, st.st_mode | stat.S_IEXEC) # add +x for the owner
            #        msg='made the pulled file executable'
            #        print(msg)
              #      syslog(msg)
             #       return 0
            #    except:
            #        msg='FAILED to make pulled file executable!'
            #        print(msg)
            ##        syslog(msg)
            #        traceback.print_exc()
            #        return 99
            self.traffic[0] += dnsize
            return 0

        else:
            if dnsize<filesize:
                msg='pull: file '+filename+' received partially with size '+str(dnsize)
                log.warning(msg)
                #udp.syslog(msg)
                self.traffic[0] += dnsize
                return 1 # next try will continue
            else:
                msg='pull: file '+filename+' received larger than unexpected, in size '+str(dnsize)
                log.warning(msg)
                #udp.syslog(msg)
                self.traffic[0] += dnsize
                return 99


    def makecalendar(self, table='calendar'): # creates  buffer table in memory for calendar events
        Cmd='drop table if exists '+table
        sql="CREATE TABLE "+table+"(title,timestamp,value);CREATE INDEX ts_calendar on "+table+"(timestamp);" # semicolon needed for NPE for some reason!
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.executescript(sql) # read table into database
            self.conn.commit()
            msg='successfully (re)created table '+table
            return 0
        except:
            msg='sqlread: '+str(sys.exc_info()[1])
            print(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1


    def get_calendar(self, id, days = 3): # query to SUPPORTHOST, returning txt. started by cmd:GCAL too for testing
        ''' google calendar events via monitoring server '''
        # example:   http://www.itvilla.ee/cgi-bin/gcal.cgi?mac=000101000001&days=10
        self.ts_cal=time.time() # calendar access timestamp
        cur=self.conn.cursor()
        req = 'http://www.itvilla.ee/cgi-bin/gcal.cgi?mac='+id+'&days='+str(days)+'&format=json'
        headers={'Authorization': 'Basic YmFyaXg6Y29udHJvbGxlcg=='} # Base64$="YmFyaXg6Y29udHJvbGxlcg==" ' barix:controller
        msg='starting gcal query '+req
        print(msg) # debug
        try:
            response = requests.get(req, headers = headers)
        except:
            msg='gcal query '+req+' failed!'
            traceback.print_exc()
            print(msg)
            #udp.syslog(msg)
            return 1 # kui ei saa gcal yhendust, siis lopetab ja vana ei havita!

        try:
            events = eval(response.content) # string to list
        except:
            msg='getting calendar events failed for host id '+id
            print(msg)
            #udp.syslog(msg)
            traceback.print_exc() # debug
            return 1 # kui ei saa normaalseid syndmusi, siis ka lopetab

        #print(repr(events)) # debug
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd="delete from calendar"
            self.conn.execute(Cmd)
            for event in events:
                #print('event',event) # debug
                columns=str(list(event.keys())).replace('[','(').replace(']',')')
                values=str(list(event.values())).replace('[','(').replace(']',')')
                #columns=str(list(event.keys())).replace('{','(').replace('}',')')
                #values=str(list(event.values())).replace('{','(').replace('}',')')
                Cmd = "insert into calendar"+columns+" values"+values
                print(Cmd) # debug
                self.conn.execute(Cmd)
            self.conn.commit()
            msg='calendar table updated'
            log.warning(msg)
            #udp.syslog(msg) # FIXME - syslog via UDPchannel does not work. syslog() is found, but not it's logaddr?
            #self.syslog(msg) # common parent UDP TCP channel
            return 0
        except:
            msg='delete + insert to calendar table failed!'
            log.warning(msg)
            #udp.syslog(msg)
            log.warning('logaddr in tcp',self.logaddr)
            #self.syslog(msg,logaddr=self.logaddr) # class UDPchannel is parent to TCPchannel
            #UDPchannel.syslog(msg)
            traceback.print_exc() # debug
            return 1 # kui insert ei onnestu, siis ka delete ei toimu


    def chk_calevents(self, title = ''): # set a new setpoint if found in table calendar (sharing database connection with setup)
        ''' Obsolete, functionality moved to gcal.py '''
        ts=time.time()
        cur=self.conn.cursor()
        value='' # local string value
        if title == '':
            return None

        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            conn.execute(Cmd)
            Cmd="select value from calendar where title='"+title+"' and timestamp+0<"+str(ts)+" order by timestamp asc" # find the last passed event value
            cur.execute(Cmd)
            for row in cur:
                value=row[0] # overwrite with the last value before now
                #print(Cmd4,', value',value) # debug. voib olla mitu rida, viimane value jaab iga title jaoks kehtima
            self.conn.commit()
            return value # last one for given title becomes effective. can be empty string too, then use default value for setpoint related to title
        except:
            traceback.print_exc()
            return None

