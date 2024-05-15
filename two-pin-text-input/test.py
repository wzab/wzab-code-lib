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

