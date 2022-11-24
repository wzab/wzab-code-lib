#!/usr/bin/python
#
# This is the PUBLIC DOMAIN software, written
# by Wojciech M. Zabolotny
# wzab<at>ise.pw.edu.pl 14.02.2010
# updated by Wojciech M. Zabolotny
# wzab<at>ise.pw.edu.pl or wzab01<at>gmail.com
# at 15.06.2019 for:
# - Python3
# - Python virtual environments
# - pylibdtmx
# updated by Wojciech M. Zabolotny
# wzab01<at>gmail.com
# to generate randomized tests from the same set 
# of questions and answers (the encrypted test_key
# is printed on the test form!)

# This software may be used to generate the PNG files
# with patterns useful for generation of multiple 
# choice tests well suited for automatic analysis
# 
# The student should blur with black pen the DataMatrix pattern
# after the chosen answer.
# The filled and scanned test may then be analysed with the
# test_scan.py script.
#
# This software is provided without any warranty
# You can use it only on your own risk.
# I don't know whether its use may infringe any patents
# in any country in the world...
# 
# This software uses the libdmtx library with Python wrapper
# You can find it at http://libdmtx.sourceforge.net/
# Options (in fact they should be read from command line)
passw=open("test.pass","r").read().strip()
from pylibdmtx.pylibdmtx import encode as dmtx_encode
from PIL import Image, ImageFont, ImageDraw
import yaml
import random
import msgpack
import os
import sys
import json
os.system("rm -rf patterns ; mkdir patterns")
variant=sys.argv[2]

header = """
\\documentclass[11pt]{article}
\\usepackage{wrapfig}
\\usepackage[pdftex]{graphicx}
\\usepackage[utf8]{inputenc}
\\usepackage[T1]{fontenc}
\\usepackage{pslatex}
\\usepackage[a4paper,left=1cm, right=1cm, top=1cm, bottom=1cm]{geometry}
\\setlength{\\parindent}{0pt}
\\linespread{0.8}
\\begin{document}
\\sffamily
\\noindent
\\begin{wrapfigure}{r}{2.5cm}
\\includegraphics[width=\linewidth]{qkey.png}
\\end{wrapfigure}
Imię, nazwisko i nr indeksu \\hfill Wariant:""" + variant + """\\\\
{\small Proszę zaznaczyć właściwą odpowiedź zamazując kod graficzny umieszczony NA PRAWO od wybranej odpowiedzi.
Jeśli na jakieś pytanie nie chcecie Państwo odpowiadać, zamażcie kod umieszczony na prawo od znaku zapytania.
Proszę o przemyślane zaznaczanie odpowiedzi, ponieważ nie jest możliwa zmiana wyboru. 
Proszę nie modyfikować kodu graficznego umieszczonego w prawym górnym rogu arkusza - jest on niezbędny do sprawej oceny pracy.\\\\
Punktacja: pytania z czterema odpowiedziami -- dobra odpowiedź +1,5 punktu, błędna odpowiedź -0,5 punktu; 
pytania z trzema odpowiedziami -- dobra odpowiedź +1 punkt, błędna odpowiedź -0,5 punktu. Ostateczny wynik testu jest obcinany do przedziału [0,15].}
\\\\
~\\\\
\\\\
"""
quests = yaml.load(open(sys.argv[1],"r"),Loader=yaml.Loader)
rqs = quests
txt = ""
# Randomize the test
random.shuffle(rqs)
for q in rqs:
   random.shuffle(q["answ"])
# Now analyze the test, generating the LaTeX file and calculating the number 
# of questions and maximum number of answers
num_questions=len(rqs)
num_digits=len(str(num_questions))
num_format="%"+str(num_digits)+"."+str(num_digits)+"d"
qnum = 0
amax = 0
qkey = {}
for q in rqs:
   qnum = qnum+1
   if qnum != 1:
      txt+="\n~\\\\\n"
   qans = []
   ac = ord("A")
   txt += "\\includegraphics[height=0.7cm]{patterns/"+(num_format % qnum)+".png}\n"
   txt += q["quest"]+" "
   alen = len(q["answ"])
   if alen > amax:
      amax = alen
   for a in q["answ"]:
     if ac != ord("A"):
        txt += ", "
     qans.append((chr(ac), a[0]))
     txt += chr(ac)+")~"+a[2:]+"\n"
     ac += 1
   txt += ".\n"  
   qkey[qnum] = qans
# To encrypt key we need some extra packages
import zlib
import hashlib as h
import oscrypto.symmetric as osy
ht=h.sha256(passw.encode("utf8"))
ct=osy.aes_cbc_pkcs7_encrypt(ht.digest(),zlib.compress(msgpack.packb(qkey)),None)
with open("qkey.bin","wb") as fq:
   fq.write(msgpack.packb({"v":variant,"k":ct}))
os.system("dmtxwrite -s s -f PNG -o qkey.png qkey.bin")
# Now write the randomized test to the file
fo=open("test.tex","w")
fo.write(header+txt)
fo.write("\\end{document}")
fo.close()
# Now we generate the patterns needed for LaTeX
from patterns_gen import *
for i in range(0,num_questions):
   gen_pats(num_questions,i+1,len(rqs[i]["answ"]))
print(qkey)
with open("test.key","w") as fk:
   json.dump((variant,qkey),fk)

