# Demo code for triple capacitance sensor based on Raspberry Pi Pico.
# The sensor pins (3,4,5) should be connected via high resistance (1M) to the driver pin (2).
# The sensor capacitance delays propagation of the state from the driver pin to the sensor.
# Unfortunately, Wokwi does not enable simulating that delay. 
# Therefore I had to model it with a shift register, and generate its clock with 
# PWM at pin 0.
#
# This is a public domain (or CC0) code written by Wojciech M. Zabolotny (wzab01@gmail.com)
# The code was developed with help of wokwi (https://wokwi.com) simulator
# and tested on real RPi Pico
import time
import rp2
import machine as m
import micropython
micropython.alloc_emergency_exception_buf(100)
time.sleep(0.1) # Wait for USB to become ready

# The code below is needed only in Wokwi to generate the clock
# for the shift register simulating delay of the signal.
p1=m.Pin(0,m.Pin.OUT)
pw1=m.PWM(p1)
pw1.freq(1000000)
pw1.duty_u16(32768//2)

PERIOD = 0x30000
DMAX = 0x8000

# PIO procedure for measurement of the delay
@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=False)
def meas_pulse():
    pull(block)
    mov(y,osr)
    wrap_target()
    #wait(1,irq,4)
    wait(1,pin,0)
    mov(x,y)
    label("wait_pin_1")
    jmp(pin,"pin_is_1")
    jmp(x_dec,"wait_pin_1")
    label("pin_is_1")
    in_(x,31)
    in_(pins,1)
    push()
    #wait(0,irq,4)
    wait(0,pin,0)
    mov(x,y)
    label("wait_pin_0")
    jmp(pin,"pin_still_1")
    jmp("pin_is_0")
    label("pin_still_1")
    jmp(x_dec,"wait_pin_0")
    label("pin_is_0")
    in_(x,31)
    in_(pins,1)
    push()
    wrap()

# PIO procedure generating the signal driving sensors.
@rp2.asm_pio(out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=False,sideset_init=rp2.PIO.OUT_LOW)
def gen_pulse():
    pull(block)
    mov(y,osr)
    wrap_target()
    mov(x,y).side(1)
    label("wait1")
    jmp(x_dec,"wait1")
    irq(block,0)
    mov(x,y)
    label("wait2")
    jmp(x_dec,"wait2")
    mov(x,y).side(0)
    label("wait3")
    jmp(x_dec,"wait3")
    irq(block,0)
    mov(x,y)
    label("wait4")
    jmp(x_dec,"wait4")
    wrap()

# This is the interrupt handler that receives the delay value
# The LSB informs whether this is a delay of the falling slope 
# or the rising slope.
# If the read value is RVAL, then the delay is:
# DMAX-RVAL//2
def get_vals(x):
    print(hex(sm1.get()), hex(sm2.get()), hex(sm3.get()))

p2 = m.Pin(2,m.Pin.OUT)
p3 = m.Pin(3,m.Pin.IN)
p4 = m.Pin(4,m.Pin.IN)
p5 = m.Pin(5,m.Pin.IN)

sm0 = rp2.StateMachine(0, gen_pulse, freq=100000000, sideset_base=p2)
sm1 = rp2.StateMachine(1, meas_pulse, freq=100000000, in_base=p2, jmp_pin=p3)
sm2 = rp2.StateMachine(2, meas_pulse, freq=100000000, in_base=p2, jmp_pin=p4)
sm3 = rp2.StateMachine(3, meas_pulse, freq=100000000, in_base=p2, jmp_pin=p5)

# The value PERIOD defines the period of the waveform.
# It must be long enough to finish the delay measurement
sm0.put(PERIOD)

sm0.irq(get_vals)
print("Started!")

# The values DMAX written to state machines define the maximum delay
# Those values are associated with the period of the waveform.
sm1.put(DMAX)
sm2.put(DMAX)
sm3.put(DMAX)

sm1.active(1)
sm2.active(1)
sm3.active(1)
sm0.active(1)
while(True):
    time.sleep(0.1)
