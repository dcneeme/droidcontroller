# send and receive monitoring and control messages to from UniSCADA monitoring system
# udp kuulamiseks thread?
# neeme

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
#karlas kasutab sk asemel nime cu!
#OSTYPE = os.environ['OSTYPE']



class UDPchannel():
    ''' Sends away the messages, combining different key:value pairs and adding host id and time. Listens for incoming commands and setup data.
    Several UDPchannel instances can be used in parallel, to talk with different servers.

    Used by sqlgeneral.py

    '''

    def __init__(self, id = '000000000000', ip = '127.0.0.1', port = 44445, receive_timeout = 0.1, retrysend_delay = 5, loghost = '0.0.0.0', logport=514): # delays in seconds
        #from droidcontroller.connstate import ConnState
        from droidcontroller.statekeeper import StateKeeper
        self.sk = StateKeeper(off_tout=300, on_tout=0) # conn state with up/down times

        try:
            from droidcontroller.gpio_led import GPIOLED
            self.led = GPIOLED() # led alarm and conn
        except:
            log.warning('GPIOLED not imported')

        self.host_id = id
        self.ip = ip
        self.port = port
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

        print('init: created uniscada and syslog connections to '+ip+':'+str(port)+' and '+loghost+':'+str(logport))
        self.table = 'buff2server' # can be anything, not accessible to other objects WHY? would be useful to know the queue length...
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
        self.setIP(self.ip)
        self.setLogIP(self.loghost)


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

    def getIP(self):
        ''' returns server ip for this instance '''
        return self.ip

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


    def get_ts_udpgot(self):  #get ts of last ack from monitoring server
        return self.ts_udpgot


    def makebuff(self): # drops buffer table and creates
        Cmd='drop table if exists '+self.table
        sql="CREATE TABLE "+self.table+"(sta_reg,status NUMERIC,val_reg,value,ts_created NUMERIC,inum NUMERIC,ts_tried NUMERIC);" # semicolon needed for NPE for some reason!
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.executescript(sql) # read table into database
            self.conn.commit()
            msg='sqlread: successfully (re)created table '+self.table
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
        ''' Adds service components into buffer table to be sent as a string message
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
                    print(delcount,'services lines waiting ack for',10*self.retrysend_delay,' s to be deleted')
                    Cmd="delete from "+self.table+" where ts_created+0+"+str(10*self.retrysend_delay)+"<"+str(self.ts) # +" limit 10" # limit lisatud 23.03.2014 aga miks?
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



    def buff2server(self): # send the buffer content
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
                    sendstring += val_reg+":"+str(value)+"\n"
                if sta_reg != '':
                    sendstring += sta_reg+":"+str(status)+"\n"

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
        ''' Sends UDP data immediately, adding self.inum if >0. '''
        if sendstring == '': # nothing to send
            print('udpsend(): nothing to send!')
            return 1

        self.ts = round(time.time(),1)
        sendstring += "id:"+self.host_id+"\n" # loodame, et ts_created on enam-vahem yhine neil teenustel...
        if self.inum > 0: # "in:inum" to be added
            sendstring += "in:"+str(self.inum)+","+str(round(self.ts))+"\n"

        self.traffic[1]=self.traffic[1]+len(sendstring) # adding to the outgoing UDP byte counter

        try:
            self.led.commLED(0) # off, blinking shows sending and time to ack
        except:
            pass

        try:
            sendlen=self.UDPSock.sendto(sendstring.encode('utf-8'),self.saddr) # tagastab saadetud baitide arvu
            self.traffic[1]=self.traffic[1]+sendlen # traffic counter udp out
            msg='=== sent ' +str(sendlen)+' bytes to '+str(repr(self.saddr))+' '+sendstring.replace('\n',' ')   # show as one line
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

            try:
                self.led.alarmLED(1) # send failure
            except:
                pass

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


    def udpread(self):
        ''' Checks received data for monitoring server to see if the data contains key "in",
            then deletes the rows with this inum in the sql table.
            If the received datagram contains more data, these key:value pairs are
            returned as dictionary.
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
            #print('<= '+data.replace('\n', ' ')) # also to syslog (communication with server only)

            if (int(raddr[1]) < 1 or int(raddr[1]) > 65536):
                msg='illegal_ source port '+str(raddr[1])+' in the message received from '+raddr[0]
                print(msg)
                #syslog(msg)

            if raddr[0] != self.ip:
                msg='illegal sender '+str(raddr[0])+' of message: '+data+' at '+str(int(ts))  # ignore the data received!
                print(msg)
                #syslog(msg)
                data='' # data destroy

            if "id:" in data: # first check based on host id existence in the received message, must exist to be valid message!
                in_id=data[data.find("id:")+3:].splitlines()[0]
                if in_id != self.host_id:
                    print("invalid id "+in_id+" in server message from ", addr[0]) # this is not for us!
                    data=''
                    return data # error condition, traffic counter was still increased
                else:
                    self.ts_udpgot=self.ts # timestamp of last udp received

                try:
                    self.led.commLED(1) # data from server, comm OK
                except:
                    pass
                self.sk.up()

                lines=data.splitlines() # split message into key:value lines
                for i in range(len(lines)): # looking into every member of incoming message
                    if ":" in lines[i]:
                        #print "   "+lines[i]
                        line = lines[i].split(':')
                        line = lines[i].split(':')
                        sregister = line[0] # setup reg name
                        svalue = line[1] # setup reg value
                        #print('received key:value',sregister,svalue) # debug
                        if sregister != 'in' and sregister != 'id': # may be setup or command (cmd:)
                            msg='got setup/cmd reg:val '+sregister+':'+svalue  # need to reply in order to avoid retransmits of the command(s)
                            print(msg)
                            data_dict.update({ sregister : svalue }) # in and idf are not included in dict
                            #udp.syslog(msg) # cannot use udp here
                            #sendstring += sregister+":"+svalue+"\n"  # add to the answer - better to answer with real values immediately after change

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

                        if len(sendstring) > 0:
                            self.udpsend(sendstring) # send the response right away to avoid multiple retransmits
                            # this answers to the server but does not update the setup or service table yet!

                return data_dict # possible key:value pairs here for setup change or commands. returns {} for just ack with no cmd
        else:
            return None


    def syslog(self, msg,logaddr=()): # sending out syslog message to self.logaddr.
        msg=msg+"\n" # add newline to the end
        #print('syslog send to',self.logaddr) # debug
        dnsize=0
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
        self.ts = round(time.time(),1) # timestamp
        self.unsent() # delete old records
        udpgot = self.udpread() # check for incoming udp data
        # parse_udp()
        self.buff2server() # send away. the ack for this is available on next comm() hopefully
        return udpgot



