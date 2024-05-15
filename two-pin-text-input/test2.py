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
    
