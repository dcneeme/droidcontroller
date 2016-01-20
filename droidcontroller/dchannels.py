# to be imported to access modbus registers as analogue io
# 03.04.2014 neeme
# 04.04.2014
# 06.04.2014 seguential register read for optimized reading
# 14.6.2015 mingi jama mone teenusega mis ei tekita sendtuple...
# 11.9.2015 lisatud chg_dict, aga mingi jama

''' mb[mbi].read(mba, reg, count = 1, type = 'h'):  # modbus read example

    mb[mbi].write(mba, reg, type = 'h', **kwargs):  # modbus write example
        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'type': Modbus register type, h = holding, c = coil
        :param kwargs['count']: Modbus registers count for multiple register write
        :param kwargs['value']: Modbus register value to write
        :param kwargs['values']: Modbus registers values array to write
'''



from droidcontroller.sqlgeneral import * # SQLgeneral
s=SQLgeneral()

import time

import logging
log = logging.getLogger(__name__)

class Dchannels(SQLgeneral): # handles aichannels and aochannels tables
    ''' Access to io by modbus binary register bits (and also via services?)
        SQLgeneral will open shared Modbus client.
        Able to sync input and output channels and accept changes to service members by their sta_reg code
    '''

    def __init__(self, msgbus=None, in_sql = 'dichannels.sql', out_sql = 'dochannels.sql', readperiod = 0, sendperiod = 120): # sends immediately on change too!
        self.msgbus = msgbus
        self.msg = ''
        # readperiod 0 means read on every execution. this is usually wanted behaviour to detect any di changes as soon as possible.
        self.setReadPeriod(readperiod)
        self.setSendPeriod(sendperiod)
        self.in_sql = in_sql.split('.')[0]
        self.out_sql = out_sql.split('.')[0]
        #self.s = SQLgeneral()
        self.chg_dict = {} # svc:[member,value] after the change
        self.Initialize()


    def setReadPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.readperiod = invar

    def setSendPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.sendperiod = invar


    def sqlread(self,table):
        s.sqlread(table) # restore dichannels from file


    def Initialize(self): # before using this create s=SQLgeneral()
        ''' initialize delta t variables, create tables and modbus connection '''
        self.ts = round(time.time(),1)
        self.ts_read = self.ts # time of last read
        self.ts_send = self.ts -150 # time of last reporting
        #self.conn = sqlite3.connect(':memory:')
        self.sqlread(self.in_sql) # read dichannels
        self.sqlread(self.out_sql) # read dochannels if exist
        self.ask_values() # from server


    def read_di_grp(self,mba,regadd,count,mbi=0, regtype='h'): # using self,in_sql as the table to store in.
        ''' Read sequential register group and store raw into table self.in_sql. Inside transaction! return 1 if change, 0- no chg, 2 error '''
        if self.ts == 0:
            self.ts=int(round(time.time())) # for debugging time is needed

        cur=conn.cursor()
        msg='d_grp read from mba '+str(mba)+', regadd '+str(regadd)+', count '+str(count)+', regtype '+regtype

        if count>0:
            try:
                if mb[mbi]:
                    result = mb[mbi].read(mba, regadd, count=count, type=regtype)
                    msg += ' OK, raw '+str(result)
                    if self.msgbus != None:
                        self.msgbus.publish('di_grp_result', {'mbi': mbi, 'mba': mba, 'regadd': regadd, 'result': result})
                    log.debug(msg) ##
                else:
                    msg += ' -- FAIL, no mb[] for '+str(mbi)
                    log.warning(msg)
            except:
                msg += ' -- FAILED!'
                log.warning(msg)
                traceback.print_exc()
                return 2
        else:
            msg += '-- FAIL, invalid parameter count '+str(count)
            log.warning(msg)
            return 2

        if result != None:
            try:
                for i in range(len(result)): # register values in tuple
                #for i in range(count): # tuple to table rows. tuple len is twice count!
                    # bitwise processing now - only bits not words can be saved!
                    Cmd="select bit,value from "+self.in_sql+" where mba='"+str(mba)+"' and mbi="+str(mbi)+" and regadd='"+str(regadd+i)+"' group by bit" # handle repeated bits in one go
                    #print(Cmd)
                    cur.execute(Cmd)
                    for srow in cur: # for every mba list the bits in used&to be updated
                        #print(srow) # debug
                        bit = 0
                        ovalue = 0
                        chg = 0 #  bit change flag
                        #mba and regadd are known
                        if srow[0] != '':
                            bit = int(srow[0]) # bit 0..15
                        else:
                            warning('INVALID bit in dchannels read result '+str(srow))
                        ovalue = int(eval(srow[1])) if srow[1] != '' else None # bit 0..15 old value
                        #print('old value for mbi, mba, regadd, bit',mbi,mba,regadd+i,bit,'was',ovalue) # debug

                        try:
                            value = int((result[i] & (2 ** bit)) >> bit) # new bit value
                            #print('decoded new value for mbi, mba, regadd, bit',mbi,mba,regadd+i,bit,'is',value,'was',ovalue) # debug
                        except:
                            log.warning('read_di_grp problem: result '+str(result)+', i'+str(i)+', bit'+str(bit))
                            traceback.print_exc()

                        # check if outputs must be written
                        try:
                            if value != ovalue: # change detected, update dichannels value, chg-flag  - saaks ka maski alusel!!!
                                chg = 3 # 2-bit change flag, bit 0 to send and bit 1 to process, to be reset separately
                                msg = 'DIchannel mbi.mba.reg '+str(mbi)+'.'+str(mba)+'.'+str(regadd)+' bit '+str(bit)+' change! was '+str(ovalue)+', became '+str(value) # temporary
                                log.debug(msg) ##
                                #udp.syslog(msg)
                                # dichannels table update with new bit values and change flags. no status change here. no update if not changed!
                                Cmd = "UPDATE "+self.in_sql+" set value='"+str(value)+"', chg='"+str(chg)+"', ts='"+str(self.ts)+"' where mba='"+str(mba)+"' and regadd='"+str(regadd+i)+"' and mbi="+str(mbi)+" and bit='"+str(bit)+"'"
                                # uus bit value ja chg lipp, 2 BITTI!
                            else: # no value change, just update the timestamp!
                                chg = 0
                                Cmd = "UPDATE "+self.in_sql+" set ts='"+str(self.ts)+"', chg='"+str(chg)+"' where mba='"+str(mba)+"' and mbi="+str(mbi)+" and regadd='"+str(regadd+i)+"' and bit='"+str(bit)+"'" # old value unchanged, use ts_CHG AS TS!
                            log.debug('dichannels update cmd: '+Cmd)
                            conn.execute(Cmd) # write
                        except:
                            log.warning('dichannels table update FAILED!')
                            traceback.print_exc()
                #time.sleep(0.05)
                if chg == 0: # no change
                    return 0
                else:
                    return 1 # there was change
            except:
                traceback.print_exc()
                time.sleep(0.2)
                return 2
        else: #failure, recreate mb[mbi]
            
            #log.warning('recreating modbus channel due to error on '+str(mbhost[mbi]))
            if mba == mb[mbi].get_mba_keepalive(): # recreate mb[] on access failure to this address only
                port = mb[mbi].get_port() # None if not tcp
                host = mb[mbi].get_host() # always exists, ip or /dev/tty
                serial = 0
                speed = 19200 # default
                if mb[mbi].get_host() == mb[mbi].get_port():
                    serialconf = mb[mbi].get_serial() # fails if not serial
                    serial = 1
                    speed = int(eval(serialconf.split(' ')[1])) # num needed
                    
                if serial == 0:
                    mb[mbi] = CommModbus(host = host, port = port) # tcp
                else:
                    mb[mbi] = CommModbus(host = host, speed = speed) # serial
                
                msg = 'recreated mb['+str(mbi)+'] due to read FAILURE for mbi,mba,regadd,count '+str(mbi)+', '+str(mba)+', '+str(regadd)+', '+str(count)
                if self.msg != msg:
                    self.msg = msg
                    log.warning(msg)
                time.sleep(0.5) # hopefully helps to avoid sequential error / recreations
            return 1


    def sync_di(self): # binary input readings to sqlite, to be executed regularly.
        ''' Read data from all modbus DI registers to dichannels.sql, return 0 if ok. '''
        res = 0 # returncode
        mba = 0
        val_reg = ''
        mcount = 0
        block = 0 # vigade arv
        self.ts = round(time.time(),1)
        ts_created = self.ts # selle loeme teenuse ajamargiks
        value = 0
        ovalue = 0
        Cmd = ''
        #Cmd3= ''
        cur = conn.cursor()
        #cur3 = conn.cursor()
        bfirst = -1 # register address to start with, unassigned do far
        blast = 0
        bmba = 0 # modbus address
        bmbi = 0 # modbus channel numbered from 0
        bcount = 0 # number of registers to read
        regtype = ''
        bregtype = ''

        # -- DI CONF BITS
        # 1 - value 1 = warningu (values can be 0 or 1 only)
        # 2 - value 1 = critical,
        # 4 - value inversion
        # 8 - value to status inversion
        # 16 - immediate notification on value change (whole multivalue service will be (re)reported)
        # 32 - this channel is actually a writable coil output, not a bit from the register (takes value 0000 or FF00 as value to be written, function code 05 instead of 06!)
        #     when reading coil, the output will be in the lowest bit, so 0 is correct as bit value

        try:
            Cmd = "BEGIN IMMEDIATE TRANSACTION" # hoiab kinni kuni mb suhtlus kestab? teised seda ei kasuta samal ajal nagunii. iga tabel omaette.
            conn.execute(Cmd)
            Cmd = "select mba,regadd,mbi,regtype from "+self.in_sql+" where mba != '' and regadd != '' group by mbi,mba,regtype,regadd" # tsykkel lugemiseks, tuleks regadd kasvavasse jrk grupeerida
            cur.execute(Cmd) # selle paringu alusel raw update, hiljem teha value arvutused iga teenuseliikme jaoks eraldi
            for row in cur: # find sequential group size to read
                mba = int(row[0])
                regadd = int(row[1])
                mbi = int(row[2]) # tegelt num niigi
                regtype = row[3] if row[3] != '' else 'h'
                if bfirst == -1: # unassigned so far
                    bfirst = regadd # register address to start with sequential block
                    blast = regadd
                    bcount = 1
                    bmba = mba
                    bmbi = mbi
                    bregtype = regtype
                    #print('di first group mba '+str(bmba)+' start from reg ',bfirst) # debug, count yet unknown

                else: # not the first
                    if mbi == bmbi and mba == bmba and regadd == blast+1: # next regadd found, sequential group still growing
                        blast = regadd # shift the end address
                        bcount = bcount+1 # register count to read
                        #print('di group starting from '+str(bfirst)+': end shifted to',blast) # debug
                    else: # a new group started, make a query for previous
                        #print('di group end detected at regadd',blast,'bcount',bcount) # debugb
                        #print('going to read di registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                        res = (res | self.read_di_grp(bmba,bfirst,bcount,bmbi,bregtype)) # reads and updates table with previous data. res = bitmap
                        bfirst = regadd # new grp starts immediately
                        blast = regadd
                        bcount = 1
                        bmba = mba
                        bmbi = mbi
                        bregtype = regtype
                        #print('di next group found: mba '+str(bmba)+', starting from reg ',bfirst) # debug

            if bfirst != -1: # last group yet unread
                #print('di group end detected at regadd',blast) # debugb
                #print('2going to read di registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                res = (res | self.read_di_grp(bmba,bfirst,bcount,bmbi,bregtype)) # last read / update. res = bitmap

            #  bit values updated for all dichannels

            conn.commit()  # dichannel-bits transaction end

            return res # can be 3 if some grp changed, some got error! 0 is no change, 1 is change, 2 error

        except: # Exception,err:  # python3 ei taha seda viimast
            msg = 'there was a problem with dichannels data reading or processing! '+str(sys.exc_info()[1])
            udp.syslog(msg)
            log.warning(msg)
            traceback.print_exc()
            time.sleep(1)
            return 2

    # sync_di() end. FRESHENED DICHANNELS TABLE VALUES AND CGH BITS (0 TO SEND, 1 TO PROCESS)


    def get_chg_dict(self):
        return self.chg_dict # {svc:[chgmap,valmap]}


    def make_dichannels(self, svc = ''): # chk all if svc empty
        ''' Send di svc with changed member or (lapsed sendperiod AND
            updated less than sendperiod s ago (still fresh)). ts used as update ts.
            If svc != '' then that one svc has probably been changed??
        '''
        # mask == 1: send changed, mask == 3: send all
        msg = ''
        mba = 0 # local here
        val_reg = ''
        desc = ''
        comment = ''
        mcount = 0
        ts_created = self.ts # timestamp
        #sumstatus=0 # summary status for a service, based on service member statuses
        chg = 0 # status change flag with 2 bits in use!
        value = 0
        ts_last = 0 # last time the service member has been reported to the server
        cur = conn.cursor()
        sendtuple = []
        chg_dict = {} # svc:[member,value] after the change. short lifetime!
        svccount = 0 # to be reported
        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # transaction, dichannels
            conn.execute(Cmd) # dichannels

            # dichannels(mba,regadd,bit,val_reg,member,cfg,block,value,status,ts,chg,desc,comment,ts_msg,type integer)
            if svc == '': ##  chk all di services for sending
                #Cmd="select val_reg, max((chg+0) & 1), min(ts_msg+0) from \
                #    dichannels where ((chg+0 & 1) and ((cfg+0) & 16)) or \
                #    ("+str(self.ts)+">ts_msg+"+str(self.sendperiod)+") \
                #    group by val_reg"
                Cmd = "select val_reg, sum(chg<<(member-1)), sum(value<<(member-1)) from dichannels where ((chg+0 & 1) and ((cfg+0) & 16)) or ("+str(self.ts)+">ts_msg+"+str(self.sendperiod)+") group by val_reg"
                # take into account cfg! not all changes are to be reported immediately!
                # cfg is also for application needs, not only monitoring!

                log.debug('Cmd: '+Cmd) ##
                cur.execute(Cmd)

                for row in cur: # services to be processed. either just changed or to be resent
                    svccount += 1
                    log.debug('processing di row '+str(repr(row))) ##
                    val_reg = ''
                    sta_reg = ''
                    sumstatus = 0 # initially

                    if len(row) > 0:
                        val_reg = row[0] # service name
                        chg = int(row[1]) # change bitmap by members
                        val = int(row[2]) # values bitmap by members
                        #ts_last=int(row[2]) # last reporting time
                        if chg > 0: # message due to bichannel state change
                            msg='DI service '+val_reg+' needs to be notified, new val bitmap '+str(hex(val))+', change bitmap '+str(hex(chg))
                            chg_dict.update({val_reg : [chg, val]})  #### FIXME / kahtlane , 1 asemel 3, 2 asemel 6 jne
                            log.info(msg)
                            
                        else:
                            msg='DI service '+val_reg+' unchanged: '
                        log.debug(msg)

                        sendtuple = self.make_dichannel_svc(val_reg) # for each service
                        udp.send(sendtuple)
                        msg = 'buffered within reporting all '+str(sendtuple) ####
                        log.debug(msg)
                    else:
                        log.warning('FAILED to select row for '+val_reg)

                self.chg_dict = chg_dict

            else:
                sendtuple = self.make_dichannel_svc(svc)
                if sendtuple:
                    udp.send(sendtuple)
                    msg = 'buffered due to reporting single '+str(sendtuple) ####
                    log.debug(msg)

            #if sendtuple != None and sendtuple != []:
            #    udp.send(sendtuple)
            #    msg += str(sendtuple)
            #    log.info(msg)
            #else:
            #    log.warning('empty sendtuple '+str(sendtuple)+' for svc '+svc)
            # ilmselt ei ole muutnud ega aeg korrata veel kaes

            conn.commit() # dichannels transaction end
            if svccount > 0:
                return 1
            else:
                return 0

        except:
            traceback.print_exc()
            #syslog('err: '+repr(err))
            msg='there was a problem with make_dichannels()! '+str(sys.exc_info()[1])
            log.warning(msg)
            #syslog(msg)
            return 2

    #make_dichannels() lopp




    def make_dichannel_svc(self,val_reg): # one service. find status and send away.
        ''' Find service status and return tuple of sta_reg,status, val_reg,value to be sent away.
            Execute by make_dichannels() to get transaction
           '''
        # no transaction started here because we are in transaction (started make_dichannels())
        lisa='' # value string
        values = []
        sumstatus=0 # status calc
        cur=conn.cursor()
        Cmd="select * from dichannels where val_reg='"+val_reg+"' order by member asc" # data for one service ###########
        cur.execute(Cmd)
        rowproblem = 0 # do not report service where member of type h is stalled
        
        for srow in cur: # ridu tuleb nii palju kui selle teenuse liikmeid, pole oluline milliste mba ja readd vahele jaotatud
            #print 'row in cursor3a',srow # temporary debug
            mba=0 # local here
            regadd=0
            bit=0 #
            member=0
            cfg=0
            chg=0
            ostatus=0 # previous value
            ovalue=0 # previous or averaged value
            ots=0 # previous update timestamp
            avg=0 # averaging strength, has effect starting from 2
            # 0      1   2     3      4      5     6     7     8    9     10   11   12      13     14
            #(mba,regadd,bit,val_reg,member,cfg,block,value,status,ts,chg,desc,comment,ts_msg,type integer) # dichannels
            if srow[0] != '':
                mba=int(srow[0])
            if srow[1] != '':
                regadd=int(srow[1]) # must be int! can be missing
            if srow[2] != '':
                bit=int(srow[2])
            val_reg=srow[3] #  string
            if srow[4] != '':
                member=int(srow[4])
            if srow[5] != '':
                cfg=int(srow[5]) # configuration byte
            # block?? to prevent sending service with errors. to be added!
            #if srow[7] != '':
            value = int(eval(srow[7])) if srow[7] != '' else None  # None, 0 or 1
            if srow[8] != '':
                ostatus=int(eval(srow[8])) # old status
            if srow[9] != '':
                ots=eval(srow[9]) # value ts timestamp
            if srow[10] != '':
                chg=eval(srow[10]) # change flag 0..3
            #if srow[11] != '':  # desc not needed
            if srow[12] != '':
                regtype = srow[12] # change flag 0..3

            #print 'make_dichannel_svc():',val_reg,'member',member,'value before status proc',value,', lisa',lisa  # temporary debug

            #if ots < self.ts + self.sendperiod: # stalled!
            if (regtype == 'h' or regtype == 'i'  or regtype == 'c' or regtype == 'r'): # for channel data only, not for setup values (s, s!)
                if self.ts > ots + self.sendperiod: # stalled / but not for regtype s!
                    rowproblem = 1 # do not send this svc
                    log.warning('svc '+val_reg+' member '+str(member)+' stalled for '+str(int(self.ts - ots))+' s!')
            if value == None:
                rowproblem = 1 # do not send this svc
                log.warning('svc '+val_reg+' member '+str(member)+' value None!')
                log.warning('srow '+str(repr(srow))) ##
               
            else:
                if lisa != '': # not the first member any more
                    lisa = lisa + " "

                # status and inversions according to configuration byte
                status = 0 # initially for each member
                if (cfg&4): # value2value inversion
                    value = (1^value) # possible member values 0 voi 1
                lisa += str(value) # adding possibly inverted member value to multivalue string
                values.append(value)
                
                if (cfg&8): # value2status inversion
                    value = (1^value) # member value not needed any more?

                if (cfg&1): # status warning if value 1
                    status = value #
                if (cfg&2): # status critical if value 1
                    status = 2 * value



                if status > sumstatus: # summary status is defined by the biggest member sstatus
                    sumstatus = status # suurem jaab kehtima

                log.debug(val_reg+'.'+str(member)+' value after status proc '+str(value)+', sumstatus '+str(sumstatus)+', lisa '+str(lisa))


            #dichannels table update with new chg and status values. no changes for values! chg bit 0 off! set ts_msg!
            if rowproblem == 0: # no problem with this svc members
                Cmd="UPDATE "+self.in_sql+" set ts_msg='"+str(self.ts)+"', chg='"+str(chg&2)+"' where val_reg='"+str(val_reg)+"'" # koik liikmed korraga sama ts_msg
                conn.execute(Cmd)

        sta_reg=val_reg[:-1]+"S" # service status register name
        if sta_reg == val_reg: # only status will be sent then!
            val_reg=''
            lisa=''
            values.append(status) # for msgbus
            
        if rowproblem == 0:
            if self.msgbus != None:
                self.msgbus.publish(val_reg, {'values': values, 'status': sumstatus})
            return [sta_reg, sumstatus, val_reg, lisa]  # returns tuple to send. to be send to udp.send([])
        else:
            log.warning('no sendtuple due to rowproblem')
            return None



    def sync_do(self): # synchronizes DO bits (output channels) with data in dochannels table, checking actual values via dichannels table
        # find out which do channels need to be changed based on dichannels and dochannels value differencies
        # and use write_register() write modbus registers (not coils) to get the desired result (all do channels must be also defined as di channels in dichannels table!)
        respcode=0
        mba=0 # lokaalne siin
        #omba=0 # previous value
        mbi=0
        #ombi=0
        val_reg=''
        desc=''
        value=0
        word=0 # 16 bit register value
        #comment=''
        mcount=0
        #Cmd1=''
        #Cmd3=''
        #Cmd4=''
        ts_created=self.ts # selle loeme teenuse ajamargiks
        cur=conn.cursor()
        res = 0 # returncode 0 1 2 = nochg chg error

        # coils not handled yet

        # only write the new word if at least one bits in dochannel is not equal to the corresponding bit in dichannels
        Cmd="select dochannels.mba, dochannels.regadd, dochannels.bit, dochannels.value, dichannels.value, dichannels.mbi from \
            dochannels left join dichannels on dochannels.mba = dichannels.mba AND dochannels.mbi = dichannels.mbi AND \
            dochannels.regadd = dichannels.regadd AND dochannels.bit = dichannels.bit where round(dochannels.value) != round(dichannels.value) and \
            not(dichannels.cfg & 32) group by dochannels.mbi, dochannels.mba, dochannels.regadd, dochannels.bit"  # find changes only
        # without round() 1 != 1.0 !
        #print(Cmd)
        try:
            cur.execute(Cmd)
            bit_dict={} # {bit:[do,di]}
            reg_dict={} # {reg:bit_dict}
            mba_dict={} # {mba:reg_dict)
            mbi_dict={} # {mbi: mba_dict}

            for row in cur: # for every bit, sorted by mbi, mba, regadd, bit
                tmp_array = [] # do,di bits together
                log.debug('got row about change needed from dochannels-dichannels left join %s', row)
                regadd = 0
                mba = 0
                bit = 0
                di_value = 0
                do_value = 0
                mbi = 0
                log.info('do change mba, regadd, bit '+str(int(eval(row[0])))+', '+str(int(eval(row[1])))+', '+str(int(eval(row[2])))+' from '+str(int(eval(row[4])))+' to '+str(int(eval(row[3]))))
                try:
                    mbi = row[5] if row[5] != '' else 0 # num
                    mba = int(eval(row[0])) # must be number
                    regadd = int(eval(row[1])) # must be a number. 0..255
                    bit = (int(eval(row[2]))) # bit 0..15
                    tmp_array.append(int(eval(row[3])))  # do_value=int(row[3]) # 0 or 1 to be written
                    tmp_array.append(int(eval(row[4]))) # di_value=int(row[4]) # 0 or 1 to be written
                    bit_dict.update({bit : tmp_array}) # regadd:[bit,do,di] dict member
                    reg_dict.update({regadd : bit_dict})
                    mba_dict.update({mba : reg_dict})
                    mbi_dict.update({mbi : mba_dict})

                except:
                    msg = 'failure in creating tmp_array '+repr(tmp_array)+' '+str(sys.exc_info()[1])
                    res = (res | 2)# add error bit
                    log.warning(msg)
                    #udp.syslog(msg)
                    traceback.print_exc()

                #print('sync_do mbi_dict',mbi_dict) # debug



            # nested dictionaries ready, let's process
            for mbi in mbi_dict.keys(): # this key is string!
                #print('processing mbi',mbi)
                for mba in mba_dict.keys(): # this key is string!
                    #print('processing mba',mba)
                    for regadd in reg_dict.keys(): # chk all output registers defined in dochannels table
                        try:
                            word = mb[mbi].read(mba, regadd, count = 1, type = 'h')[0]
                            #print('value of the output',mba,regadd,'before change',format("%04x" % word)) # debug
                            for bit in bit_dict.keys():
                                #print('do di bit,[do,di]',bit,bit_dict[bit]) # debug
                                word2 = s.bit_replace(word,bit,bit_dict[bit][0]) # changed the necessary bit. can't reuse / change word directly!
                                word = word2

                            try:
                                respcode = mb[mbi].write(mba, regadd, value=word)
                                if respcode == 0:
                                    msg = 'sync_do(): output written - mbi mba regadd value '+str(mbi)+' '+str(mba)+' '+str(regadd)+' '+format("%04x" % word)
                                    log.info(msg) ##
                                    res = (res | 1) # change bit
                                else:
                                    msg = 'sync_do() FAILED to write register '+str(mba)+'.'+str(regadd)+', value '+str(value)+', respcode '+str(respcode)
                                    log.error(msg)
                                    res = (res | 2) # error bit
                            except:
                                log.error('sync_do() FAILED to write mba '+str(mba)+', regadd '+str(regadd)+', value '+str(value))
                                traceback.print_exc()
                                return 2

                        except:
                            log.error('sync_do() FAILED too read mbi '+str(mbi)+', mba'+str(mba))
                            traceback.print_exc()
                            return 2

                        


        except:
            msg = 'problem with dichannel grp select in write_do_channels! '+str(sys.exc_info()[1])
            log.warning(msg)
            traceback.print_exc() # debug
            sys.stdout.flush()
            time.sleep(1)
            return 2

        conn.commit() # transaction end, perhaps not even needed - 2 reads, no writes...
        msg = 'do sync done'
        log.debug(msg)
        return res


    def parse_udp(self,data_dict): # search for setup or set di remote control signals
        ''' Setup change for variables in sql for modbus di channels. Ignore invalid parameters, not defined in self.in_sql! '''
        cur=conn.cursor()
        setup_changed = 0 # flag general setup change, data to be dumped into sql file
        msg=''
        mval=''
        res=0
        member=0
        #found = 0
        log.debug('dchannels: parsing for possible key:value data ',data_dict) # debug
        for key in data_dict: # process per key:value
            found = 0
            if key[-1] == 'W': # must end with W to be multivalue service containing setup values FIXME! 's!' needed instead!
                valmembers=data_dict[key].split(' ') # convert value to member list
                for valmember in range(len(valmembers)): # 0...N-1
                    Cmd="select mba,regadd,val_reg,member,value,regtype from "+self.in_sql+" where val_reg='"+key+"' and member='"+str(valmember+1)+"'"
                    cur.execute(Cmd)
                    #conn.commit()
                    for row in cur:
                        found += 1
                        #print('srow:',row) # debug
                        sqlvalue=int(row[4]) if row[4] != '' else 0 # eval(row[4]) if row[4] != '' else 0 #
                        try:
                            value=eval(valmembers[valmember])
                        except:
                            value = sqlvalue # no change!
                            #log.warning('invalid value in message from server for key '+key)

                        regtype=row[5] # 'h' 'i' 's!'

                        if (sqlvalue != value and regtype == 's!'): # ok to change value
                            # replace actual counters only if bigger than existing or zero, no limits for setup type 's!'
                            member=valmember+1

                            if (row[0] == '' and row[1] == ''): # mba, regadd
                                if self.set_divalue(str(key),member,value) == 0: # set setup value in sql table
                                    msg='di setup changed for key '+key+', member '+str(member)+' to value '+str(value)
                                    setup_changed=1
                                    log.info(msg)
                                    #udp.syslog(msg)
                                else:
                                    msg='svc member setting problem for key '+key+', member '+str(member)+' to value '+str(value)
                                    log.warning(msg)
                                    #udp.syslog(msg)
                                    res+=1
                            else:
                                msg='dchannels.parse_upd: setup value cannot have mba,regadd defined!'
                                log.warning(msg)
                                #udp.syslog(msg)
                                res+=1

                        else: # skip
                            log.warning('member value write for key '+key+' SKIPPED due to sqlvalue '+str(sqlvalue)+', value '+str(sqlvalue)+', regtype '+regtype)

                conn.commit()
                #if setup_changed == 1: # no need to dump di, too much dumping. ask di states after reboot, if regtype == 's!'
                #    print('going to dump table',self.in_sql)
                #    try:
                #        s.dump_table(self.in_sql)
                #    except:
                #        print('FAILED to dump table',self.in_sql)
                 #       traceback.print_exc() # debug
            #if res == 0:
                #self.read_all() # reread the changed channels to avoid repeated restore - no need

            #if found > 0:
            if setup_changed > 0:
                log.info('reporting due to di setup change (no dumping to '+self.in_sql+' though) '+key)
                self.make_dichannels(key) # notification needed changed or not, to confirm the state after chg trial
        return res # kui setup_changed ==1, siis todo = varlist! aga kui samal ajal veel miski ootel?


    def set_divalue(self,svc,member,value): # sets binary variables within services for remote control, based on service name and member number
        ''' Setting member value using sqlgeneral set_membervalue. adding sql table below for that '''
        return s.set_membervalue(svc,member,value,self.in_sql)

    def set_dovalue(self,svc,member,value): # sets binary variables within services for remote control, based on service name and member number
        ''' Setting member value using sqlgeneral set_membervalue. adding sql table below for that '''
        log.info('writing output bit for '+svc+'.'+str(member)+' to become '+str(value))
        return s.setby_dimember_do(svc, member, value) # s.set_membervalue(svc,member,value,self.out_sql)

    def set_doword(self,mba,regadd,value,mbi=0): # sets holding register without services involvment
        ''' Setting holding register (like pwm channel for pulse or pwm) '''
        log.info('writing output register mba '+str(mba)+' with word '+str(hex(value)))
        return mb[mbi].write(mba, regadd, value = value)

    def get_doword(self,mba,regadd,count=1,mbi=0): # returns list!
        ''' Returns holding register values as list '''
        return mb[mbi].read(mba, regadd, count = 1, type='h')

    def set_dowords(self,mba,regadd,values,mbi=0): # sets holding register without services ivolvment
        ''' Setting holding registwer (like pwm channel for pulse or pwm) '''
        return mb[mbi].write(mba, regadd, values = values) # values must be list

    def ask_values(self): # from server, use on init and conn up, send ? to server if value type = 's!'
        ''' Queries last known service (multi)value from the server '''
        Cmd="select val_reg,max(cfg) from "+self.in_sql+" where regtype='s!' group by val_reg"
        #print "Cmd=",Cmd
        cur=conn.cursor()
        cur.execute(Cmd) # getting services to be read and reported
        for row in cur: # possibly multivalue service members
            val_reg=row[0]
            sta_reg=val_reg[:-1]+'S' # status
            log.info('trying to restore value from server for '+val_reg)
            udp.send([sta_reg,1,val_reg,'?']) # udp.udpsend(val_reg+':?\n') # ask last value from uniscada server.
        conn.commit()
        return 0


    def get_divalue(self,svc,member): # returns value based on di service name and member number
        ''' Returns di channel value as integer '''
        #Cmd3="BEGIN IMMEDIATE TRANSACTION" # conn3, et ei saaks muutuda lugemise ajal
        #conn3.execute(Cmd3)
        Cmd = "select value from dichannels where val_reg='"+svc+"' and member='"+str(member)+"'"
        cur = conn.cursor()
        cur.execute(Cmd)
        value = None
        found = 0
        for row in cur: # should be one row only
            log.debug('get_divalue row: '+str(repr(row))) # debug
            found = 1
            value = int(float(row[0])) if row[0] != '' and row[0] != None else 0
        if found == 0:
            msg = 'get_divalue failure, no member '+str(member)+' for '+svc+' found!'
            log.warning(msg)

        conn.commit()
        return value # also state and value should be important! like ac.get_aivalue does...

    def get_divalues(self,svc): # returns values based on di service name as []
        ''' Returns di channel values as integer list '''
        #Cmd3="BEGIN IMMEDIATE TRANSACTION" # conn3, et ei saaks muutuda lugemise ajal
        #conn3.execute(Cmd3)
        Cmd = "select value from dichannels where val_reg='"+svc+"'"
        cur = conn.cursor()
        cur.execute(Cmd)
        values = []
        found = 0
        for row in cur: # should be one row only
            log.debug('get_divalue row: '+str(repr(row))) # debug
            found = 1
            values.append(int(float(row[0])) if row[0] != '' and row[0] != None else None) ## FIXME kasuta None ka mujal?
        if found == 0:
            msg = 'get_divalue failure, no member values  for '+svc+' found!'
            log.warning(msg)

        conn.commit()
        return values


    def doall(self): # do this regularly
        ''' Does everything on time if executed regularly '''
        res = [2, 2, 2] # returncodes list
        self.ts = round(time.time(),1)
        if self.ts - self.ts_read>self.readperiod:
            self.ts_read = self.ts
            try:
                res[0] = self.sync_di() # 0 1 2 = nochg, dichg, error
                res[1] = self.sync_do() # 0 1 2 = nochg, dochg, error
                res[2] = self.make_dichannels() # 0 1 2 = nobuff, somebuff, error
            except:
                traceback.print_exc()
        return res # list of what was done
