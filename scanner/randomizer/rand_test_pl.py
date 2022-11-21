import yaml
import random
import msgpack
import os
header = """
\\documentclass[11pt]{article}
\\usepackage[pdftex]{graphicx}
\\usepackage[utf8]{inputenc}
\\usepackage[a4paper,left=1cm, right=1cm, top=1cm, bottom=1cm]{geometry}
\\setlength{\\parindent}{0pt}
\\begin{document}
\\noindent
Please mark the correct answer for the questions below.
The correct answer should be marked
by blurring the pattern on the right side of the corresponding letter.
If you want to skip the question, blur the pattern on the right side
of the question mark.\\\\
~\\\\
"""
quests = yaml.load(open("pyt.yaml","r"),Loader=yaml.Loader)
rqs = quests
# Randomize the test
random.shuffle(rqs)
for q in rqs:
   random.shuffle(q["answ"])
# Now write the randomized test to the file
fo=open("test.tex","w")
fo.write(header)
qnum = 1
qkey = {}
for q in rqs:
   if qnum != 1:
      fo.write("\n~\\\\\n")
   qans = []
   ac = ord("A")
   fo.write("\\includegraphics[height=0.7cm]{patterns/"+("%2.2d" % qnum)+".png}\n")
   fo.write(q["quest"]+" ")
   for a in q["answ"]:
     if ac != ord("A"):
        fo.write(", ")
     qans.append((chr(ac), a[0]))
     fo.write(chr(ac)+")~"+a[2:]+"\n")
     ac += 1
   qkey[qnum] = qans
   qnum = qnum+1
# To encrypt key we need some extra packages
import zlib
import hashlib as h
import oscrypto.symmetric as osy
passw="test"
ht=h.sha256("test".encode("utf8"))
ct=osy.aes_cbc_pkcs7_encrypt(ht.digest(),zlib.compress(msgpack.packb(qkey)),None)
with open("qkey.bin","wb") as fq:
   fq.write(msgpack.packb(ct))
os.system("dmtxwrite -s s -f PNG -o qkey.png qkey.bin")
fo.write("\\end{document}")
fo.close()
print(qkey)

