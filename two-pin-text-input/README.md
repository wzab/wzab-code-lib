Current state of technology enables creating small and simple communication devices offering high level of privacy and security.
A good example may be Meshtastic devices. However, a necessity to use smartphone (possibly infected with a spyware) may break both privacy and security.
It would be much better if the text message could be entered on the Meshtastic device itself, and then have it encrypted internally before transmission.
Unfortunately, most Meshtastic device do not offer a full keyboard. An option could be entering the text as a Morse code, using the key of capacitive pad.
The Morse code however covers only a limited set of characters, and its knowledge in society is limited.
Therefore, I'd like to propose another method for entering text. It is based on two digital inputs. They may be two capacitive pads, or a double paddle Morse key.
Please note that I have developed the below described procedure from scratch. I have not investigated if similar procedures are implemented (or may be even patented?) by anybody. 
So if you would like to use it in a commercial product, please make the necessary investigations yourself.

## What we may generate with two inputs:

Below I put the ASCII diagrams of possible events that we can send with two inputs. I mark low level (_) as "inactive" and high level (‾) as active. 
The inputs are marked as In1 and In2.

```
Event   Wavevorfm
E1      In1: __/‾‾\__
        In2: ________

E2      In1: ________
        In2: __/‾‾\__
        
E1i2    In1: ___/‾‾\___
        In2: _/‾‾‾‾‾‾\_

E2i1    In1: _/‾‾‾‾‾‾\_
        In2: ___/‾‾\___

E1f2    In1: _/‾‾‾‾\_____
        In2: ____/‾‾‾‾\__

E2f1    In1: ____/‾‾‾‾\__
        In2: _/‾‾‾‾\_____
```

So we have 6 elementary events: Event 1, Event 2, Event 1 in event 2, Event 2 in event 1, Event 1 followed by event 2, Event 2 followed by event 1.
Each of them may be easily generated with two independent switches, two capacitive pads or double Morse paddle.

We may also generate more complex sequences, like:

```
Multiple E1i2:
E1i2    In1: ___/‾‾\__/‾‾\__/‾‾\__/‾‾\__/‾‾\____
        In2: _/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\__

Multiple E1i2 finished by E2f1:
E1i2    In1: ___/‾‾\__/‾‾\__/‾‾\__/‾‾\__/‾‾‾‾\__
        In2: _/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\____

Multiple E2i1
E1i2    In1: _/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\__
        In2: ___/‾‾\__/‾‾\__/‾‾\__/‾‾\__/‾‾‾‾\__

Multiple E2i1 finished by E1f2:
E1i2    In1: _/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\____
        In2: ___/‾‾\__/‾‾\__/‾‾\__/‾‾\__/‾‾‾‾\__
```

## Using of possible events for entering text.
First, with E1i2 and multiple E1i2 we may select an appropriate group of characters (for example we may have four groups: "upper case letters", "lower case letters", "digits", "special chracters").

Then, the selected group is split into two equal subgroups, and the first and last character of each subgroup is shown. Then the selected group is handled in the same way, until only one chracter is left. This character is then selected and added to the created message.

Below is the sample code showing the proposed procedure:

```python
#!/usr/bin/python
# The demonstration code for two-key character selection.
# Written by Wojciech M. Zabołotny (wzab01@gmail.com)
# This is a public domain code (under CC0 1.0 license)
c=[]
for i in range(ord('A'),ord('Z')+1):
  c.append(chr(i))
# We have three indices:
# start, end, split
start = 0
end = len(c)
while True:
  split = (start + end) // 2
  if start == split:
     # The character is already selected, print it
     print("Chosen:"+c[start])
     break
  if split > start + 1:
    line = "["+c[start]+" "+c[split-1]+"]"
  else:
    line = "["+c[start]+"]"
  if split < end - 1:
    line += "["+c[split]+" "+c[end-1]+"]"
  else:
    line += "["+c[split]+"]"
  #print(start,split,end)
  print(line)
  sel = input("sel:")
  if sel == "1":
    end = split
  else:
    start = split
```
Below is the process of selection of the `K` character.
```
$ python test.py 
[A M][N Z]
sel:1
[A F][G M]
sel:2
[G I][J M]
sel:2
[J K][L M]
sel:1
[J][K]
sel:2
Chosen:K
```
Of course the user should be able to correct the character entered. That can bee achieved with 
E2i1 event. Double E2i1 event may be used to clear the whole text.

