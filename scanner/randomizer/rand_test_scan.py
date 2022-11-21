#!/usr/bin/python
# This is PUBLIC DOMAIN software written by
# Wojciech M. Zabolotny wzab<at>ise.pw.edu.pl 14.02.2010
# updated by Wojciech M. Zabolotny
# wzab<at>ise.pw.edu.pl or wzab01<at>gmail.com
# at 15.06.2019 for:
# - Python3
# - Python virtual environments
# - pylibdtmx
# This script analyzes the scanned tests and finds the checked
# answers. It also detects if the tests has been filled 
# correctly.
# This software is provided without any warranty
# You can use it only on your own risk.
# I don't know whether its use may infringe any patents
# in any country in the world...
#
# This software uses the libdmtx library with Python wrapper
# You can find it at http://libdmtx.sourceforge.net/
#
# Options (in fact they should be read from command line)
import zlib
import hashlib as h
import oscrypto.symmetric as osy
import msgpack
passw="test"
test_key = None
file_name="scanned_test.png"
# Code below should not be changed unless you know what 
# are you doing
from pylibdmtx.pylibdmtx import decode
from PIL import Image
# Read the scanned test
img = Image.open(file_name)
if img.mode != 'RGB':
   img = img.convert('RGB')
# The timeout value (and other options) below may need adjustment
# If you know any better way how to reasonable control
# precision of the dmtx decoding, please let me know
dm_read=decode(img,\
    min_edge=40, max_edge=600, deviation=20,\
    timeout=10000)
print (dm_read)
# Now we iterate through the detected codes dictionary and created the 
# list of codes that are not checked. They will be deleted next.
# The codes left should be those checked (blurred)
# by the student
to_del = []
for i in range(0,len(dm_read)):
    dt = dm_read[i].data
    if len(dt) < 10: # Arbitrary limit!
      code=dt.decode('Ascii')
      to_del.append(code)
    else: # This should be a testkey
      if test_key is not None:
         print ("Found duplicate key!")
         exit(1)
      ct = msgpack.unpackb(dt)      
      ht=h.sha256(passw.encode("utf8"))
      pt=osy.aes_cbc_pkcs7_decrypt(ht.digest(),ct[1],ct[0])
      test_key = msgpack.unpackb(zlib.decompress(pt), strict_map_key = False)
      print(test_key)
# Check if the test_key was found
num_questions=len(test_key)
num_digits=len(str(num_questions))
num_format="%"+str(num_digits)+"."+str(num_digits)+"d"
if test_key is None:
   print("No test key found in the scan!")
   exit(1)
# Now we build the dictionary with all possible answers in analyzed test
answers={}
for i,k in test_key.items():
  for j in k:
    pat=j[0]
    ans=(num_format % i)+pat
    answers[ans]=(i,pat)
  pat="?"
  ans=(num_format % i)+pat
  answers[ans]=(i,pat)
# Now we remove the non-checked answers
for code in to_del:
    if code in answers:
       answers.pop(code)
# Now we check if the test has been filled correctly (in each questions one
# option should be checked)
#print answers
answers2={}
for j in answers:
   key=answers[j][0]
   if key in answers2:
      print("The question "+str(key)+" has more then 1 answers checked")
      print("The test has been filled incorrectly")
      #exit(2)
   else:
      answers2[key]=answers[j][1]
# Now we have all answers in a dictionary indexed with question numbers
# Check if all questions are answered
#print answers2
for i in range(1,num_questions+1):
   if not i in answers2:
      print("In the question "+str(i)+" no answer has been selected")
      print("The test has been filled incorrectly")
      #exit(2)
# Now we know, that the test has been filled correctly, and we can 
# Evaluate the answers
# In this demo version we just print them out
for i in range(1,num_questions+1):
   print(str(i)+":"+answers2[i])


