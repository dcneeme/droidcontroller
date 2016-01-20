# lighting control listening services from msgbus and publishing new services to mgsbus

from droidcontroller.util_n import UN # for val2int()
from droidcontroller.statekeeper import StateKeeper

import traceback, time
import logging
log = logging.getLogger(__name__)

class DO(object): # parent for Lamp instances 
    def __init__(self, mbi=0, mba=1, reg=0, bits=[8,9,10,11,12,13,14,15])
        


##############
class Lamp(object): # one instance per floor loop. no d or ac needed, just msgbus!
    def __init__(self, d, msgbus=None, in_svc={'K1W':[(1,1), (2,1)], 'KAW':[(1,3)], 'DKS':[(1,19)], 'DAS':[(1,6)], 'LAS':[(1,5)]}, 
            out_svc=['DOV',1], name = 'undefined', timeout = None, out = 0): # timeout in s
        #K1W like a switch, KAW like a pir, DAS like dim all, LAS like light all
        ''' 
        Virtual lamp that controls the actual io output channel, via level or dimmer pulse or (TBD) dali command.
        Input svc may present level or transition (define the change direction). 
        In order to mix manual and automated control, the levels should not be generally followed directly. 
        It is better to use transitions, to avoid conficts between inputs channels and enable multi-input control. 
        
        Presence sensors may be used to swith on or off (via timeout) if such services are defined.
        
        There may be several input services with similar or different properties. Define as list of lists.
        in_svc = {svc:[(member,mtype), ], } # mtype 1 invbyup, 2 invbydn, 3 invbyboth, 
                                               5 upbyup, 6 upbydn, 7 upbyboth
                                               9 followhi, 10 followlo, 11 followboth
       
        out_svc = svc, member. level!
                                               
    
        TESTING
        python
        from droidcontroller.msgbus import *; from droidcontroller.lamp import *
        msgbus=MsgBus(); lamp=Lamp(msgbus)
        lamp.inproc('KAW',[1]); lamp.get_state()
        '''
        self.name = name
        self.d = d # dchannels instance
        self.in_svc = in_svc # dict of lists
        self.out_svc = out_svc # one svc only
        self.invars = {} # keep the input states in memory for each svc : [members]
        self.msgbus = msgbus
        if msgbus:
            self.msgbus = msgbus
            for svc in self.in_svc:
                log.info('subscribing to '+svc)
                self.msgbus.subscribe('in_'+self.name+'_'+svc, svc, 'lights', self.listen_proc) # several members per svvc may have values & types
                currvalues = []
                for i in range(len(self.in_svc[svc])):
                    #print(i, svc)
                    currvalues.append(None) # until replaced by values (from msgbus)
                self.invars.update({svc: currvalues})
            if len(self.in_svc) != len(self.invars):
                log.error('in_svc and invars len do not match for lamp '+self.name+'! invars: '+str(self.invars))
        else:
            low.warning('no msgbus in use...')
            
        self.darktime = False # presence sensors to activate ligths disabled
        self.out = out # lamp state on program start. None for no change!
        log.info('instance '+self.name+' created, in_svc '+str(self.in_svc)+', invars '+str(self.invars))

    def get_state(self):
        ''' Returns current output state 0 or 1 (latter is active). '''
        return self.out
    
    def listen_proc(self, token, subject, message):
        ''' Returns the value of received service member '''
        log.info('lamp received from msgbus for '+self.name+':'+subject+', '+str(message))
        values = message['values'] # member index starting from 0
        self.inproc(subject, values)
      
      
        
    def inproc(self, svc, values): # example ('DI1W', [0, 0, 0, 0, 0, 0, 0, 0])
        ''' Processes the lamp inputs service received  ''' 
        with open('inproc.log', 'a') as handle: # ei logi msgbus teate puhul???
            handle.write('processing svc '+svc+' values '+str(values) + '\n')
            
        out = None # peaks lugema tegelikku! msgbus kaudu kuula ka seda!
        #print('svc, values',svc, values, 'self.out',self.out) ##
        if not isinstance(svc, str):
            log.error('invalid svc (must be str) '+str(svc))
            return None
        if not isinstance(values, list): # 'list' in str(type(values)):
            log.error('invalid values (must be list) '+str(values))
            return None
           
        log.info('processing svc '+svc+' values '+str(values))
        print('processing svc '+svc+' values '+str(values)) ##
        currvalues = self.invars[svc] # value list for one svc
        memstypes = self.in_svc[svc]  # members and types for this input service as list of tuples
        for im in range(len(self.invars[svc])): # im = input member of interest in configuration, not all in svc
            member = memstypes[im][0]
            mtype = memstypes[im][1]
            mvalue = values[member - 1]
            log.info('in_svc im '+str(im)+' member '+str(member)+', mtype '+str(mtype)+', mvalue '+str(mvalue))
            if mvalue != currvalues[im]:
                currvalues[im] = mvalue
                log.info(svc+'.'+str(member)+' mvalue '+str(mvalue)+', im '+str(im)+', new currvalues[im] '+str(currvalues[im]))
                print(svc+'.'+str(member)+' mvalue '+str(mvalue)+', im '+str(im)+', new currvalues[im] '+str(currvalues[im])) ##
                #processing according to the mtype    
                ## manual switches, bits 0..1
                if mtype == 1:
                    if mvalue == 1:
                        out = (self.out ^ 1)
                elif mtype == 2:
                    if mvalue == 0:
                        out = (self.out ^ 1)
                elif mtype == 3:
                    out = (self.out ^ 1)
                ## pir sensors, bitvalue 4 to flag
                if self.darktime == 1: # presence signals to activate light enabled (disactivate always operational it timeout)
                    if mtype == 5:
                        if mvalue == 1:
                            out = 1
                    elif mtype == 6:
                        if mvalue == 0:
                            out = 1
                    elif mtype == 7:
                        out = 1
                
            ## level control without change, bitvalue 8 to flag
            if mtype == 9:
                if mvalue == 1:
                    out = 1
            elif mtype == 10:
                if mvalue == 0:
                    out = 0
            elif mtype == 11:
                out = mvalue
            
            ## darktime sensor
            if mtype == 17:
                if mvalue == 1:
                    self.darktime = 1
            elif mtype == 18:
                if mvalue == 0:
                    self.darktime = 0
            if mtype == 19: # dark time depends on di level
                self.darktime = mvalue
                
        self.invars.update({svc: currvalues}) #remember the new valuelist
            
        if out != None:
            if out != self.out:
                #print('out change from '+str(self.out)+' to '+str(out))
                log.info('lamp out change to '+str(out)+', to svc '+str(self.out_svc[0])+'.'+str(self.out_svc[1]))
                print('lamp out change to '+str(out)+', to svc '+str(self.out_svc[0])+'.'+str(self.out_svc[1]))
                with open('inproc.log', 'a') as handle: # ei logi msgbus teate puhul???
                    handle.write('lamp out change to '+str(out)+', to svc '+str(self.out_svc[0])+'.'+str(self.out_svc[1])+ '\n')
                self.d.set_dovalue(self.out_svc[0], self.out_svc[1], out) # svc, member, value
                self.out = out
            #if self.msgbus:
            #    self.msgbus.publish(self.out_svc[0], {'values': [self.out], 'status': 0}) # 
            # liikme kaupa msgbus kaudu paha tegutseda...
            
        return out    
            
            
