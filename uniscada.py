# send and receive monitoring and control messages to from UniSCADA monitoring system
# udp kuulamiseks thread?
# neeme 01.04.2014
# 02.04.2014  intial success. no external sql needed.
# 03.04.2013 UDPsock moved into UDPchannel __init__
# 06.04.2014 send() takes tuple now
# 07.04.2014 send() tuple members to string or int

import time, datetime
import sqlite3
import traceback
from socket import *
import sys

#UDPSock = socket(AF_INET,SOCK_DGRAM)


class UDPchannel: # for one host only. if using 2 servers, create separate UDPchannels but a single MessageBuffer.. probably not necessary, can be separate too!
    ''' Sends away the messages, combining different key:value pairs and adding host id and time. Listens for incoming commands and setup data.
    Several UDPchannel instances can be used in parallel, to talk with different servers.

    Usage example:
    from uniscada import *
    f=UDPchannel(ip='46.183.73.35', id='000000000000', port=44445)
    f.send('BRS',0,'','') # store to buffer
    f.buff2server() # sends to server and resends earlier messages if any w.o ack
    f.udpread() # possible ack or other data from the server

    for regular send/receive use
    f.comm() # returns possible data as key:value dictionary

    '''

    def __init__(self, id = '000000000000', ip = '127.0.0.1', port = 44445, receive_timeout = 0.1, retrysend_delay = 5): # delays in seconds
        self.host_id = id
        self.ip = ip
        self.port = port
        self.traffic = [0,0] # udp bytes in out
        self.UDPSock = socket(AF_INET,SOCK_DGRAM)
        self.UDPSock.settimeout(receive_timeout)
        self.retrysend_delay = retrysend_delay
        self.saddr = (ip,port) # monitoring server
        self.inum = 0 # sent message counter
        print('init: created uniscada connection')
        self.table = 'buff2server' # can be anything, not accessible to other objects
        self.Initialize()

    def Initialize(self):
        ''' initialize time/related variables and create buffer database with one table in memory '''
        self.ts = round(time.time(),1)
        #self.ts_inum = self.ts # inum increase time, is it used at all? NO!
        self.ts_unsent = self.ts # last unsent chk
        self.ts_udpsent=self.ts
        self.ts_udpgot=self.ts
        self.conn = sqlite3.connect(':memory:') 
        #self.cur=self.conn.cursor() # cursors to read data from tables / cursor can be local
        self.makebuff() # create buffer table for unsent messages


    def setIP(self, invar):
        ''' Set the monitoring server ip address '''
        self.ip = invar


    def setPort(self, invar):
        ''' Set the monitoring server UDP port '''
        self.port = invar

        
    def setID(self, invar):
        ''' Set the host id '''
        self.id = invar
        
    
    def setRetryDelay(self, invar):
        ''' Set the monitoring server UDP port '''
        self.retrysend_delay = invar

    
    def get_ts(self):
        '''returns timestamps for last send trial and successful receive '''
        return self.ts_udpsent, self.ts_udpgot
        

    def get_traffic(self):
        return self.traffic # tuple in, out
        

    def set_traffic(self, bytes_in = None, bytes_out = None): # set traffic counters (it is possible to update only one of them as well)
        if bytes_in != None:
            if not bytes_in < 0:
                self.traffic[0] = bytes_in
            else:
                print('invalid bytes_in',bytes_in)

        if bytes_out != None:
            if not bytes_out < 0:
                self.traffic[1] = bytes_out
            else:
                print('invalid bytes_out',bytes_out)
                

    def set_inum(self,inum = 0): # set message counter
        self.inum=inum
        

    def get_inum(self):  #get message counter
        return self.inum        
        
        
    def makebuff(self): # drops table and creates
        Cmd='drop table if exists '+self.table
        sql="CREATE TABLE "+self.table+"(sta_reg,status NUMERIC,val_reg,value,ts_created NUMERIC,inum NUMERIC,ts_tried NUMERIC);" # semicolon needed for NPE for some reason!
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.executescript(sql) # read table into database
            self.conn.commit()
            msg='sqlread: successfully (re)created table '+self.table
            #print(msg)
            #syslog(msg)
            #time.sleep(0.5)
            return 0
        except:
            msg='sqlread: '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1


    def delete_buffer(self): # empty buffer
        Cmd='delete from '+self.table
        try:
            self.conn.execute(Cmd)
            self.conn.commit()
            print('buffer content deleted')
        except:
            traceback.print_exc()
            


        

    def send(self, servicetuple): # store service components to buffer for send and resend
        ''' adds service components into buffer to be sent as a string message
            the components are sta_reg = '', status = 0, val_reg = '', value = ''
        '''
        try:
            sta_reg=str(servicetuple[0])
            status=int(servicetuple[1])
            val_reg=str(servicetuple[2])
            value=str(servicetuple[3])
            self.ts = round(time.time(),1)
            Cmd="INSERT into "+self.table+" values('"+sta_reg+"',"+str(status)+",'"+val_reg+"','"+value+"',"+str(self.ts)+",0,0)" # inum and ts_tried left initially empty
            #print(Cmd) # debug
            self.conn.execute(Cmd)
            return 0
        except:
            msg='FAILED to write svc into buffer'
            #syslog(msg) # incl syslog
            print(msg)
            traceback.print_exc()
            return 1



    def unsent(self):  # delete unsent for too long messages - otherwise the udp messages will contain older key:value duplicates!
        ''' Counts the non-acknowledged messages and removes older than 3 times retrysend_delay '''
        if self.ts - self.ts_unsent < self.retrysend_delay / 2: # no need to recheck too early
            return 0
        self.ts = round(time.time(),1)
        self.ts_unsent = self.ts
        mintscreated=0
        maxtscreated=0
        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION"  # buff2server
            self.conn.execute(Cmd)
            Cmd="SELECT count(sta_reg),min(ts_created),max(ts_created) from "+self.table+" where ts_created+0+"+str(3*self.retrysend_delay)+"<"+str(self.ts) # yle 3x regular notif
            cur = self.conn.cursor()
            cur.execute(Cmd)
            for rida in cur: # only one line for count if any at all
                delcount=rida[0] # int
                if delcount>0: # stalled services found
                    #print repr(rida) # debug
                    mintscreated=rida[1]
                    maxtscreated=rida[2]
                    print(delcount,'services lines waiting ack for',3*self.retrysend_delay,' s to be deleted')
                    Cmd="delete from "+self.table+" where ts_created+0+"+str(3*self.retrysend_delay)+"<"+str(self.ts) # +" limit 10" # limit lisatud 23.03.2014
                    self.conn.execute(Cmd)

            Cmd="SELECT count(sta_reg),min(ts_created),max(ts_created) from "+self.table
            cur.execute(Cmd)
            for rida in cur: # only one line for count if any at all
                delcount=rida[0] # int
            if delcount>50: # delete all!
                Cmd="delete from "+self.table
                self.conn.execute(Cmd)
                msg='deleted '+str(delcount)+' unsent messages from '+self.table+'!'
                print(msg)
                #syslog(msg)
            self.conn.commit() # buff2server transaction end
            return delcount # 0
            #time.sleep(1) # prooviks
        except:
            msg='problem with unsent, '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            #sys.stdout.flush()
            time.sleep(1)
            return 1

        #unsent() end



    def buff2server(self): # try to send the buffer content
        ''' UDP monitoring message creation and sending (using udpsend)
            based on already existing buff2server data, does the retransmits too if needed.
            buff2server rows successfully send will be deleted by udpread() based on in: contained in the received  message
        '''
        timetoretry = 0 # local
        ts_created = 0 # local
        svc_count = 0 # local
        sendstring = ''
        timetoretry=int(self.ts-self.retrysend_delay) # send again services older than that
        Cmd = "BEGIN IMMEDIATE TRANSACTION" # buff2server
        try:
            self.conn.execute(Cmd)
        except:
            print('could not start transaction on self.conn, '+self.table)
            traceback.print_exc()

        Cmd = "SELECT * from "+self.table+" where ts_tried=0 or (ts_tried+0>1358756016 and ts_tried+0<"+str(self.ts)+"+0-"+str(timetoretry)+") AND status+0 != 3 order by ts_created asc limit 30"
        try:
            cur = self.conn.cursor()
            cur.execute(Cmd)
            for srow in cur:
                #print(repr(srow)) # debug, what will be sent
                if svc_count == 0: # on first row only increase the inum!
                    self.inum=self.inum+1 # increase the message number / WHY HERE? ACK WILL NOT DELETE THE ROWS!
                    if self.inum > 65535:
                        self.inum = 1 # avoid zero for sending
                        #self.ts_inum=self.ts # time to set new inum value

                svc_count=svc_count+1
                sta_reg=srow[0]
                status=srow[1]
                val_reg=srow[2]
                value=srow[3]
                ts_created=srow[4]

                if val_reg != '':
                    sendstring=sendstring+val_reg+":"+str(value)+"\n"
                if sta_reg != '':
                    sendstring=sendstring+sta_reg+":"+str(status)+"\n"

                Cmd="update "+self.table+" set ts_tried="+str(int(self.ts))+",inum="+str(self.inum)+" where sta_reg='"+sta_reg+"' and status="+str(status)+" and ts_created="+str(ts_created)
                #print "update Cmd=",Cmd # debug
                self.conn.execute(Cmd)

            if svc_count>0: # there is something (changed services) to be sent!
                #print(svc_count,"services to send using inum",self.inum) # debug
                self.udpsend(sendstring) # sending away

            Cmd="SELECT count(inum) from "+self.table  # unsent service count in buffer
            cur.execute(Cmd) #
            for srow in cur:
                svc_count2=int(srow[0]) # total number of unsent messages

            if svc_count2>30: # do not complain below 30
                print(svc_count2,"SERVICES IN BUFFER waiting for ack from monitoring server")

        except: # buff2server read unsuccessful. unlikely...
            msg='problem with '+self.table+' read '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            #sys.stdout.flush()
            time.sleep(1)
            return 1

        self.conn.commit() # buff2server transaction end
        return 0
    # udpmessage() end
    # #################



    def udpsend(self, sendstring = ''): # actual udp sending, no resend. give message as parameter. used by buff2server too.
        ''' sends data immediately  without sql buffer data in between! no inum inclusion! '''
        if sendstring == '': # nothing to send
            print('udpsend(): nothing to send!')
            return 1


        sendstring="id:"+self.host_id+"\n"+sendstring # loodame, et ts_created on enam-vahem yhine neil teenustel...
        if self.inum > 0: # "in:inum" to be added
            sendstring="in:"+str(self.inum)+","+str(round(self.ts))+"\n"+sendstring

        self.traffic[1]=self.traffic[1]+len(sendstring) # adding to the outgoing UDP byte counter

        try:
            sendlen=self.UDPSock.sendto(sendstring.encode('utf-8'),self.saddr) # tagastab saadetud baitide arvu
            self.traffic[1]=self.traffic[1]+sendlen # traffic counter udp out
            msg='sent to '+str(repr(self.saddr))+' '+sendstring.replace('\n',' ')   # show as one line
            print(msg)
            #syslog(msg)
            sendstring=''
            self.ts_udpsent=self.ts # last successful udp send
            return sendlen
        except:
            msg='udp send failure in udpsend() to saddr '+repr(self.saddr)+', lasting s '+str(int(self.ts - self.ts_udpsent)) # cannot send, this means problem with connectivity
            #syslog(msg)
            print(msg)
            traceback.print_exc()
            return None


    def read_buffer(self):
        ''' reads the content of the buffer, debugging needs only '''
        Cmd ="SELECT * from "+self.table
        cur = self.conn.cursor()
        cur.execute(Cmd)
        for row in cur:
            print(repr(row))


    def udpread(self):
        ''' tries to receive data from monitoring server and IF the data contains key "in",
        then deletes the rows with this inum in the sql table and returns received data
        '''
        data=''
        data_dict={} # possible setup and commands
        sendstring = ''

        try: # if anything is comes into udp buffer before timepout
            buf=1024
            rdata,raddr = self.UDPSock.recvfrom(buf)
            data=rdata.decode("utf-8") # python3 related need due to mac in hex
        except:
            #print('no new udp data received') # debug
            #traceback.print_exc()
            return None

        if len(data) > 0: # something arrived
            #print('got from monitoring server',repr(raddr),repr(data)) # debug
            self.traffic[0]=self.traffic[0]+len(data) # adding top the incoming UDP byte counter
            print('<= '+data.replace('\n', ' ')) # also to syslog (communication with server only)

            if (int(raddr[1]) < 1 or int(raddr[1]) > 65536):
                msg='illegal source port '+str(raddr[1])+' in the message received from '+raddr[0]
                print(msg)
                syslog(msg)

            if raddr[0] != self.ip:
                msg='illegal sender '+str(raddr[0])+' of message: '+data+' at '+str(int(ts))  # ignore the data received!
                print(msg)
                syslog(msg)
                data='' # data destroy

            if "id:" in data: # first check based on host id existence in thge received message, must exist to be valid message!
                in_id=data[data.find("id:")+3:].splitlines()[0]
                if in_id != self.host_id:
                    print("invalid id "+in_id+" in server message from ", addr[0]) # this is not for us!
                    data=''
                    return data # error condition, traffic counter was still increased
                else:
                    self.ts_udpgot=self.ts # timestamp of last udp received

            lines=data.splitlines() # split message into key:value lines
            for i in range(len(lines)): # looking into every member of incoming message
                if ":" in lines[i]:
                    #print "   "+lines[i]
                    line = lines[i].split(':')
                    sregister = line[0] # setup reg name
                    svalue = line[1] # setup reg value
                    #print('received key:value',sregister,svalue) # debug
                    if sregister != 'in' and sregister != 'id': # may be setup or command (cmd:)
                        msg='got setup/cmd reg:val '+sregister+':'+svalue  # need to reply in order to avoid retransmits of the command(s)
                        print(msg)
                        data_dict.update({ sregister : svalue })
                        #syslog(msg)
                        sendstring=sendstring+sregister+":"+svalue+"\n"  # add to the answer
                        self.udpsend(sendstring) # send the response right away to avoid multiple retransmits
                    else:
                        if sregister == "in": # one such a key in message
                            inumm=eval(data[data.find("in:")+3:].splitlines()[0].split(',')[0]) # loodaks integerit
                            if inumm >= 0 and inumm<65536:  # valid inum, response to message sent if 1...65535. datagram including "in:0" is a server initiated "fast communication" message
                                #print "found valid inum",inum,"in the incoming message " # temporary
                                msg='got ack '+str(inumm)+' in message: '+data.replace('\n',' ')
                                print(msg)
                                #syslog(msg)

                                Cmd="BEGIN IMMEDIATE TRANSACTION" # buff2server, to delete acknowledged rows from the buffer
                                self.conn.execute(Cmd) # buff2server ack transactioni algus, loeme ja kustutame saadetud read
                                Cmd="DELETE from "+self.table+" WHERE inum='"+str(inumm)+"'"  # deleting all rows where inum matches server ack
                                try:
                                    self.conn.execute(Cmd) # deleted
                                except:
                                    msg='problem with '+Cmd+'\n'+str(sys.exc_info()[1])
                                    print(msg)
                                    #syslog(msg)
                                    time.sleep(1)
                                self.conn.commit() # buff2server transaction end

        return data_dict # possible key:value pairs here for setup change or commands


    def comm(self): # do this regularly, blocks for the time of socket timeout!
        ''' Communicates with server, returns cmd and setup key:value'''
        self.ts = round(time.time(),1)
        self.unsent()
        udpgot = self.udpread() # check for incoming udp data
        self.buff2server() # the ack for this is available on next comm() hopefully
        return udpgot




