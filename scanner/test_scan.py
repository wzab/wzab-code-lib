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
num_answers=4
num_questions=10
file_name="scanned_test.png"
# Code below should not be changed unless you know what 
# are you doing
from pylibdmtx.pylibdmtx import decode
from PIL import Image
num_digits=len(str(num_questions))
num_format="%"+str(num_digits)+"."+str(num_digits)+"d"
# Read the scanned test
img = Image.open(file_name)
if img.mode != 'RGB':
   img = img.convert('RGB')
# The timeout value (and other options) below may need adjustment
# If you know any better way how to reasonable control
# precision of the dmtx decoding, please let me know
dm_read=decode(img,\
    min_edge=40, max_edge=200, deviation=20,\
    timeout=10000)
print (dm_read)
# Now we build the dictionary with all possible answers in analyzed test
answers={}
for i in range(1,num_questions+1):
  for j in range(0,num_answers+1):
    if j< num_answers:
      pat=chr(ord('A')+j)
    else:
      pat="?"
    ans=(num_format % i)+pat
    #print ans
    answers[ans]=(i,pat)
# Now we iterate through the detected codes dictionary and delete them
# from the dictionary. The codes left should be those checked (blurred)
# by the student
for i in range(0,len(dm_read)):
    code=dm_read[i].data.decode('Ascii')
    if code in answers:
       answers.pop(code)
    else:
       print ("The scanned test contains the unknown code: "+code)
       exit(1)
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


