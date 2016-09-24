# This Python file uses the following encoding: utf-8

#to be imported into modbus_sql. needs mb and conn
'''  Creates multiple modbus access channels for various access channels defined in devices.sql.
    Also creates communication channel to uniscada server, statekeeper and gpioled instances.
 '''

import time, datetime
import sqlite3
import traceback
#import os
import sys
from pymodbus import *
from droidcontroller.comm_modbus import CommModbus  # contains CommModbus, .read(), .write()
from droidcontroller.uniscada import UDPchannel, TCPchannel
    
import logging
log = logging.getLogger(__name__)

try:
    if udp:
        log.info('uniscada connection already existing to '+host+':'+str(port))
except:
    udp = UDPchannel()
    log.info('created uniscada UDP connection instance')
    tcp = TCPchannel()
    log.info('created uniscada TCP connection instance')


try:
    if conn:
        log.debug('sqlite connection already existing')
except:
    conn = sqlite3.connect(':memory:')
    log.info('created sqlite connection')


try:
    if mb:
        log.debug('modbus connection(s) already existing')
except:
    # several connections may be needed, tuple of modbus connections! also direct rtu, rtu via tcp-serial or tcp-modbustcp
    for file in ['devices.sql','setup.sql']: # channel tables opened by dchannels or acchannels
        sql = open(file).read() # (num integer,rtuaddr integer,tcpaddr)
        log.info('reading file ' + file)
        try:
            conn.executescript(sql) # read table into database
            conn.commit()
            log.info('created table from file ' + file)
        except:
            log.error('creating table from file ' + file + ' FAILED!')
            traceback.print_exc()

    mb = [] # modbus comm instance
    #mbhost=[] # tcp or tty
    Cmd = "select mbi, tcpaddr from devices group by mbi"
    cur = conn.cursor()
    cur.execute(Cmd)
    conn.commit()
    for row in cur:
        if ':' in row[1]: # over tcp
            mb.append(CommModbus(host=row[1].split(':')[0], port=int(row[1].split(':')[1]), name='mbi_'+str(row[0]))) # modbustcp over tcp
        elif '|' in row[1]: # serial with speed and parity defined
            parity = 'E'
            if len(row[1]) == 3:
                parity = row[1].split('|')[2] if row[1].split('|')[2] == 'N' or row[1].split('|')[2] == 'O' else 'E' # must be N or E or O
            mb.append(CommModbus(host=row[1].split('|')[0], speed=int(row[1].split('|')[1]), parity = parity, name='mbi_'+str(row[0]))) # modbustcp over tcp
        else: # serial in default configuration 19k2 8E1
            mb.append(CommModbus(host=row[1], speed=19200, name='mbi'+str(row[0]))) # probably olinuxino serial. speed, parity in comm_modbus
    log.info('opened setup, devices tables and created '+str(len(mb))+' modbus connection(s)')



