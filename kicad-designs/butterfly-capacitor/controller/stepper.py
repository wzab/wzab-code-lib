# This is a stepper motor controller for a butterfly capacitor.
# It implements the backlash compensation.
# The code is written by Wojciech M. Zabolotny (wzab01@gmail.com, SP5DAA) 
# and published under CC0 Public Domain Dedication 
# The idea resulted from reddit discussion:
# https://www.reddit.com/r/amateurradio/comments/1nauoub/controller_for_magloop_antenna_capacitor_how_to/ 
import machine as m
import time
class stepper:
    def __init__(self, dur = 2, p1 = 13, p2 = 12, p3 = 14, p4 = 27, pos = 0, nsteps = 4096, back = 100):
      self.f1=m.Pin(13,m.Pin.OUT)
      self.f2=m.Pin(12,m.Pin.OUT)
      self.f3=m.Pin(14,m.Pin.OUT)
      self.f4=m.Pin(27,m.Pin.OUT)
      self.pos = pos
      self.dur = dur
      self.nsteps = nsteps
      self.back = back
      self.ctrl = ((self.f1,), 
          (self.f1,self.f2),
          (self.f2,), 
          (self.f2,self.f3),
          (self.f3,),
          (self.f3,self.f4),
          (self.f4,),
          (self.f4,self.f1))
    def move(self, npos):
      npos = npos % self.nsteps
      shift = (npos - self.pos) % self.nsteps
      # If we turn shaft counterclockwise, then we first go back by "back" steps
      bpos = (npos - self.back) % self.nsteps
      if shift > (self.nsteps // 2):
          while True:
              # We skip the intermediate pulses (when the current consumption is high),
              # unless it is the final position
              if (self.pos % 2 == 0) or self.pos == bpos:
                  self.gen_pulse()
              self.pos = (self.pos - 1) % self.nsteps
              if self.pos == bpos:
                  break
      # Finally, we always move the shaft clockwise
      while True:
          # We skip the intermediate pulses, unless it is the final position
          if (self.pos % 2 == 0) or self.pos == npos:
              self.gen_pulse()
          self.pos = (self.pos + 1) % self.nsteps
          if self.pos == npos:
              break

    def gen_pulse(self):
      phase = self.pos % 8
      for pin in self.ctrl[phase]:
          pin.value(1)
      time.sleep_ms(self.dur)
      for pin in (self.f1, self.f2, self.f3, self.f4):
          pin.value(0)

#Works with duration 2 ms and above
#Doesn't work with duration 1 ms

