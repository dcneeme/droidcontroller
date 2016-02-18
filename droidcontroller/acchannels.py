# This Python file uses the following encoding: utf-8

from droidcontroller.sqlgeneral import * # SQLgeneral  / vaja ka time,mb, conn jne
s=SQLgeneral() # init sisse?
from droidcontroller.counter2power import *  # Counter2Power() as cp handles power calculation based on pulse count increments

import time
import logging
log = logging.getLogger(__name__)

class ACchannels(SQLgeneral): # handles aichannels and counters, modbus registers and sqlite tables
    ''' Access to io by modbus analogue register addresses (and also via services?). Modbus client must be opened before.
        Able to sync input and output channels and accept changes to service members by their sta_reg code.
        Channel configuration is defined in sql tables.
        Read and send only happen if enough time is passed from previous, chk readperiod, sendperiod!
    '''

    def __init__(self, msgbus=None, in_sql = 'aicochannels.sql', out_sql = 'aochannels.sql', readperiod = 10, sendperiod = 120):
        self.msgbus = msgbus
        self.setReadPeriod(readperiod)
        self.setSendPeriod(sendperiod)
        self.in_sql = in_sql.split('.')[0]
        self.out_sql = out_sql.split('.')[0]
        #self.s = SQLgeneral()
        self.cp = [] # possible counter2value calculation instances
        self.chg = 0 # possible need for immediate notification
        self.msg = ''  # to reduce repetitive messages
        log.info('ACchannels instance created, msgbus '+str(self.msgbus))
        self.Initialize()


    def setReadPeriod(self, invar):
        ''' Set the ai reading period in s, to execute sync if time from last read was earlier than period ago. '''
        self.readperiod = invar  # values considered as stalled after 10x self.readperiod

    def getReadPeriod(self):
        ''' Returns the ai reading period in s '''
        return self.readperiod  # values considered as stalled after 10x self.readperiod

    def setSendPeriod(self, invar):
        ''' Set the ai notification period s, to execute sync if time from last read was earlier than period ago '''
        self.sendperiod = invar

    def getSendPeriod(self):
        ''' Set the ai notification period s, executes sync if time from last read was earlier than period ago '''
        return self.sendperiod

    def sqlread(self, table):
        ''' Read the sql file into memory '''
        s.sqlread(table) #

    def Initialize(self): # before using this create s=SQLgeneral()
        ''' initialize delta t variables, create tables and modbus connection '''
        self.ts = int(round(time.time(),0))
        self.ts_read = self.ts # time of last read
        self.ts_send = self.ts-10 # allow counters restoring
        self.sqlread(self.in_sql) # read counters table
        self.sqlread(self.out_sql) # read aochannels if exist
        self.ask_counters() # ask server about the last known values of all counter related services (1024 in cfg)


    def ask_counters(self): # use on init, send ? to server
        ''' Queries last counter service values from the server '''
        Cmd = "select val_reg,max(cfg) from "+self.in_sql+" where (cfg+0 & 1024) group by val_reg" # counters only, to be asked and restored
        #print "Cmd=",Cmd
        cur = conn.cursor()
        cur.execute(Cmd) # getting services to be read and reported
        for row in cur: # possibly multivalue service members
            val_reg=row[0]
            sta_reg=val_reg[:-1]+'S' # status
            #cfg=int(row[1]) if row[1] != '' else 0
            udp.send([sta_reg,1,val_reg,'?']) # udp.udpsend(val_reg+':?\n') # ask via buffer only
        try:
            conn.commit()
            log.info('queried the last known values for counter services')
        except:
            log.warning('FAILED to create a query about counter values')
        return 0


    def parse_udp(self,data_dict): # search for setup or set counter values
        ''' Channels setup change based on message from monitoring server. Only accepts keys ending with W in data_dict '''
        cur = conn.cursor()
        setup_changed = 0 # flag general setup change, data to be dumped into sql file
        msg = ''
        mval = ''
        res = 0
        member = 0
        if data_dict == {} or data_dict == '' or data_dict == None:
            log.warning('ac: nothing to parse in',data_dict)
            return 0
        log.debug('parsing for possible match key:value data ',data_dict) # debug
        for key in data_dict: # process per key:value
            found = 0
            if key[-1] == 'W': # must end with W to be multivalue service containing setup values
                valmembers=data_dict[key].split(' ') # convert value to member list
                log.debug('number of members for '+str(key)+' is '+str(len(valmembers)))
                for valmember in range(len(valmembers)): # 0...N-1
                    Cmd = "select mba,regadd,val_reg,member,value,regtype,wcount,mbi,x2,y2,cfg from "+self.in_sql+" where val_reg='"+key+"' and member='"+str(valmember+1)+"'"
                    #print(Cmd) # debug
                    cur.execute(Cmd)
                    conn.commit()
                    for row in cur: # single member
                        found += 1
                        log.debug('srow:'+str(row)) # debug
                        sqlvalue = int(row[4]) if row[4] != '' else 0 # eval(row[4]) if row[4] != '' else 0 #
                        cfg = int(row[10]) if row[10] != '' else 0
                        #val_reg = row[2] # pole vaja

                        try:
                            value=eval(valmembers[valmember])
                        except:
                            value = sqlvalue # no change!
                            #log.warning('invalid value in message from server for key '+key)

                        regtype=row[5] # 'h' 'i' 's!'

                        if sqlvalue != value and ((regtype == 'h' and value == 0 or value > sqlvalue) or (regtype == 's!')) and (cfg&2048) == 0:
                            # replace actual counters only if bigger than existing or zero and not 1wire channel, no limits for setup type 's!'
                            member = valmember+1

                            log.debug('going to replace '+key+' member '+str(member)+' existing value '+str(sqlvalue)+' with '+str(value)) # debug
                            # faster to use physical data instead of svc. also clear counter2power buffer if cp[] exsists!

                            if regtype == 's!': # setup row, external modif allowed (!)
                                if (row[0] == '' and row[1] == ''): # mba, regadd
                                    if self.set_aivalue(str(key),member,value) == 0: # set setup value in sql table
                                        msg = 'setup changed for key '+str(key)+', member '+str(member)+' to value '+str(value)
                                        setup_changed=1
                                        log.info(msg)
                                        #udp.syslog(msg)
                                    else:
                                        msg = 'svc member setting problem for key '+str(key)+', member '+str(member)+' to value '+str(value)
                                        log.warning(msg)
                                        #udp.syslog(msg)
                                        res += 1
                                else:
                                    msg = 'acchannels.udp_parse: setup value cannot have mba,regadd defined!'
                                    log.warning(msg)
                                    #udp.syslog(msg)
                                    res += 1
                            elif regtype == 'h': # holding register, probably counter
                                if (row[0] != '' and row[1] != ''): # mba,regadd probably valid
                                    mba = int(row[0]) if row[0] != '' else 0
                                    regadd = int(row[1]) if row[1] != '' else None
                                    wcount = int(row[6]) if row[6] != '' else 1
                                    mbi = int(row[7]) if row[7] != '' else None
                                    x2 = int(row[8]) if row[8] != '' else 0
                                    y2 = int(row[9]) if row[9] != '' else 0

                                    #if self.set_counter(val_reg=key, member=member,value=value, wcount=wcount) == 0: # faster to use physical data instead of svc
                                    if self.set_counter(mbi=mbi, mba=mba, regadd=regadd, value=value, wcount=wcount, x2=x2, y2=y2) == 0: # set counter
                                        #set_counter also cleared counter2power buffer if cp[] exsisted!
                                        msg = 'counter set for key '+key+', member '+str(member)+' to value '+str(value)
                                        log.debug(msg)
                                        #udp.syslog(msg)
                                    else:
                                        msg = 'member value setting problem for key '+key+', member '+str(member)+' to value '+str(value)
                                        log.warning(msg)
                                        #udp.syslog(msg)
                                        res += 1
                                else:
                                    msg = 'acchannels.udp_parse: holding register must have mba,regadd defined!'
                                    log.warning(msg)
                                    #udp.syslog(msg)
                                    res += 1
                        else: # skip
                            log.warning('SKIPPED restore for key '+key+' due to regtype '+regtype+', sqlvalue '+str(sqlvalue)+', value '+str(value))

            if found > 0:  # process status too
                self.make_svc(key,'') ### processing svc and notify about new counter value

        if setup_changed == 1:
            log.info('going to dump table '+self.in_sql)
            try:
                s.dump_table(self.in_sql)

            except:
                log.warning('FAILED to dump table '+self.in_sql)
                traceback.print_exc() # debug

        return res # kui setup_changed ==1, siis todo = varlist! aga kui samal ajal veel miski ootel?


    def set_counter(self, value = 0, **kwargs): # value, mba,regadd,mbi,val_reg,member   # one counter to be set. check wcount from counters table
        ''' Sets consecutive holding registers, wordlen 1 or 2 or -2 (must be defined in sql table in use).
            Usable for cumulative counter counting initialization, not for analogue output (use set_output for this).
            Must also clear counter2power instance buffer dictionary if cp[] instance exsists, to avoid unwanted spike in power calculation result!
        '''
        #val_reg=''  # arguments to use a subset of them
        #member=0
        #mba=0
        #mbi=0
        #regadd=0
        #wcount=0
        #value=value
        cur=conn.cursor()
        x2=0
        y2=0
        Cmd=''
        try: # is is mba or val_reg based addressing in use?
            mba = kwargs['mba']
            regadd = kwargs['regadd']
            mbi = kwargs['mbi']
            wcount = kwargs['wcount']
            x2 = kwargs['x2']
            y2 = kwargs['y2']
            # if this fails, svc_name and member must be given as parameters
        except:
            try:
                val_reg=kwargs.get('val_reg')
                member=kwargs.get('member')
                if val_reg == '' or member == 0:
                    log.debug('set_counter: invalid parameters val_reg '+str(val_reg)+', member '+str(member))
                    return 1
            except:
                log.warning('invalid parameters for set_counter() '+str(kwargs))
                return 2

            Cmd="select mbi,mba,regadd,wcount,x2,y2 from "+self.in_sql+" where val_reg='"+val_reg+"' and member='"+str(member)+"'"
            #print('set_counter: ',Cmd) # debug
            cur.execute(Cmd) # what about commit()? FIXME
            conn.commit()
            for row in cur:
                log.debug('row:',row) # debug
                mbi=row[0]
                mba=int(row[1]) if row[1] != '' else 0
                regadd=int(row[2]) if row[2] != '' else 0
                wcount=int(row[3]) if row[3] != '' else 0
                x2=int(row[4]) if row[4] != '' else 0
                y2=int(row[5]) if row[5] != '' else 0

        #print('set_counter: mbi,mba,regadd,wcount,x2,y2',mbi,mba,regadd,wcount,x2,y2) # debug
        if x2 != 0 and y2 != 0: #convert
            value=round(1.0*value*x2/y2) # assuming x1=x2=0, only counter registers to be written this way...
        else:
            log.warning('set_counter: invalid scaling x2,y2',x2,y2)
            return 1

        value=(int(value)&0xFFFFFFFF) # to make sure the value to write is 32 bit integer
        try:
            if wcount == 2: # normal counter, type h
                #res=mb[mbi].write(mba, regadd, values=[(value&0xFFFF0000)>>16,(value&0xFFFF)]) # works if multiple register write supported
                res = mb[mbi].write(mba, regadd, value=(value&0xFFFF0000)>>16) # single registe write
                time.sleep(0.1)
                res += mb[mbi].write(mba, regadd+1, value=(value&0xFFFF)) # single registe write

            elif wcount == -2:
                #res=mb[mbi].write(mba, regadd, values=[(value&0xFFFF), (value&0xFFFF0000)>>16]) # works if multiple register write supported
                res = mb[mbi].write(mba, regadd, value=(value&0xFFFF)) # single registe write
                time.sleep(0.1)
                res += mb[mbi].write(mba, regadd+1, value=(value&0xFFFF0000)>>16) # single registe write

            elif wcount == 1:
                res = mb[mbi].write(mba, regadd, value=(value&0xFFFF)) # single register write

            else:
                log.warning('set_counter: unsupported word count! mba '+str(mba)+', regadd '+str(regadd)+', wcount '+str(wcount))
                res=1

            if res == 0:
                log.debug('write success to counter mba.regadd '+str(mba)+'.'+str(regadd))
            else:
                log.warning('set_counter: write FAILED to mba '+str(mba)+', regadd '+str(regadd))
            return res

        except:  # set failed
            msg = 'failed set_counter mbi.mba.regadd '+str(mbi)+'.'+str(mba)+'.'+str(regadd)
            #udp.syslog(msg)
            log.warning(msg)
            traceback.print_exc()
            return 1
        # no need for commit, this method is used in transaction



    def read_grp(self,mba,regadd,count,wcount,mbi=0,regtype='h'): # update raw in self.in_sql with data from modbus registers
        ''' Reads sequential register group, process numbers according to counter size and store raw into table self.in_sql. Inside transaction!
            Compares the raw value from mobdbus register with old value in the table. If changed, ts is set to the modbus readout time self.ts.

            Add here counter state recovery if suddenly zeroed
            #    if value == 0 and ovalue >0: # possible pic reset. perhaps value <= 100?
            #        msg='restoring lost content for counter '+str(mba)+'.'+str(regadd)+':2 to become '+str(ovalue)+' again instead of '+str(value)
            #        #syslog(msg)
            #        print(msg)
            #        self.set_counter(value=ovalue, mba=mba, regadd=regadd, mbi=mbi, wcount=wcount, x2=x2, y2=y2) # does not contain commit()!
            #this above should be fixed. value is already saved, put it there!

            Delay in the end attempts to increase reliability of reading on mba change. INVESTIGATE, is it possibly a slave (ioboard) related problem?
            FIMXME:  do not attempt to access counters that are not defined in devices.sql! this should be an easy way to add/remove devices.
        '''
        self.ts = int(round(time.time(),0)) # refresh timestamp for raw, common for grp members
        step = int(abs(wcount))
        cur = conn.cursor()
        oraw = 0

        msg = 'grp read from mba '+str(mba)+'.'+str(regadd)+', cnt '+str(count)+', wc '+str(wcount)+', mbi '+str(mbi)+', regtype '+regtype

        if count > 0 and wcount > 0 and wcount < 5: # 64 bit max should be enough
            try:
                if mb[mbi]:
                    result = mb[mbi].read(mba, regadd, count=count, type=regtype) # client.read_holding_registers(address=regadd, count=1, unit=mba)
                    msg += ', raw: '+str(result)
                    if self.msgbus != None:
                        self.msgbus.publish('ai_grp_result', {'mbi': mbi, 'mba': mba, 'regadd': regadd, 'result': result})
                else:
                    msg += ' -- no mb[]!'

                log.info(msg) ###### See on hea kompaktne raw kontroll

            except:
                msg += ' -- FAILED!'
                log.warning(msg)
                return 2
        else:
            msg += ' -- invalid count or wcount!'
            log.warning(msg)
            return 2


        if result != None: # got something from modbus register
            try:
                for i in range(int(count/step)): # ai-co processing loop. tuple to table rows. tuple len is twice count! int for py3 needed
                    tcpdata = 0
                    #print('aico_grp debug: i',i,'step',step,'results',result[step*i],result[step*i+1]) # debug
                    if wcount == 2:
                        tcpdata = (result[step*i]<<16)+result[step*i+1]
                        #print('normal counter',str(i),'result',tcpdata) # debug
                    elif wcount == -2:
                        tcpdata = (result[step*i+1]<<16)+result[step*i]  # swapped word order, as in barionet
                        #print('swapped words counter',str(i),'result',tcpdata) # debug
                    elif wcount == 1: # normal ai and 1wire. the latter can be negative!
                        if len(result) - 1 >= i:
                            tcpdata = result[i]
                        else:
                            log.warning('read_grp invalid, i='+str(i)+' while result='+str(result)+', mba '+str(mba)+', regadd '+str(regadd)+', count '+str(count)+', regtype '+regtype)
                    else: # something else, lengths other than 1 2 -2 not yet supported!
                        log.warning('unsupported counter word size '+str(wcount))
                        return 1

                    #Cmd="select raw from "+self.in_sql+" where mbi="+str(mbi)+" and mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"' group by mbi,mba,regadd"
                    Cmd = "select raw,max(cfg) from "+self.in_sql+" where mbi="+str(mbi)+" and mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"' group by mbi,mba,regadd"
                    # get the old value to compare with new. can be multiple rows, group to single row. if counter and zero, ask_counters()
                    cur.execute(Cmd)
                    for row in cur:
                        oraw=int(row[0]) if row[0] !='' else -1
                        cfg=int(row[1]) if row[1] != '' else 0
                    #if tcpdata != oraw or oraw == -1: # update only if change needed or empty so far - NO! value CAN stay the same, but age is needed!
                    if str(regadd)[0] == '6' and tcpdata == 2560: #  failing temperature sensor, do not update
                        log.warning('failing temperature sensor on address '+str(regadd+i*step))
                    else:
                        Cmd = "UPDATE "+self.in_sql+" set raw='"+str(tcpdata)+"', ts='"+str(self.ts)+ \
                            "' where mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"' and mbi="+str(mbi) # koigile korraga selle mbi, mba, regadd jaoks
                        conn.execute(Cmd)
                        log.debug('updated '+self.in_sql+' with raw='+str(tcpdata)+' from mba '+str(mba)+' regadd '+str(regadd+i*step))  ######

                time.sleep(0.03) # ainult seriali puhul? ##########  FIXME
                return 0
            except:
                traceback.print_exc()
                time.sleep(0.2)
                return 1
        else:
            #log.warning('recreating modbus channel due to error on '+str(mbhost[mbi]))
            if mba == mb[mbi].get_mba_keepalive(): # recreate mb[] on access failure to this address only
                port = mb[mbi].get_port() # None if not tcp
                host = mb[mbi].get_host() # always exists, ip or /dev/tty
                serial = 0
                speed = 19200 # default
                if mb[mbi].get_host() == mb[mbi].get_port():
                    serialconf = mb[mbi].get_serial() # fails if not serial. (port, speed, parity, timeout, Bytesize, stopbits)
                    serial = 1
                    port =  serialconf[0]
                    speed = serialconf[1]
                    parity = serialconf[2]
                    #timeout = serialconf[3]
                    
                if serial == 0:
                    mb[mbi] = CommModbus(host = host, port = port) # tcp
                else:
                    mb[mbi] = CommModbus(host = host, speed = speed) # serial
                    mb[mbi].set_serial(port = port, speed = speed, parity = parity) # muid nagunii ei muuda
                    
                log.warning('recreated mb['+str(mbi)+'] due to read FAILURE for mbi,mba,regadd,count '+str(mbi)+', '+str(mba)+', '+str(regadd)+', '+str(count))
                time.sleep(0.5) # hopefully helps to avoid sequential error / recreations
                
            return 1



    def read_all(self): # read all defined modbus ai and counter channels to sql in groups by regtype, usually 32 bit / 2 registers.
        ''' Must read the counter registers by sequential regadd blocks if possible (if regadd increment == wcount.
            Also converts the raw data (incl member rows wo mba) into services, calculates the svc component statuses
            and summary stratus, sends away to UDPchannel.
        '''
        respcode = 0
        mba = 0
        val_reg = ''
        sta_reg = ''
        status = 0
        value = 0
        lisa = ''
        desc = ''
        comment = ''
        #mcount=0
        Cmd1 = ''
        #self.ts = round(time.time(),2) # not needed here
        #ts_created=self.ts # not needed here
        cur = conn.cursor()
        cur3 = conn.cursor()
        bmba = 0 # mba for sequential register address block
        bfirst = 0 # sequential register block start
        blast = 0
        wcount = 0
        bwcount = 0
        bcount = 0
        tcpdata = 0
        sent = 0
        regtype = ''
        bregtype = ''
        self.cpi = -1 # start with cp instance numbering, by service members not services!

        try:
            Cmd = "BEGIN IMMEDIATE TRANSACTION" # combines several read/writes into one transaction
            # read mbi,mba,regadd,wcount,regtype from channels table to define groups
            # read modbus registers in groups and write raw into table
            # read svc from table to calculate and update value
            #

            conn.execute(Cmd)
            Cmd = "select mba,regadd,wcount,mbi,regtype from "+self.in_sql+" where mba != '' and regadd != '' group by mbi,mba,regtype,regadd" # gruppideks jagamine
            cur.execute(Cmd) # selle paringu alusel raw update, hiljem teha value arvutused iga teenuseliikme jaoks eraldi
            for row in cur: # registers queried by one multiread per group
                mba=int(row[0]) if int(row[0]) != '' else 0
                regadd=int(row[1]) if int(row[1]) != '' else 0
                wcount=int(row[2]) if int(row[2]) != '' else 0 # wordcount for the whole group!!
                mbi=int(row[3]) if int(row[3]) != '' else 0 # modbus connection indexed
                regtype=row[4] if row[4] != '' else 'h' # modbus register holding or input
                #print('found channel mbi,mba,regadd,wcount,regtype',mbi,mba,regadd,wcount,regtype) # debug

                if bfirst == 0:
                    bfirst = regadd
                    blast = regadd
                    bwcount = wcount # wcount can change with next group
                    bcount=int(abs(wcount)) # word count is the count
                    bmba=mba
                    bmbi=mbi
                    bregtype= regtype
                    #print(' group mba '+str(bmba)+' start ',bfirst) # debug
                else: # not the first
                    if mbi == bmbi and regtype == bregtype and mba == bmba and regadd == blast+abs(wcount): # sequential group still growing
                        blast = regadd
                        bcount=bcount+int(abs(wcount)) # increment by word size
                        #print('group end shifted to',blast) # debug
                    else: # a new group started, make a query for previous
                        self.read_grp(bmba,bfirst,bcount,bwcount,bmbi,bregtype) # reads and updates table with previous data #####################  READ MB  ######
                        bfirst = regadd # new grp starts immediately
                        blast = regadd
                        #bwcount = wcount # does not change inside group
                        bcount=int(abs(wcount)) # new read piece started
                        bwcount=wcount
                        bmba=mba
                        bmbi=mbi
                        bregtype=regtype
                        #print('group mba '+str(bmba)+' start ',bfirst) # debug

            if bfirst != 0: # last group yet unread
                #print(' group end detected at regadd',blast) # debug
                #print('going to read last  group, registers from',bmba,bfirst,'to',blast,'regcount',bcount,'regtype',bregtype) # debug
                self.read_grp(bmba,bfirst,bcount,bwcount,bmbi,bregtype) # reads and updates table with previous data #####################  READ MB  ######

            # raw sync (from modbus to sql) done.



            # now process raw -> value and find statuses using make_svc() for each service.
            #power calculations happen in make_svc too!

            Cmd="select val_reg from "+self.in_sql+" group by val_reg" # find services
            log.debug('read_all Cmd='+Cmd) ### oli kommenteeritud 31.1?
            cur.execute(Cmd) ### oli kommenteeritud 31.1?

            for row in cur: # SERVICES LOOP
                val_reg=row[0] # service value register name
                #sta_reg=val_reg[:-1]+"S" # status register name ASSUMPTION. BUT MAKE_SVC ACCEPTS NOW STA_REG=''

                log.debug('processing '+self.in_sql+' rows into service with val_reg '+val_reg+' sta_reg '+sta_reg)
                #self.make_svc(val_reg,sta_reg) ## sets status and notifies id status chg in any member
                self.make_svc(val_reg) ## sets status and notifies id status chg in any member. self.cpi?

            conn.commit() #  haarab ka make_svc()
            sys.stdout.write('A')
            return 0

        except:
            msg = 'problem with acchannels.read_all(): '+str(sys.exc_info()[1])
            if self.msg != msg:
               self.msg = msg
               log.warning(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            time.sleep(1)
            return 1

    #read_all end #############



    def sync_ao(self):
        ''' Synchronizes AI registers with data in aochannels table '''
        #print('write_aochannels start') # debug
        # and use write_register() write modbus registers  to get the desired result (all ao channels must be also defined in aichannels table!)
        respcode=0
        mbi=0
        mba=0
        omba=0 # previous value
        val_reg=''
        desc=''
        value=0
        word=0 # 16 bit register value
        #comment=''
        mcount=0
        cur = conn.cursor()
        cur3 = conn.cursor()
        ts_created=self.ts # selle loeme teenuse ajamargiks

        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION"
            conn.execute(Cmd)

            # 0      1   2    3        4      5    6      7
            #mba,regadd,bit,bootvalue,value,rule,desc,comment

            Cmd="select "+self.out_sql+".mba,"+self.out_sql+".regadd,"+self.out_sql+".value,"+self.out_sql+".mbi from "+self.out_sql+" left join "+self.in_sql+" \
                on "+self.out_sql+".mba = "+self.in_sql+".mba AND "+self.out_sql+".mbi = "+self.in_sql+".mbi AND "+self.out_sql+".regadd = "+self.in_sql+".regadd \
                where "+self.out_sql+".value != "+self.in_sql+".value" #
            # the command above retrieves mba, regadd and value where values for mba, reagsdd, mbi do not match in aicochannels and aochannels
            #print "Cmd=",Cmd
            cur.execute(Cmd)

            for row in cur: # got mba, regadd and value for registers that need to be updated / written
                #log.debug('row: '+str(repr(row))) # toob appd.log sisse
                regadd = 0
                mba = 0

                mba = int(eval(row[0])) if row[0] != '' else None  #  0 # must be a number
                regadd = int(eval(row[1])) if row[1] != '' else 0 # must be a number
                value = int(eval(row[2])) if row[2] != '' else 0  # komaga nr voib olla, teha int!
                mbi = row[3] if row[3] != None else 0  # mbi on num!

                try:
                    if mb[mbi] and mba: # alpha innotek kasutab mba 0! modbustcp puhul voimalik
                        respcode = respcode + mb[mbi].write(mba=mba, reg=regadd, value=value)
                        if respcode == 0:
                            log.debug('successfully written value '+str(value)+' to mbi '+str(mbi)+', mba '+str(mba)+' regadd '+str(regadd))
                        else:
                            log.warning('FAILED write to modbus device mbi '+str(mbi)+', mba '+str(mba)+' regadd '+str(regadd))
                            return 1
                except:
                    log.warning('FAILED write to modbus device mbi '+str(mbi)+', mba '+str(mba)+' not defined in devices.sql?')
                    return 2

            conn.commit()  #  transaction end - why?
            return 0
        except:
            msg = 'problem with sync_ao()!'
            log.warning(msg)
            traceback.print_exc()
            return 1
        # sync_ao() end. FRESHENED DICHANNELS TABLE VALUES AND CHG BITS (0 TO SEND, 1 TO PROCESS)



    def get_aivalue(self, svc, member):
        ''' Returns value,lo,hi,substatus values based on service name and member number. Value None if empty '''
        # status gets reported as summary status foir service, not svc member!
        #(mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment,type integer)
        cur=conn.cursor()
        Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3, et ei saaks muutuda lugemise ajal
        conn.execute(Cmd)
        Cmd="select value,outlo,outhi,status,ts from "+self.in_sql+" where val_reg='"+svc+"' and member='"+str(member)+"'"
        #print(Cmd) # debug
        cur.execute(Cmd)
        raw = 0
        value = None # None
        outlo = None
        outhi = None
        status = 0
        found = 0
        ts_created = 0
        for row in cur: # should be one row only
            #print(repr(row)) # debug
            found=1
            value=int(eval(row[0])) if row[0] != '' and row[0] != None else None ## 9.7.2015
            outlo=int(eval(row[1])) if row[1] != '' and row[1] != None else None
            outhi=int(eval(row[2])) if row[2] != '' and row[2] != None else None
            status=int(eval(row[3])) if row[3] != '' and row[3] != None else 0
            ts_created = int(eval(row[4])) if row[4] != '' and row[4] != None else 0 # will be stalled
        if found == 0:
            msg='get_aivalue failure, no member '+str(member)+' for '+svc+' found!'
            log.warning(msg)

        conn.commit()
        log.debug('svc '+svc+' member '+str(member)+' value '+str(value)+' ts_created '+str(ts_created)) # debug
        return value, outlo, outhi, status, ts_created # ts added 26.7.2015

    def get_aivalues(self, svc, maxage = None): # age in s FIXME no mba result?
        ''' Returns al list of all member values. Returns [] if nothing found. Stalled values are replaced with None. '''
        if maxage == None:
            maxage = self.ts # all ages are good
        cur = conn.cursor()
        Cmd = "BEGIN IMMEDIATE TRANSACTION" # conn3, et ei saaks muutuda lugemise ajal
        conn.execute(Cmd)
        Cmd = "select value, ts, regtype from "+self.in_sql+" where val_reg='"+svc+"' order by member"
        log.debug(Cmd) ##
        cur.execute(Cmd)
        values = [] # None
        found = 0
        ts_created = 0
        if maxage == None:
            maxage = self.ts # no filtering based on age

        for row in cur: # should be one row only
            ts_created = int(eval(row[1])) if row[1] != '' and row[1] != None else 0 # will be stalled
            regtype= row[2]
            found = 1
            if ((self.ts - ts_created < maxage and row[1] != '' and row[1] != None) or (regtype[0] == 's')) and row[0] != '' :
                values.append(int(row[0]))
            else:
                values.append(None)

        if found == 0:
            msg='get_aivalue() FAILURE, no values for '+svc+' found!'
            log.warning(msg)

        conn.commit()
        return values # ts added 26.7.2015


    def set_aivalues(self, svc, values = []): # member count must match the svc member count!
        ''' Returns al list of all member values. Returns [] if nothing found. Stalled values are replaced with None. '''
        if isinstance(svc, str):
            pass
        else:
            log.warning('servicename '+str(svc)+' NOT str!') # ?
            return 2

        Cmd = "BEGIN IMMEDIATE TRANSACTION" # conn3
        conn.execute(Cmd)
        try:
            for i in range(len(values)):
                #Cmd = "update "+self.in_sql+" set value='"+str(values[i])+"', ts='"+str(self.ts)+"' where val_reg='"+svc+"' and member = '"+str(i+1)+"'"
                Cmd = "update "+self.in_sql+" set value='"+str(int(values[i]))+"', ts='"+str(int(self.ts))+"' where val_reg='"+svc+"' and member = '"+str(i+1)+"'"
                log.debug(Cmd) ##
                conn.execute(Cmd)
            conn.commit()
            log.info('aivalues update done for '+svc+' with '+str(values))
            return 0
        except:
            log.warning('FAILED to update svc '+svc+' with values '+str(values))
            traceback.print_exc()
            return 1


    def set_aivalue(self, svc, member, value): # sets variables like setpoints or limits to be reported within services, based on service name and member number
        ''' Setting member value using sqlgeneral set_membervalue. adding sql table below for that '''
        return s.set_membervalue(svc,member,value,self.in_sql,raw=False) # set value

    def set_airaw(self, svc, member, value): # sets variables like setpoints or limits to be reported within services, based on service name and member number
        ''' Setting member raw value using sqlgeneral set_membervalue. adding sql table below for that '''
        return s.set_membervalue(svc,member,value,self.in_sql,raw=True) # set raw, value will be calc by make_

    def set_aovalue(self, value, mba, reg, mbi = 0):
        ''' Write value to follow into aochannels table.
            The according modbus holding register will be written by sync_ao() until the according
            aicochannels register contain the same value.
        '''
        #(mba,regadd,bootvalue,value,ts,rule,desc,comment)
        Cmd="BEGIN IMMEDIATE TRANSACTION" # conn
        conn.execute(Cmd)
        Cmd="update "+self.out_sql+" set value='"+str(value)+"' where regadd='"+str(reg)+"' and mba='"+str(mba)+"' and mbi="+str(mbi) # mbi int
        #print(Cmd)
        try:
            conn.execute(Cmd)
            conn.commit()
            log.debug('set_aovalue value '+str(value)+' mba '+str(mba)+' regadd '+str(reg)) ##
            return 0
        except:
            msg='set_aovalue failure: '+str(sys.exc_info()[1])
            log.warning(msg)
            #udp.syslog(msg)
            return 1  # update failure


    def set_aosvc(self, svc, member, value): # to set a readable output channel by the service name and member using aicochannels table
        ''' Set service member value by service name and member number, to be synced into holding register.
            The aicochannels table must contain a similar input channel, to compare the result with.
        '''
        #(mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment,type integer) # ai
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        conn.execute(Cmd)
        Cmd = "select mba, regadd, mbi from "+self.in_sql+" where val_reg='"+svc+"' and member='"+str(member)+"'"
        cur = conn.cursor()
        cur.execute(Cmd)
        mba = None
        reg = None
        mbi = None
        for row in cur: # should be one row only
            try:
                mba = int(row[0])
                reg = int(row[1])
                mbi = row[2]
                log.debug('found mbi '+str(mbi)+', mba '+str(mba)+', reg '+str(reg)+' for svc '+svc+' member '+str(member)) ##
                self.set_aovalue(value, mba, reg, mbi) # FIXME  mbi?  ON VAJA TEGELIKULT!
                conn.commit()
                return 0
            except:
                msg = 'set_aovalue in set_aosvc failed for reg '+str(reg)+': '+str(sys.exc_info()[1])
                log.warning(msg)
                #udp.syslog(msg)
                return 1



    def report_all(self, svc = ''): # send the aico service messages to the monitoring server (only if fresh enough, not older than 2xappdelay). all or just one svc.
        ''' Make all (defined self.in_sql) services reportable (with status chk) and send it away to UDPchannel '''
        mba=0
        val_reg=''
        desc=''
        cur=conn.cursor()
        ts_created=self.ts # selle loeme teenuse ajamargiks

        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3, kogu selle teenustegrupiga (aichannels) tegelemine on transaction
            conn.execute(Cmd)
            if svc == '':  # all services
                Cmd="select val_reg from "+self.in_sql+" group by val_reg"
            else: # just one
                Cmd="select val_reg from "+self.in_sql+" where val_reg='"+svc+"'"
            cur.execute(Cmd)

            self.cpi = -1 # self.cp[self.cpi] instance counter initially missing
            for row in cur: # services
                val_reg=row[0] # teenuse nimi
                #sta_reg=val_reg[:-1]+"S" # nimi ilma viimase symbolita ja S - statuse teenuse nimi, analoogsuuruste ja temp kohta

                self.make_svc(val_reg) # sends to buffer ['T1S', 0, 'T1W', '170 218 164']
                #if sendtuple != None and sendtuple != []: #
                #    udp.send(sendtuple) # can send to buffer double if make_svc found change. no dbl sending if ts is the same.
                #    log.debug('buffered for reporting: '+str(sendtuple)) ##
                #else:
                #   msg = 'FAILED to report due to empty sendtuple for svc '+val_reg
                #    if self.msg != msg:
                #        self.msg = msg
                #        log.warning(msg)
                    # return 1 # other services still need to be reported, commit needs to be done.

            conn.commit() # aicochannels svc_report transaction end
            return 0

        except:
            msg='PROBLEM with acchannels.report_all() for svc '+svc+' based on table '+self.in_sql+': '+str(sys.exc_info()[1])
            log.warning(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            return




    def make_svc(self, val_reg, sta_reg=''):  # ONE svc, both val_reg and sta_reg exist for ai and counters
        ''' Make a single service record WITH STATUS based on existing values and update the scaled value in sql table.
            Use block as hysteresis in value units for status change, if cfg&8192 == True.
            Use block as off_tout in s for counters with power-on/off detection if cfg&64 == True.
            If sta_reg is empty and vale_reg ends with W, S is assumed for sta_reg name end.

            self.cpi must be set before executing!
            FIXME - do not send a svs out if any of the members is missing / None!
        '''

        status = 0 # initially for whole service
        mstatus = 0
        cur = conn.cursor()
        lisa = ''
        olisa = ''
        value = None
        hilim = None
        lolim = None
        nolim = 0
        values = [] # to be reported via msgbus
        mcount = 0
        
        if sta_reg == '' and (val_reg[-1] == 'W' or val_reg[-1] == 'V'):
            sta_reg = val_reg[0:-1]+'S' # assuming S in the end

        Cmd="select mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,regtype,grp,mbi,wcount from "+self.in_sql \
            +" where val_reg='"+val_reg+"' order by member asc" # avoid trouble with column order
        log.debug(Cmd)
        #print(Cmd)

        cur.execute(Cmd) # another cursor to read the same table
        ts_now = time.time() # time now in sec
        rowproblemcount = 0 # count of invalid members in svc

        for srow in cur: ## go through service members
            log.debug(repr(srow))
            repeat = False # earlier values will be sent with shifted time if True
            mcount += 1 # member count
            mba = -1 #
            regadd = -1
            member = 0
            cfg = 0
            x1 = 0
            x2 = 0
            y1 = 0
            y2 = 0
            outlo = None
            outhi = None
            ostatus = 0 # previous member status
            #tvalue=0 # test, vordlus
            oraw = 0
            ovalue = 0 # previous (possibly averaged) value
            ots = 0 # eelmine ts value ja status ja raw oma
            avg = 0 # keskmistamistegur, mojub alates 2
            block = 0 # power off_tout for counters
            hyst = 0
            result = None
            #desc=''
            #comment=''
            rowproblem = 0 # initially ok
            # 0       1     2     3     4   5  6  7  8  9    10     11  12    13  14   15     16  17    18
            #mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment  # aichannels
            try:
                mba = int(srow[0]) if srow[0] != '' else 0   # must be int! will be -1 if empty (setpoints)
                regadd = int(srow[1]) if srow[1] != '' else 0  # must be int! will be -1 if empty
                val_reg = srow[2] # see on string
                member = int(srow[3]) if srow[3] != '' else 0
                cfg = int(srow[4]) if srow[4] != '' else 0 # konfibait nii ind kui grp korraga, esita hex kujul hiljem
                x1 = float(srow[5]) if srow[5] != '' else 0
                x2 = float(srow[6]) if srow[6] != '' else 0
                y1 = float(srow[7]) if srow[7] != '' else 0
                y2 = float(srow[8]) if srow[8] != '' else 0
                outlo = float(srow[9]) if srow[9] != '' else None
                outhi = float(srow[10]) if srow[10] != '' else None
                avg = float(srow[11]) if srow[11] != '' else 0  #  averaging strength, values 0 and 1 do not average!
                block = int(srow[12]) if srow[12] != '' else 0 # off-tout for power related on/off
                raw = int(srow[13]) if srow[13] != '' else None # None on vaja! 0 ei tohi saata kui oige vaartus puudub!
                ovalue = int(srow[14]) if (srow[14] != '' ) else None # teenuseliikme endine vaartus
                ostatus = int(srow[15]) if srow[15] != '' else 0 # teenusekomponendi status - ei kasuta / votame kasutusele
                ots = eval(srow[16]) if srow[16] != '' else 0
                #desc=srow[17]
                regtype = srow[18] # should be h or i for modbus registers
                mbi = srow[20] # int
                wcount = int(srow[21]) if srow[21] != '' else 1  # word count
                ##chg = 0 # member status change flag
                log.debug('>>> val_reg '+val_reg+' member '+str(member)+', cfg='+str(cfg)+', raw='+str(raw)+', ovalue='+str(ovalue)+', outlo='+str(outlo)+', outhi='+str(outhi)) ##
                #print('val_reg '+val_reg+' member '+str(member)+', cfg='+str(cfg)+', raw='+str(raw)+', ovalue='+str(ovalue)+', outlo='+str(outlo)+', outhi='+str(outhi)) # debug

            except:
                log.warning('invalid data from '+self.in_sql+' for svc '+val_reg+', srow: '+repr(srow))
                rowproblem = 1
                traceback.print_exc()
                time.sleep(2)

            #power instances to be done
            if (cfg & 64): # power instance index increment HERE! within service list
                self.cpi += 1
                log.debug('****** cpi '+str(self.cpi)+' val_reg '+val_reg+'.'+str(member))
                try:
                    if self.cp[self.cpi]:
                        pass # this instance already exists
                except:
                    # make_svc() must append self.cp if not exists
                    self.cp.append(Counter2Power(val_reg, member, off_tout = block)) # another Count2Power instance. 100s  = 36W threshold if 1000 imp/kWh
                    log.info('created counter2power (ac.cp) instance '+str(self.cpi)+' for val_reg '+str(val_reg)+' member '+str(member)) ##


            # cfg related tests and calc
            if (regtype == 'h' or regtype == 'i'  or regtype == 'c' or regtype == 'r'): # for channel data only, not for setup values (s, s!)
                if raw != None:
                    if rowproblem == 1:
                        msg = 'svc processing skipped due to invalid data from '+self.in_sql+' for svc '+val_reg+', srow: '+repr(srow)
                        if self.msg != msg:
                            self.msg = msg
                            log.warning(msg)
                    elif regtype != 'r' and (ots < ts_now - 10 * self.readperiod and ots < ts_now - 3 * self.sendperiod): # raw too old, stalled
                        log.warning('svc processing skipped due to stalled (for '+str(int(ts_now - ots))+' s) raw data ('+str(raw)+') for '+val_reg+'.'+str(member))
                    else: # data fresh enough, going to process. data of type r is never stalled.

                        ## POWER? FILTER? ####
                        if (cfg&64): # power, no sign, increment to be calculated! divide increment to time from the last reading to get the power
                            #cpi += 1 # counter2power index, increment BEFORE value validation

                            #log.info('going to calc power for mba.regadd '+str(mba)+'.'+str(regadd)+' using cp['+str(self.cpi)+']') ## debug
                            #res = self.cp[self.cpi].calc(ots, raw, ts_now = self.ts) # power calculation based on raw counter increase
                            res = self.cp[self.cpi].calc(raw) # based on current ts only!
                            if res != None and res[0] != None:
                                log.info('got calc power result from cp['+str(self.cpi)+']: '+str(res)+', based on raw '+str(raw))  ## debug
                                if (cfg&128): # on off state from power
                                    raw = res[1] # state on/off 0 or 1
                                    if res[2] != 0: # on/off change
                                        self.chg += 1 # immediate notification needed due to state change
                                        log.info('state change in cp['+str(self.cpi)+']')
                                else: # just power, not state
                                    raw = int(round(res[0],0)) # power in W, res[0] has 3 decimals!
                            
                        elif (cfg&2048): # 1wire filter. should have cfg bit 4096 as well!
                            if raw == 1360 or raw == 4096:
                                log.warning('invalid raw value '+str(raw)+' for temp sensor in svc '+val_reg+'.'+str(member)+', replacing with None')
                                raw = None # there should be no change for value
                                value = None

                        ## SCALING #############
                        if raw != None:
                            if (cfg & 4096): # take sign into account
                                if raw >= (2**(wcount*16-1)): # negative!
                                    raw = raw-(2**(wcount*16))
                                    log.debug('converted to negative: '+str(raw)) # debug


                            if x1 != x2 and y1 != y2: # seems like normal input data, also not state from power
                                value = (raw-x1) * (y2-y1) / (x2-x1)
                                value = int(round(y1+value)) # integer values to be reported only
                            else:
                                #log.debug('val_reg '+val_reg+' member '+str(member)+', raw '+str(raw)+' ai2scale conversion NOT DONE! using value = raw ='+str(raw))
                                #log.warning('val_reg '+val_reg+' member '+str(member)+', raw '+str(raw)+' ai2scale conversion NOT DONE!')
                                ##value = None # do not change previous data until stalled
                                rowproblem = 1 # this service will not be used in notification
                                ## binary services defined in aicochannels must have x1 x2 y1 y2! 0 1 0 1


                        if value != None and avg != None and ovalue != None:
                            if avg > 1 and abs(value - ovalue) < value / 2:  # averaging the readings. big jumps (more than 50% change) are not averaged.
                                value = int(((avg - 1) * ovalue+value)/avg) # averaging with the previous value, works like RC low pass filter
                                log.debug('averaging on, value became '+str(value)) # debug

                            if (cfg & 256) and (abs(value - ovalue) > abs(value / 5.0)): # change more than 20% detected, use num w comma!
                                log.debug('### value change (was '+str(ovalue)+', became '+str(value)+') for '+val_reg+'.'+str(member)+', need to send')
                                repeat = True
                                self.chg += 1
                                

                            # counter2power and scaling done, status check begins ##########
                            if cfg & 8192: # use hysteresis from block
                                hyst = block # int
                            mstatus = self.value2status(value,cfg,outlo,outhi,ostatus, hyst) # default hyst=0 value units


                            if mstatus != ostatus: # member status change detected
                                self.chg += 1 # immediate notification within this method
                                log.info('member status chg (after possible inversion) to ' +str(mstatus))



                        if value != None:
                            #limiting out the values outside  6 times hi-lo band
                            nolim = 0  # initial value, 3 if both limits missing
                            if outlo != None and outhi != None:
                                nolim = 0
                                hilim = outhi + 3 * (outhi - outlo)
                                lolim = outlo - 3 * (outhi - outlo)
                            elif outlo == None and outhi != None:
                                nolim = 1
                                hilim = outhi + 3 * abs(outhi)
                                lolim = outhi - 3 * abs(outhi)
                            elif outhi == None and outlo != None:
                                nolim = 2
                                lolim = outlo - 3 * abs(outlo)
                                hilim = 2 ** 31 - 1
                            else: # both outhi, outlo none
                                nolim = 3
                                log.debug('both lolim, hilim None for '+val_reg)

                            if (nolim < 3 and value > lolim and value < hilim) or nolim == 3 or lolim == hilim: # the latter is somewhat illegal
                                # but workaround to 0.0 instead of None for outlo outhi koskla2 Z6W FIXME
                                Cmd="update "+self.in_sql+" set status='"+str(mstatus)+"', value='"+str(value)+"' where val_reg='"+val_reg+"' and member='"+str(member)+"'"
                                # limit possible value spikes after restart due to counter reset
                                conn.execute(Cmd) # who commits? the calling method, read_all()!!!
                                log.debug(Cmd) # status and value update based on raw
                            else:
                                log.warning('val_reg '+val_reg+'.'+str(member)+' value '+str(value)+' out of allowed band from '+str(lolim)+' to ' +str(hilim))
                                # but still updating status... to avois excessive status change related reporting with faulty limits
                                Cmd="update "+self.in_sql+" set status='"+str(mstatus)+"' where val_reg='"+val_reg+"' and member='"+str(member)+"'"
                                conn.execute(Cmd) # who commits? the calling method, read_all()!!!

                        else:
                            msg = 'skipped updating '+self.in_sql+' due to '+val_reg+' member '+str(member)+' value None! chk regadd '+str(regadd)
                            if self.msg != msg:
                                self.msg = msg
                                log.warning(msg)
                            rowproblem = 1

                    ############# h, c, r or i processing done #######

                else: # raw == None !!!!
                    pass # value = None
                    log.warning('SKIPPED svc '+val_reg+'.'+str(member)+' value update due to raw None')

            elif 's' in regtype: # setup value
                value = ovalue # use the value in table without conversion or influence on status
                if mba:
                    log.warning('NO mba SHOULD be set for setup value '+val_reg+'.'+str(member)) # debug


            if lisa != '': # not the first member
                lisa += ' ' # separator between member values
                olisa += ' ' # old value to repeat
                
            try: # what if None? exception?
                if value != None:
                    lisa += str(int(round(value))) # adding member values into one string
                    values.append(int(round(value))) # for msgbus
                    if ovalue != None:
                        olisa += str(int(round(ovalue))) # adding member values into one string
                else:
                    log.warning('invalid value None from regtype '+regtype+', reg '+val_reg+', member '+str(member))
            except:
                msg = 'invalid value '+str(value)+' found for service '+val_reg+'.'+str(member)
                traceback.print_exc()
                if self.msg != msg:
                    self.msg = msg
                    log.warning(msg) # do not refer value here, may be missing from another mba!
                rowproblem = 1

            if mstatus > status:
                    status = mstatus # max status will prevail

            rowproblemcount += rowproblem

            chk = len(olisa.split(' '))
            if chk != mcount: # member(s) missing!
                log.error('invalid old sendtuple member count '+str(chk)+', should be '+str(mcount)+', skipping notifying svc '+val_reg)
                rowproblemcount += 1
            chk = len(lisa.split(' '))
            if chk != mcount: # member(s) missing!
                log.error('invalid new sendtuple member count '+str(chk)+', should be '+str(mcount)+', skipping notifying svc '+val_reg)
                rowproblemcount += 1
                
        # service members done, check if all of them valid to use in svc tuple
        if rowproblemcount == 0: # all members valid
            if repeat: # > 20% change was detected from ovalue to value
                sendtuple = [sta_reg, status, val_reg, olisa] # repeat the earlier service to buffer, with last status though
                udp.send(sendtuple, timeadd = -self.readperiod) # send earlier too due to change since last reading
                log.info('==repeating earlier sendtuple before new with shifted time, ovalue '+str(ovalue)+', value '+str(value)) ###
            
            sendtuple = [sta_reg, status, val_reg, lisa] # sending service to buffer
            udp.send(sendtuple) # send end result here, possibly the old result was sent once again before 
            if self.msgbus != None:
                try:
                    self.msgbus.publish(val_reg, {'values': values, 'status': status})
                    #log.debug('published to msgbus: '+str(val_reg)+' values '+str(values)+', status '+str(status)) ##
                except:
                    traceback.print_exc()
            #return sendtuple # for regular send or status check
        else:
            log.warning(val_reg+' had '+str(rowproblemcount)+' problematic members')
            

    def value2status(self,value,cfg,outlo,outhi,ostatus=0,hyst=0):
        ''' Returns svc member status based on value and limits, taking cfg and previous status into account.
            If value to status inversion is in use (to define forbidden instead of allowed zones),
            normalize old status ostatus first and then invert mstatus in the end.
            Use hysteresis in value units for status change if needed.
        '''
        # svc STATUS CHK. check the value limits and set the status, according to configuration byte cfg bits values
        # use hysteresis to return from non-zero status values

        # CONFIG BYTE BIT MEANINGS
        # 1 - below outlo warning,
        # 2 - below outlo critical,
            # NB! 3 - not to be sent  if value below outlo
        # 4 - above outhi warning
        # 8 - above outhi critical
            # NB! 3 - not to be sent  if value above outhi
        # 16 - - immediate notification on status change (USED FOR STATE FROM POWER)
        # 32  - limits to state inversion
        # 64 - power to be counted based on count increase and time period between counts
        # 128 -  state from power flag
        # 256 - notify on 10% value change (not only limit crossing that becomes activated by first 4 cfg bits)
        # 512 - do not report at all, for internal usage
        # 1024 - raw counter
        # 2147  1wire, filter out 4096 and 1086
        # 4096 signed value
        # 8192 use hysteresis from block

        mstatus = 0 # initial service member status
        bitvalue = 0 # remember the important bitvalue for nonzero internal status
        #print('value,cfg,outlo,outhi',value,cfg,outlo,outhi) # debug

        if (cfg & 32): # status inversion IN USE, normalize
            if ostatus > 0:
                ostatus = 0
            else:
                ostatus = 1 # treating statuses 1 and 2 equally

        if outhi != None: # hi limit set
            if value > outhi + hyst: # above hi limit
                #print('value above outhi,cfg',cfg) # debug
                if (cfg & 4) > 0: # warning
                    mstatus = 1
                if (cfg & 8)>0: # critical
                    mstatus = 2
                if (cfg & 12) == 12: #  not to be sent
                    mstatus = 3
                #print('mstatus due to value above outhi',mstatus) # debug
            else: # POSSIBLE return with hysteresis, even without existing outlo
                if value < outhi - hyst and (outlo == None or (outlo != None and value > outlo + hyst)):
                    mstatus = 0 # below hyst limit
                    #print('mstatus due to return below outhi',mstatus) # debug
                else: # within dead zone or above
                    if mstatus == 0 and ostatus > 0:
                        mstatus = ostatus
                        #print('no change for old mstatus due to dead zone hi',mstatus) # debug

        if outlo != None: # lo limit set
            if value < outlo - hyst: # below lo limit
                #print('value below outlo') # debug
                if (cfg & 1): # warning
                    mstatus = 1
                if (cfg & 2): # critical
                    mstatus = 2
                if (cfg & 3) == 3: # not to be sent, unknown
                    mstatus = 3
                #print('mstatus due to value below outlo',mstatus) # debug
            else: # POSSIBLE return with hysteresis, even without existing outlo
                if value > outlo + hyst and (outhi == None or (outhi != None and value < outhi - hyst)):
                    mstatus = 0 # below hyst limits
                    #print('mstatus due to return above outlo',mstatus) # debug
                else: # within dead zone or below
                    if mstatus == 0 and ostatus > 0:
                        mstatus = ostatus
                        #print('no change for old mstatus due to dead zone lo',mstatus) # debug

        if (cfg & 32): # possible status inversion for each member
            #print('status inversion enabled,cfg,mstatus before inv',cfg,mstatus) # debug
            if mstatus == 0: # within FORBIDDEN zone
                if (cfg & 5):
                    mstatus = 1 # normal becomes warning
                elif(cfg & 10):
                    mstatus = 2 # normal becomes critical, higher cfg bit  wins
            else: # outside forbidden zone
                mstatus = 0 # not normal becomes normal
        else:
            #print('no inversion used, unchanged mstatus',mstatus) # debug
            pass
        return mstatus


    def doall(self): # do this regularly, executes only if time is right
        ''' Does everything that is regularly needed in this class on time if executed often enough.
            Do not report too after early, counters may get restored from server.
        '''
        ##og.info('ai_sync (doall) start')
        res=0
        self.chg = 0
        self.ts = round(time.time(),0)
        if self.ts - self.ts_read > self.readperiod: # ei oma tahtsust kui kaivitab ioloop timer
            self.ts_read = self.ts
            try:
                res = self.read_all() ## read all registers defined in aicochannels
                if self.chg > 0:
                    log.info('##### '+str(self.chg)+' value change(s) detected')
                self.sync_ao() ### write ao registers that are also present in aicochannels but the content is different
            except:
                traceback.print_exc()

        if (self.ts - self.ts_send > self.sendperiod) or (self.chg > 0): #  and self.ts - self.ts_send > self.sendperiod / 10):
            ''' send also if change is detected '''
            if self.chg > 0:
                log.info('irregular ac reporting due to '+str(self.chg)+' value change(s)')
            else:
                log.debug('normal reporting due sendperiod '+str(self.sendperiod)+' elapsed')

            self.ts_send = self.ts
            try:
                res = res + self.report_all() ### report all services in aicochannels
            except:
                traceback.print_exc()
        ##log.info('ai_sync (doall) end')
        return res

    #END