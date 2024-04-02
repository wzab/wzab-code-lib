#!/usr/bin/env python
# -*- encoding=iso-8859-2 -*-
# Written by Wojciech M. Zabołotny <wzab01@gmail.com>
# Copyleft 2024 W.M. Zabołotny
# This is a PUBLIC DOMAIN code
#
# The code is somehow based on:
# https://stackoverflow.com/questions/44290837/how-to-interact-with-usb-device-using-pyusb

import usb.core
import usb.util
import struct
import time
import signal

# Globals are kept in a single variable 
# That trick enables accessing them from 
# various routines...

class glbs:
  pass
glb = glbs()

glb.runflag = True

# find our device
dev = usb.core.find(idVendor=0x2e8a, idProduct=0x0005)

# was it found?
if dev is None:
    raise ValueError('Device not found')

# find our interface
for cfg in dev:
   for intf in cfg:
      if usb.util.get_string(dev,intf.iInterface) == 'WZADC1':
         # This is our interface
         my_intf = intf
         my_intfn = intf.bInterfaceNumber

# try default conf
print("trying to claim interface")
try:
    usb.util.claim_interface(dev, my_intfn)
    print("claimed interface")
except usb.core.USBError as e:
    print("Error occurred claiming " + str(e))
    sys.exit("Error occurred on claiming")

glb.eps=my_intf.endpoints()

REQ_ADC_MASK =  0x12
REQ_ADC_PERIOD = 0x14
REQ_ADC_START = 0x13
REQ_ADC_STOP = 0x15

def on_sig_int(sig,frame):
    glb.runflag = False

signal.signal(signal.SIGINT, on_sig_int)


dev.ctrl_transfer(0x21,REQ_ADC_MASK,0,my_intfn,struct.pack("<BBBBB",1,1,1,1,1))
dev.ctrl_transfer(0x21,REQ_ADC_PERIOD,0,my_intfn,struct.pack("<L",100))
dev.ctrl_transfer(0x21,REQ_ADC_START,0,my_intfn,b"")
while glb.runflag:
    res=glb.eps[0].read(300,timeout=2000)
    vals=struct.unpack("<"+str(len(res)//2)+"H",bytes(res))
    print(["{:04x}".format(i) for i in vals])
dev.ctrl_transfer(0x21,REQ_ADC_STOP,0,my_intfn,b"")
