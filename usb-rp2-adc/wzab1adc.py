# MicroPython USB WZab1 ADC module
# MIT license; Copyright (c) 2024 Wojciech Zabolotny
# Based on examples from 
# https://github.com/projectgus/micropython-lib/tree/feature/usbd_python/micropython/usb
# MIT license; Copyright (c) 2023 Paul Hamshere, 2023-2024 Angus Gratton
#
# The module implements the ADC converter collects the data with the 
# programmed frequency from the selected ADC inputs.
#
# There are three control requests for that:

REQ_ADC_MASK = const(0x12)
REQ_ADC_PERIOD = const(0x14)
REQ_ADC_START = const(0x13)
REQ_ADC_STOP = const(0x15)

_EP_IN_FLAG = const(1 << 7)

import struct
import array
from micropython import schedule
from usb.device.impl import Interface, Buffer, split_bmRequestType
from machine import ADC, Pin, Timer

# Control transfer stages
_STAGE_IDLE = const(0)
_STAGE_SETUP = const(1)
_STAGE_DATA = const(2)
_STAGE_ACK = const(3)

# Request types
_REQ_TYPE_STANDARD = const(0x0)
_REQ_TYPE_CLASS = const(0x1)
_REQ_TYPE_VENDOR = const(0x2)
_REQ_TYPE_RESERVED = const(0x3)

# Let's define our requests


class WZab1Interface(Interface):
    # Base class to implement a USB WZab1 device in Python.
    
    def __init__(self,txlen=300):
        super().__init__()
        self.ep_in = None # TX direction (device to host)
        self._tx = Buffer(txlen)
        self.dummy = bytearray(2)
        self.adc_mask = bytearray(5)
        self.adc_period = bytearray(4)
        self.tim = None
        self.chans = []
        self.cur_chan = 0

    def _tx_xfer(self):
        # Keep an active IN transfer to send data to the host, whenever
        # there is data to send.
        if self.is_open() and not self.xfer_pending(self.ep_in) and self._tx.readable():
            self.submit_xfer(self.ep_in, self._tx.pend_read(), self._tx_cb)

    def _tx_cb(self, ep, res, num_bytes):
        #print(num_bytes,self._tx._n)
        if res == 0:
            self._tx.finish_read(num_bytes)
        self._tx_xfer()
        
    def on_interface_control_xfer(self, stage, request):
        
        bmRequestType, bRequest, wValue, wIndex, wLength = struct.unpack("BBHHH", request)

        recipient, req_type, _ = split_bmRequestType(bmRequestType)
        print("Interface CTRL:", bmRequestType, bRequest, wValue, wIndex, wLength, recipient, req_type)
        if stage == _STAGE_SETUP:
            if req_type == _REQ_TYPE_CLASS:
                if bRequest == REQ_ADC_START:
                   self.adc_start()
                   return self.dummy
                if bRequest == REQ_ADC_STOP:
                   self.adc_stop()
                   return self.dummy                  
                if bRequest == REQ_ADC_MASK:
                   return self.adc_mask
                if bRequest == REQ_ADC_PERIOD:
                   return self.adc_period
            return False  # Unsupported
        if stage == _STAGE_DATA:
                   return True        
        return True  # allow DATA/ACK stages to complete normally        

    def desc_cfg(self, desc, itf_num, ep_num, strs):
        strs.append("WZADC1")
        desc.interface(itf_num, 1, iInterface = len(strs)-1)
        self.ep_in = (ep_num) | _EP_IN_FLAG
        desc.endpoint(self.ep_in,"bulk",64,0)
                
    def num_itfs(self):
        return 1
        
    def num_eps(self):
        return 2

    def on_open(self):
        super().on_open()
        # kick off any transfers that may have queued while the device was not open
        self._tx_xfer()

    # Servicing the ADC
    def adc_start(self):
        period = struct.unpack("<L",self.adc_period)[0]
        #Create list of channels
        a = self.adc_mask
        adc_pins = [Pin(26), Pin(27), Pin(28), Pin(29), ADC.CORE_TEMP] 
        chans = [adc_pins[i] for i,v in enumerate(a) if a[i]>0]
        self.chans = chans
        self.cur_chan = 0
        b = [0 for i in chans]
        self.adc_vals = array.array('H',b)
        self.adc_pack = "<"+str(len(b))+"H"
        self.adc = ADC(chans[0])
        self.tim = Timer()
        self.tim.init(period=period, mode=Timer.PERIODIC, callback=self.adc_sample)

    def adc_stop(self):
        self.tim.deinit()
    
    def adc_sample(self,_):
        i = self.cur_chan
        self.adc_vals[i] = self.adc.read_u16()
        if i == len(self.chans)-1:
            res = struct.pack(self.adc_pack,*self.adc_vals)
            self._tx.write(res)
            self._tx_xfer()
            i = 0
        else:
            i += 1
        self.adc = ADC(self.chans[i])
        self.cur_chan = i
 
# The lines below enable testing without flashing your RPi Pico.
# Just press CTRL+E in terminal, past the content of that file and press CTRL+D
# After that the device with new functionalities should appear.           
import usb.device
wz=WZab1Interface()                                                         
usb.device.get().init(wz, builtin_driver=True)
       
