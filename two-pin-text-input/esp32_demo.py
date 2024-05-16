print("Text inputs with buttons")
import machine as m
import collections

# Define a class implementing states for a state machine
class eventgen:
    # Constants defining states
    IDLE = 1
    P1 = 2
    P2 = 3
    P12 = 4
    P21 = 5
    P120 = 6
    P210 = 7
    P212 = 8
    P121 = 9
    WAIT_IDLE = 10
    # Constructor connecting pins and queue
    def __init__(self,pin1,pin2,queue):
        # Functions for getting the pin state (possibly inverted)
        self.p1 = lambda : 1-pin1.value()
        self.p2 = lambda : 1-pin2.value()
        self.q = queue
        self.reps = 0
        self.st = self.IDLE
    def pin_change(self,t): # The function called when the buttons are settled
        while True:
            p1 = self.p1()
            p2 = self.p2()
            print(p1,p2,self.reps, self.st)
            if self.st == self.IDLE:
                print("reps=0")
                self.reps = 0
                if p1 == 0 and p2 == 0:
                    return
                elif p1 == 1:
                    self.st = self.P1
                elif p2 == 1:
                    self.st = self.P2
            elif self.st == self.P1:
                if p1 == 1 and p2 == 0:
                    return
                elif p1 == 0:
                    self.q.append(("E1",1))
                    self.st = self.IDLE
                elif p2 == 1:
                    self.st = self.P12                
            elif self.st == self.P2:
                if p1 == 0 and p2 == 1:
                    return
                elif p2 == 0:
                    self.q.append(("E2",1))
                    self.st = self.IDLE
                elif p1 == 1:
                    self.st = self.P21
            elif self.st == self.P12:
                if p1 == 1 and p2 == 1:
                    return
                elif p2 == 0:
                    self.reps = self.reps + 1
                    self.st = self.P120
                elif p1 == 0:
                    self.st = self.P121
            elif self.st == self.P121:
                if p1 == 0 and p2 == 1:
                    return
                if p2 == 0:
                    self.q.append(("E1f2",int(self.reps)))
                    self.st = self.IDLE
            elif self.st == self.P120:
                if p1 == 1 and p2 == 0:
                    return
                elif p1 == 0:
                    self.q.append(("E12",int(self.reps)))
                    self.st = self.IDLE
                elif p2 == 1:
                    self.st = self.P12
            elif self.st == self.P21:
                if p1 == 1 and p2 == 1:
                    return
                elif p1 == 0:
                    self.reps = self.reps + 1
                    self.st = self.P210
                elif p2 == 0:
                    self.st = self.P212
            elif self.st == self.P212:
                if p1 == 1 and p2 == 0:
                    return
                if p1 == 0:
                    self.q.append(("E2f1",int(self.reps)))
                    self.st = self.IDLE
            elif self.st == self.P210:
                if p1 == 0 and p2 == 1:
                    return
                elif p2 == 0:
                    self.q.append(("E21",int(self.reps)))
                    self.st = self.IDLE
                elif p1 == 1:
                    self.st = self.P21
            elif self.st == self.WAIT_IDLE:
                if p1 == 0 and p2 == 0:
                    self.st = self.IDLE
                else:
                    return

q = collections.deque((),32)
settling_time = 20 # Set to 1000 to see how does it work
Pin1=m.Pin(32,m.Pin.IN, m.Pin.PULL_UP)
Pin2=m.Pin(33,m.Pin.IN, m.Pin.PULL_UP)
t1 = m.Timer(1)

ev = eventgen(Pin1,Pin2,q)    
def p_cb(p):
    t1.init(mode=m.Timer.ONE_SHOT, period=settling_time, callback=ev.pin_change)
Pin1.irq(trigger=m.Pin.IRQ_RISING | m.Pin.IRQ_FALLING, handler=p_cb)    
Pin2.irq(trigger=m.Pin.IRQ_RISING | m.Pin.IRQ_FALLING, handler=p_cb)
while True:
    try:
        w = q.popleft()
        print(w)
    except Exception as e:
        pass