When the whole message is assembled, it may be sent with E1f2 event.

The above procedure does not use E2f1 event, which may be used to leave the whole procedure.

## Example implementation
I don't have an implementation for microcontroller yet. A simple demo function with Python running on a PC and using numbers instead of the above events is shown below:

```python
#!/usr/bin/python
# The demonstration code for two-key character selection.
# Written by Wojciech M. Zabołotny (wzab01@gmail.com)
# This is a public domain code (under CC0 1.0 license)

# Create groups of characters
uc_letters=[]
for i in range(ord('A'),ord('Z')+1):
  uc_letters.append(chr(i))
lc_letters=[]
for i in range(ord('a'),ord('z')+1):
  lc_letters.append(chr(i))
digits=[]
for i in range(ord('0'),ord('9')+1):
  digits.append(chr(i))
specs=list("\"\'{}[]!?@#$%^&*()-+=/\\,.<>")
groups=[uc_letters, lc_letters, digits, specs]

# Main loop
# We have three indices:
# start, end, split
grnr=0
c=groups[grnr]
start = 0
end = len(c)
txt = ""
while True:
  split = (start + end) // 2
  if start == split:
     # The character is already selected, print it
     txt += c[start]
     start = 0
     end = len(c)
     continue
  if split > start + 1:
    line = "["+c[start]+" "+c[split-1]+"]"
  else:
    line = "["+c[start]+"]"
  if split < end - 1:
    line += "["+c[split]+" "+c[end-1]+"]"
  else:
    line += "["+c[split]+"]"
  #print(start,split,end)
  print(txt)
  print(line)
  sel = input("1-1st half, 2-2nd half, 3-del char, 4-clear text, 5-send text, 6-next group:")
  if sel == "1":
    end = split
  elif sel == "2":
    start = split
  elif sel == "3":
    txt = txt[:-1]
  elif sel == "4":
    txt = txt[:-1]
  elif sel == "5":
    print("Transmitted msg:"+txt)
    txt = ""
    start = 0
    end = len(c)
  elif sel == "6":
    grnr = (grnr + 1) % len(groups)
    c = groups[grnr]
    start = 0
    end = len(c)
  else:
    print("Unknown key")
```

I'll send a link to the microcontroller implementation as soon as it is ready.


## Debouncing
After each change of the pin state, we initialize the timer, set for the expected settling time.
If that timer expires, we read the current value od the pin. If it differs from the previously reported one, we generate an event.

```python
print("Hello, ESP32!")
import machine as m
p1=m.Pin(32,m.Pin.IN, m.Pin.PULL_UP)
p2=m.Pin(33,m.Pin.IN, m.Pin.PULL_UP)
#while True:
#print(p1.value(),p2.value())
t1 = m.Timer(1)
t2 = m.Timer(2)
def t1_cb(t):
    print('pin 1 change', p1.value())
def p1_cb(p):
    t1.init(mode=m.Timer.ONE_SHOT, period=1000, callback=t1_cb)
def t2_cb(t):
    print('pin 2 change', p2.value())
def p2_cb(p):
    t2.init(mode=m.Timer.ONE_SHOT, period=1000, callback=t2_cb)
p1.irq(trigger=m.Pin.IRQ_RISING | m.Pin.IRQ_FALLING, handler=p1_cb)
p2.irq(trigger=m.Pin.IRQ_RISING | m.Pin.IRQ_FALLING, handler=p2_cb)
```