class SQLgeneral(UDPchannel): # parent class for ACchannels, Dchannels
    ''' Access to io by modbus slave/register addresses and also via services. modbus client must be opened before.
        able to sync input and output channels and accept changes to service members by their sta_reg code
    '''
    def __init__(self): # , host = '127.0.0.1', port = 502):
        try: # is it android? using modbustcp then
            import android
            droid = android.Android()
            from android_context import Context
            import android_network # android_network.py and android_utils.py must be present!
            import os.path
            self.OSTYPE='android'
            import BeautifulSoup # ? 
            import termios
            msg = 'running on android, current directory '+os.getcwd()
            log.info(msg)
            udp.syslog(msg)

        except: # some linux
            import os
            if 'ARCH' in os.environ: # uname()[2]:  # olinuxino
                self.OSTYPE='archlinux'
                log.info('running on archlinux')
                #os.chdir('/root/d4c') # OLINUXINO
                #from droidcontroller.webserver import WebServer

            elif 'techbase' in os.environ: # : # npe, backgroundis ei ole kattesaadav!!!
                self.OSTYPE='techbaselinux'
                # kumb (rtu voi tcp) importida, on maaratud devices tabeliga!

            else: # ei ole ei android, arch ega techbase
                self.OSTYPE='linux' # generic
                log.info('running on generic linux')   # sql failid olgu jooksvas kataloogis



    def set_apver(self, APVER):
        ''' Sets application version for reporting '''
        self.APVER = APVER


    def print_table(self, table, column = '*'):
        ''' reads and returns he content of the table '''
        output = []
        Cmd ="SELECT "+column+" from "+table
        cur = conn.cursor()
        cur.execute(Cmd)
        conn.commit()
        for row in cur:
            output.append(row)
        return output


    def dump_table(self, table):
        ''' Writes a table into SQL-file '''
        msg = 'going to dump '+table+' into '+table+'.sql'
        log.info(msg)
        try:
            with open(table+'.sql', 'w') as f:
                for line in conn.iterdump(): # see dumbib koik kokku!
                    if table in line: # needed for one table only! without that dumps all!
                        f.write('%s\n' % line)
            return 0
        except:
            msg = 'FAILURE dumping '+table+'! '+str(sys.exc_info()[1])
            log.warning(msg)
            #syslog(msg)
            traceback.print_exc()
            return 1


    def test_mbread(self, mba, reg, count = 1, mbi=0): # mbi only defines mb[] to be used
        return mb[mbi].read(mba,reg,count)


    def sqlread(self, table): # drops table and reads from file <table>.sql that must exist
        sql=''
        filename = table+'.sql' # the file to read from
        try:
            sql = open(filename).read()
            msg = 'found '+filename
            log.info(msg)
        except:
            msg = 'FAILURE in opening '+filename+': '+str(sys.exc_info()[1])
            log.warning(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1

        Cmd='drop table if exists '+table
        try:
            conn.execute(Cmd) # drop the table if it exists
            conn.commit()
            conn.executescript(sql) # read table into database
            conn.commit()
            msg = 'sqlread: successfully recreated table '+table
            log.info(msg)
            #udp.syslog(msg)
            return 0

        except:
            msg = 'sqlread() problem for '+table+': '+str(sys.exc_info()[1])
            log.warning(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1


    def get_setup(self, register, table = 'setup'):
        ''' Returns value for one register '''
        Cmd = "select value from "+table+" where register='"+register+"'"
        #print(Cmd) # debug
        cur.execute(Cmd)
        value = '' # string!
        for row in cur: # should be one row only
            value=row[0]
        conn.commit() # setup database
        if value == '':
            msg = 'no setup value '+register+'! using 0 instead!'
            value = '0'
            log.warning(msg) # debug
            #udp.syslog(msg)
        return value # str


    def report_setup(self): # READ and send setup data to server
        mba = 0
        reg = ''
        value = ''
        Cmd = ''
        svc_name = 'setup value'
        oldmac = ''
        sendstring = ''
        loghost = ''

        cur=conn.cursor()
        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # conn1 buff2server
            conn.execute(Cmd)

            Cmd = "select register,value from setup" # no multimember registers for setup!
            #print(Cmd4) # temporary
            cur.execute(Cmd)

            for row in cur: #
                val_reg=''  # string
                value=''  # string
                status=0 # esialgu
                #value=0

                val_reg=row[0] # muutuja  nimi
                value=row[1] # string even if number!
                log.info(' setup row: '+ val_reg +str(value))

                #if val_reg[0] == 'W' and '272' in value: # power up value for do (setup register W1.272 and so on)
                #    W272_dict.update({int(float(val_reg[1])) : int(float(value))}) # {mba:272value}
                #    print ('updated W272_dict, became',W272_dict)

                if val_reg == 'S514': # syslog ip address
                    if value == '0.0.0.0' or value == '':
                        loghost='255.255.255.255'
                        udp.setLogIP(loghost) # broadcast
                    else:
                        loghost=value
                    msg='syslog server address will be updated to 255.255.255.255'
                    log.info(msg)
                    #udp.syslog(msg)
                    if self.OSTYPE == 'archlinux':  # change the archlinux syslog destination address
                        if p.subexec(['/etc/syslog-ng/changedest.sh',loghost],0) == 0:
                            msg='linux syslog redirected to '+loghost
                        else:
                            msg='linux syslog redirection to '+loghost+' FAILED!'
                        udp.syslog(msg)
                        log.info(msg)

                sta_reg = '' # configuration data
                status = -1 # configuration data
                sendtuple = [sta_reg,status,val_reg,value] # sending service to buffer
                # print('ai svc - going to report',sendtuple)  # debug
                udp.send(sendtuple) # to uniscada instance. avoid buffer?


            conn.commit() # trans lopp

            msg='setup reported'
            log.info(msg)
            udp.syslog(msg) # log message to file
            sys.stdout.flush()
            time.sleep(0.5)
            return 0

        except: # setup reading  problem
            msg='setup reporting failure (setup reading problem) '+str(sys.exc_info()[1])
            udp.syslog(msg) # log message to file
            log.warning(msg)
            time.sleep(1)
            return 1

        #report_setup lopp#############



    def change_setup(self, register, value, table='setup'):  # if register found in table, then change value. no protection here.
        ''' If register found as service in table, then change the value. No protection here against misusage. '''
        ts = time.time()
        print('setup change of '+table+' started for', register, value)
        #Cmd="BEGIN IMMEDIATE TRANSACTION" # setup table. there may be no setup changes, no need for empty transactions
        try:
            #conn.execute(Cmd) # setup transaction start
            Cmd="update "+table+" set value='"+str(value)+"', ts='"+str(int(ts))+"' where register='"+register+"'" # update only, no insert here!
            log.debug(Cmd)
            udp.syslog(Cmd) # debug
            conn.execute(Cmd) # table asetup/setup
            conn.commit() # end transaction
            print('setup change done for',register,value)
            return 0

        except: #if not succcessful, then not a valid setup message - NO INSERT here, UPDATE ONLY!
            msg='setup change problem, the assumed setup register '+register+' not found in setup table! '+str(sys.exc_info()[1])
            log.warning(msg)
            udp.syslog(msg)

            return 1


    def channelconfig(self, table = 'setup'): # modbus slaves register writes for configuration if needed, based on setup.sql
        ''' Modbus slave register writes for configuration if needed, based on setup.sql '''
        mba = 0
        register = ''
        value = 0
        regok = 0
        mba_array = []
        cur = conn.cursor()
        try:
            #Cmd="BEGIN IMMEDIATE TRANSACTION" #
            #conn.execute(Cmd)
            Cmd="select register,value from setup"
            cur.execute(Cmd) # read setup variables into cursor

            for row in cur:
                regok = 0
                msg = 'setup record '+str(repr(row))
                print(msg)
                udp.syslog(msg)
                register=row[0] # contains W<mba>.<regadd> or R<mba>.<regadd>
                # do not read value here, can be string as well

                if '.' in register: # dot is needed
                    try:
                        mba=int(register[1:].split('.')[0])
                        regadd=int(register[1:].split('.')[1])
                        msg='going to read and set (if needed) register '+register+' at mba '+str(mba)+', regadd '+str(regadd)+' to '+format("%04x" % value)
                        regok=1
                    except:
                        msg='invalid mba and/or register data for '+register
                    print(msg)
                    udp.syslog(msg)

                    if regok == 1:
                        try:
                            if row[1] != '':
                                value=int(float(row[1])) # setup value from setup table
                            else:
                                msg='empty value for register '+register+', assuming 0!'
                                value=0
                                log.warning(msg)
                                udp.syslog(msg)

                            result = client.read_holding_registers(address=regadd, count=1, unit=mba) # actual value currently in slave modbus register
                            tcpdata = result.registers[0]
                            if register[0] == 'W': # writable
                                if tcpdata == value: # the actual value verified
                                    msg=msg+' - setup register value already OK, '+str(value)
                                    print(msg)
                                    udp.syslog(msg)
                                    #prepare data for the monitoring server
                                    #sendstring += "W"+str(mba)+"."+str(regadd)+":"+str(tcpdata)+"\n"  # register content reported as decimal
                                else:
                                    msg='CHANGING config in mba '+str(mba)+' regadd '+str(regadd)+' from '+format("%04x" % tcpdata)+' to '+format("%04x" % value)
                                    time.sleep(0.1) # successive sending without delay may cause failures!
                                    try:
                                        client.write_register(address=regadd, value=value, unit=mba) # only one regiter to write here
                                        respcode=0 #write_register(mba,regadd,value,0) # write_register sets MBsta[] as well
                                        #prepare data for the monitoring server = NOT HERE!
                                        #sendstring += "W"+str(mba)+"."+str(regadd)+":"+str(value)+"\n"  # data just written, not verified!
                                    except:
                                        msg='error writing modbus register: '+str(sys.exc_info()[1])
                                        udp.syslog(msg)
                                        print(msg)
                                        respcode=1
                                        #traceback.print_exc()
                                    if respcode != 0:
                                        msg=msg+' - write_register() PROBLEM!'
                                        time.sleep(1)
                                        #return 1 # continue with others!
                                print(msg)
                                udp.syslog(msg)
                                #sys.stdout.flush()

                            else: # readable only
                                msg='updating setup with read-only configuration data from mba.reg '+str(mba)+'.'+str(regadd)
                                log.info(msg)
                                udp.syslog(msg)
                                Cmd="update setup set value='"+str(tcpdata)+"' where register='"+register+"'"
                                conn.execute(Cmd)
                                #send the actual data to the monitoring server
                                #sendstring += "R"+str(mba)+"."+str(regadd)+":"+str(tcpdata)+"\n"  # register content reported as decimal

                        except:
                            msg=' - could not read the modbus register mba.reg '+str(mba)+'.'+str(regadd)+' '+str(sys.exc_info()[1])
                            log.warning(msg)
                            udp.syslog(msg)
                            #traceback.print_exc()
                            #syslog('err: '+repr(err))
                            time.sleep(1)
                            return 1

                        time.sleep(0.1) # delay between registers

            conn.commit()

        except:
            msg='channelconfig FAILURE, '+str(sys.exc_info()[1])
            print(msg)
            udp.syslog(msg)
            #traceback.print_exc()
            #syslog('err: '+repr(err))
        sys.stdout.flush()
        time.sleep(0.5)
        return 0


    def get_column(self, table, column, like=''): # returns raw,value,lo,hi,status values based on service name and member number
        ''' Returns member values as tuple from channel table (ai, di, counter) based on service name '''
        cur=conn.cursor()
        if like == '':
            Cmd="select "+column+" from "+table+" order by "+column
        else:
            Cmd="select "+column+" from "+table+" where "+column+" like '"+like+"' order by "+column # filter
        #print(Cmd) # debug
        cur.execute(Cmd)
        value=[]
        for row in cur: # one row per member
            #print('get_value() row:', row) # debug
            value.append(row[0])

        conn.commit()
        return value # tuple from member values


    def get_value(self, svc, table='dichannels'): # returns tuple of service values if numeric
        ''' Returns member values as tuple from channel table (ai, di, counter) based on service name '''
        cur=conn.cursor()
        #Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3, et ei saaks muutuda lugemise ajal
        #conn.execute(Cmd)
        Cmd="select value from "+table+" where val_reg='"+svc+"' order by member"
        cur.execute(Cmd)
        raw=0
        outlo=0
        outhi=0
        status=0
        found=0
        value=[]
        membervalue = None
        for row in cur: # one row per member
            #print('get_value() row:', row) # debug
            membervalue = eval(row[0]) if row[0] != '' else None
            value.append(membervalue)  # make a value tuple
        if len(value) == 0: # got nothing
            msg='get_value() failure for '+svc+' from table '+table
            log.info(msg)
            udp.syslog(msg)

        conn.commit()
        return value # tuple from member values

        
    def set_membervalue(self, svc, member, value, table, raw = False): # setting value in table based on svc and member
        ''' Sets variables like setpoints or limits to be reported within services, based on service name and member number.
            Table can be either dichannels or aicochannels. For aicochannels also raw can be set instead of value, use raw = True then!
            Must tolerate but ignore None as value. Using time.time for ts to void stalled data despite changing.
        '''
        ts = int(time.time())
        if value is None:
            log.warning('no '+table+' update due to value='+str(value)+' instead of expected num value for svc '+svc+' member '+str(member))
            return 2

        valraw = {False:'value', True:'raw'}
        
        try:
            value=str(int(round(float(value),0)))
        except:
            log.warning('NO '+table+' update due to '+valraw[raw]+' = '+str(value)+' instead of expected num for '+svc+'.'+str(member))
            return 2

        Cmd="BEGIN IMMEDIATE TRANSACTION" 
        conn.execute(Cmd)
        Cmd="update "+table+" set "+valraw[raw]+"='"+str(value)+"', ts='"+str(ts)+"' where val_reg='"+svc+"' and member='"+str(member)+"'"
        log.debug('set_membervalue cmd: '+Cmd)
        try:
            conn.execute(Cmd)
            conn.commit()
            log.info(table + ' updated with '+valraw[raw]+' = '+str(value)+' for '+svc+'.'+str(member)) ##
            return 0
        except:
            msg='set_membervalue failure: '+str(sys.exc_info()[1])
            log.warning(msg)
            traceback.print_exc()
            return 1  # update failure

            


    def setbit_do(self, bit, value, mba, regadd, mbi=0):  ## no commit here, does not work alone! use via setby_dimember_do()!
        # parameter order should be changed!!! to mbi, mba, regadd, bit. chk tartu, starman!
        '''Sets the output channel by the physical addresses (mbi,mba,regadd,bit) '''
        ts = int(time.time())
        #if mba == '' or regadd == '':
        if mba == 0 or regadd == None or mbi == None or bit == None:
            print('invalid parameters for setbit_do(), mba regadd',mba,regadd,'bit value mbi',bit,value,mbi)
            time.sleep(2)
            return 2

        Cmd="update dochannels set value = '"+str(value)+"', ts='"+str(ts)+"' where mba='"+str(mba)+"' and mbi="+str(mbi)+" and regadd='"+str(regadd)+"' and bit='"+str(bit)+"'"
        #print(Cmd) # debug
        try:
            conn.execute(Cmd)
            conn.commit()
            msg='output bit '+str(bit)+' set to '+str(value)+' in table dochannels, mba '+str(mba)+', mbi '+str(mbi)
            log.info(msg)
            #udp.syslog(msg)
            return 0
        except:
            msg='output bit '+str(bit)+' setting to '+str(value)+' in table dochannels FAILED! '+str(sys.exc_info()[1])
            log.warning(msg)
            #udp.syslog(msg)
            return 1


    def getbit_do(self, mbi, mba, regadd, bit):  # to set a readable output channel by the physical addresses
        ''' Reads the wanted output channel value by the physical addresses (mbi,mba,regadd,bit) '''
        value = None
        if mba == 0 or regadd == None or mbi == None or bit == None:
            print('invalid parameters for getbit_do(), mba regadd',mba,regadd,'bit value mbi',bit,value,mbi)
            time.sleep(2)
            return 2

        Cmd="select value from dochannels where mba='"+str(mba)+"' and mbi="+str(mbi)+" and regadd='"+str(regadd)+"' and bit='"+str(bit)+"'"
        #print(Cmd) # debug
        try:
            cur.execute(Cmd)
            conn.commit()
            for row in cur: # single row
                value=int(row[0]) if row[0] != '' else 0
            return value
        except:
            msg='output bit '+str(bit)+' setting to '+str(value)+' in table dochannels FAILED! '+str(sys.exc_info()[1])
            print(msg)
            udp.syslog(msg)
            return None


    def setby_dimember_do(self, svc, member, value): # to set an output channel in dochannels by the DI service name and member (defined in dichannels)
        '''Sets  output channel by the service name and member using service name defined for this output in dichannels table '''
        ##make it complain if dochannels misconfigured! or better test it in the beginning once...
        if value == None or value > 1 or value < 0:
            log.warning('INVALID value for setby_dimember_do(): '+str(value))
            return 2
            
        cur=conn.cursor()
        #Cmd="BEGIN IMMEDIATE TRANSACTION" # conn, et ei saaks muutuda lugemise ajal
        #conn.execute(Cmd)
        Cmd="select mba,regadd,bit,mbi from dichannels where val_reg='"+svc+"' and member='"+str(member)+"'"
        cur.execute(Cmd)
        conn.commit()
        #log.info(Cmd +' done') ##
        
        mba=None
        reg=None
        bit=None
        mbi=0
        found = 0
        for row in cur: # should be one row only
            #log.info('setby_dimember row '+str(repr(row))) ##
            found =1 
            try:
                value = (value & 1) # only 0 or 1 allowed
                mba = int(row[0]) if row[0] != '' else 0 # flag illegal if 0
                reg = int(row[1]) if row[0] != '' else None
                bit = int(row[2]) if row[0] != '' else None
                mbi = int(row[3]) if row[0] != '' else None
                if mba > 0:
                    res = self.setbit_do(bit,value,mba,reg,mbi=mbi) # sets using physical channel parameters
                    #log.info('setbit_do result '+str(res)+', params ' +str((bit,value,mba,reg,mbi))) ##
                else:
                    log.warning('invalid parameters for setby_dimember_do()? '+str((bit,value,mba,reg,mbi)))
                    return 1
                
                if res == 0: # ok
                    log.info('setbit_do() done with params bit,value,mba,reg,mbi '+str((bit,value,mba,reg,mbi))+' based on svc '+svc+'.'+str(member))
                    return 0
                else:
                    log.warning('setby_dimember_do: could not get returncode 0 from setbit_do() with params bit,value,mba,reg,mbi '+str(bit,value,mba,reg,mbi))
                return 1
            except:
                msg='setbit_do FAILED for bit '+str(bit)+'!'
                log.warning(msg)
                udp.syslog(msg)
                traceback.print_exc() # debug
                return 1
        if found == 0:
            log.warning('NO match in dichannels for '+Cmd)


    def bit_replace(self, word, bit, value): # changing word with single bit value
        ''' Replaces bit in word. Examples:
            #bit_replace(255,7,0) # 127
            #bit_replace(0,15,1) # 32k
            #bit_replace(0,7,1) # 128
        '''
        #print('bit_replace var: ',format("%04x" % word),bit,value,format("%04x" % ((word & (65535 - 2**bit)) + (value<<bit)))) # debug
        return ((word & (65535 - 2**bit)) + (value<<bit))


    def check_setup(self, table):
        ''' Looks for conflicts in sql tables and prints the channels defined '''
        cur=conn.cursor()
        dev_dict={}
        tmp_array=[]
        bad=0
        #Cmd="select mbi,rtuaddr as mba,tcpaddr as host,name from devices order by mbi,mba"
        Cmd="select mbi,rtuaddr as mba from devices order by mbi,mba"
        cur.execute(Cmd)
        mbi=-1
        for row in cur:
            if row[0] != mbi:
                tmp_array=[]
            mbi=row[0]
            tmp_array.append(int(row[1])) # slaves on this mb channel
            dev_dict.update({mbi : tmp_array})
        print('defined in devices (mbi:mba)',dev_dict)

        Cmd="select mbi,mba,regadd,val_reg,member,regtype from "+table+" where mba+0>0 group by mbi,mba,regadd"
        #print(Cmd) # di korral bit eristust ei toimu, reeglina reg 0 ja 1!

        cur.execute(Cmd)
        for row in cur:
            if row[0] in dev_dict: # mbi in keys
                if int(row[1]) in dev_dict[row[0]]: # mba
                    print('channel mbi,mba,regadd,register,member,regtype '+str(row[0])+','+str(row[1])+','+str(row[2])+','+str(row[3])+','+row[4]+','+row[5]+' correctly defined in '+table)
                else:
                    bad=1
                    print('channel mbi '+str(row[0])+' in '+table+' NOT found in devices!')
            else:
                bad=2
                print('channel mbi '+str(row[0])+' in '+table+' NOT found in devices!')
        return bad
        
        
    def pic_update(self, mba = 1, mbi = 0, filename = ''):
        ''' Updates pic firmware via modbus writes of hex lines into reg 698 '''
        from droidcontroller.pic_update import PicUpdate # et ilmaaegu ei tolgendaks
        pic = PicUpdate(mb)
        #mba = int(float(mba)) # igaks juhuks, kui ei ole int
        return pic.update(int(mba), int(mbi), filename)