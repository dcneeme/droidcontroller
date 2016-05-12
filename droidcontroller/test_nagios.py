# test_nagios.py 
# python -m unittest -v test_nagios
import logging
try:
    import chromalog # colored
    chromalog.basicConfig(level=logging.INFO, format='%(name)-30s: %(asctime)s %(levelname)s %(message)s')
except: # ImportError:
    logging.basicConfig(format='%(name)-30s: %(asctime)s %(levelname)s %(message)s') # 30 on laius
    print('warning - chromalog and colorama probably not installed...')

log = logging.getLogger(__name__)

import unittest
import inspect

from nagios import *
# sendtuple = ['sta_reg',status,'val_reg','value']


class NagiosTests(unittest.TestCase):
    def setUp(self):
        self.n = NagiosMessage('host_dummy', debug_svc = True)

        # convert(sendtuple, multiperf, multivalue, svc_name='SvcName', out_unit='mm', conv_coef='1', desc='description:'):
    def test_statusonly(self):
        name=inspect.stack()[0][3]
        self.assertIsNotNone(self.n.convert(['D2S',2,'',''], [''], [''], conv_coef='', svc_name=name, desc=name), None)
        print(self.n.convert(['D2S',2,'',''], [''], [''], conv_coef='', svc_name=name, desc=name))
        self.assertIsNotNone(self.n.convert(['D2S',2,'',''], [''], [''], conv_coef='1', svc_name=inspect.stack()[0][3] ), None)
        self.assertIsNotNone(self.n.convert(['D2S',2,'',''], [], [], conv_coef='', svc_name=name, desc=name ), None)
        self.assertIsNotNone(self.n.convert(['D2S',2,'',''], [], [], conv_coef=None, svc_name=name, desc=name ), None)
        print(self.n.convert(['D2S',2,'',''], [], [], conv_coef=None, svc_name=name, desc=name ))
        
    def test_string(self):
        name=inspect.stack()[0][3]
        self.assertIsNotNone(self.n.convert(['D2S',0,'D2V','jura pura'], [''], [''], conv_coef='', svc_name=name, desc=name), None)
        print(self.n.convert(['D2S',0,'D2V','jura pura'], [''], [''], conv_coef='', svc_name=name, desc=name))
        
    def test_singlevalue(self):
        name=inspect.stack()[0][3]
        self.assertIsNotNone(self.n.convert(['D2S',0,'D2V','123'], [''], [''], conv_coef='1', svc_name=name, desc=name+':'), None)
        print(self.n.convert(['D2S',0,'D2V','123'], [''], [''], conv_coef='1', svc_name=name, desc=name+':'))
        
        self.assertIsNotNone(self.n.convert(['D2S',0,'D2V','123'], [''], ['1'], conv_coef='1', svc_name=name, desc=name+':'), None)
        print(self.n.convert(['D2S',0,'D2V','123'], [''], ['1'], conv_coef='1', svc_name=name, desc=name+':'))
        
        self.assertIsNotNone(self.n.convert(['D2S',0,'D2V','123'], [''], [''], conv_coef='', svc_name=name, desc=name+':'), None)
        print(self.n.convert(['D2S',0,'D2V','123'], [''], [''], conv_coef='', svc_name=name, desc=name+':'))
        
        
        
    def test_multivalue(self):
        name=inspect.stack()[0][3]
        self.assertIsNotNone(self.n.convert(['D2S',0,'D2W','0 0 0 0 0 0 0 0'], ['d1','d2','d3','d4','d5','d6','d7','d8'], ['1', '2'], conv_coef='1', svc_name=name, desc=name+':'), None)
        print(self.n.convert(['D2S',0,'D2W','0 0 0 0 0 0 0 0'], ['d1','d2','d3','d4','d5','d6','d7','d8'], ['1', '2'], conv_coef='1', svc_name=name, desc=name+':'))
        self.assertIsNotNone(self.n.convert(['D2S',0,'D2W','0 0 0 0 0 0 0 0'], ['d1','d2','d3','d4','d5','d6','d7','d8'], [''], conv_coef='1', svc_name=name, desc=name+':'), None)
        self.assertIsNotNone(self.n.convert(['D2S',0,'D2W','0 0 0 0 0 0 0 0'], ['d1','d2','d3','d4','d5','d6','d7','d8'], ['1', '2'], conv_coef='', svc_name=name, desc=name+':'), None)
        
    def test_illegal(self):
        name=inspect.stack()[0][3]
        pass  #