class TCPchannel(UDPchannel): # used this parent to share self.syslog()
    ''' Communication via TCP (pull, push, calendar)  '''

    def __init__(self, id = '000000000000', supporthost = 'www.itvilla.ee', directory = '/support/pyapp/', uploader='/upload.php', base64string='cHlhcHA6QkVMYXVwb2E='):
        self.supporthost = supporthost
        self.uploader=uploader
        self.base64string=base64string
        self.traffic = [0,0] # TCP bytes in, out
        self.setID(id)
        self.directory=directory
        self.ts_cal=time.time()
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
                log.info('set bytes_in to '+str(bytes_in))
            else:
                log.warning('invalid bytes_in '+str(bytes_in))

        if bytes_out != None:
            if not bytes_out < 0:
                self.traffic[1] = bytes_out
                log.info('set bytes_out to '+str(bytes_in))
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
            print(msg)
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
            print(msg)
            #udp.syslog(msg)
            return 99 # illegal parameters or file bigger than stated during download resume

        req = 'http://'+self.supporthost+self.directory+self.host_id+'/'+filename
        pullheaders={'Range': 'bytes=%s-' % (start)} # with requests

        msg='trying '+req+' from byte '+str(start)+' using '+repr(pullheaders)
        print(msg)
        #udp.syslog(msg)
        try:
            response = requests.get(req, headers=pullheaders) # with python3
            output = open(filepart,'wb')
            output.write(response.content)
            output.close()
        except:
            msg='pull: partial or failed download of temporary file '+filepart+' '+str(sys.exc_info()[1])
            print(msg)
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
                    print(msg)
                except:
                    os.rename(filename2+'.bak', filename2) # restore the previous versioon if unzip failed
                    msg='pull: file '+filename+' unzipping failure, previous file '+filename2+' restored. '+str(sys.exc_info()[1])
                    #traceback.print_exc()
                    print(msg)
                    #udp.syslog(msg)
                    self.traffic[0] += dnsize
                    return 1

            if '.tgz' in filename: # possibly contains a directory
                try:
                    f = tarfile.open(filename,'r')
                    f.extractall() # extract all into the current directory
                    f.close()
                    msg='pull: tgz file '+filename+' successfully unpacked'
                    print(msg)
                    #udp.syslog(msg)
                except:
                    msg='pull: tgz file '+filename+' unpacking failure! '+str(sys.exc_info()[1])
                    #traceback.print_exc()
                    print(msg)
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
                print(msg)
                #udp.syslog(msg)
                self.traffic[0] += dnsize
                return 1 # next try will continue
            else:
                msg='pull: file '+filename+' received larger than unexpected, in size '+str(dnsize)
                print(msg)
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
            print(msg)
            #udp.syslog(msg) # FIXME - syslog via UDPchannel does not work. syslog() is found, but not it's logaddr?
            #self.syslog(msg) # common parent UDP TCP channel
            return 0
        except:
            msg='delete + insert to calendar table failed!'
            print(msg)
            #udp.syslog(msg)
            print('logaddr in tcp',self.logaddr)
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

