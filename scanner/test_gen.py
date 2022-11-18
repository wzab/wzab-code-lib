# This is the PUBLIC DOMAIN software, written
# by Wojciech M. Zabolotny
# wzab<at>ise.pw.edu.pl 14.02.2010
# updated by Wojciech M. Zabolotny
# wzab<at>ise.pw.edu.pl or wzab01<at>gmail.com
# at 15.06.2019 for:
# - Python3
# - Python virtual environments
# - pylibdtmx
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
num_answers=4
num_questions=30
num_digits=len(str(num_questions))
# Code below should not be changed unless you know what 
# are you doing
from pylibdmtx.pylibdmtx import encode as dmtx_encode
from PIL import Image, ImageFont, ImageDraw
num_format="%"+str(num_digits)+"."+str(num_digits)+"d"
for i in range(1,num_questions+1):
    #Generate the test answer pattern for the question #i
    # Write a Data Matrix barcode
    ans_codes=[]
    max_x=0;
    max_y=0;
    for j in range(0,num_answers+1):
        #Generate the DataMatrix code for each answer
        if j<num_answers:
           answer=chr(ord("A")+j)
        else:
           answer="?"
        ant = (num_format % i)+answer
        #print(ant)
        encoded=dmtx_encode(ant.encode('Ascii'),'Ascii')
        img = Image.frombytes('RGB', (encoded.width, encoded.height), encoded.pixels)
        ans_codes.append(img)
        if encoded.width>max_x:
           max_x = encoded.width
        if encoded.height>max_y:
           max_y = encoded.height    # Now we add the text descriptions of the question and answers
    # You may need to adjust the font location below
    font=ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/arial.ttf",int(0.7*max_y))
    # Here we should generate the bitmap containing first the question number
    # then the letters and encoded answers
    # e.g.: "001 A:XX,B:XX,C:XX,D:XX,?:XX
    #Now we calculate the sizes of descriptions
    desc_sizes=[]
    desc_text=[]
    for j in range(0,num_answers+1):
        if j==0:
           txt=(num_format % i)+" A:"
        elif j<num_answers:
           txt=","+chr(ord("A")+j)+":"
        else:
           txt=","+"?:"
        desc_sizes.append(font.getsize(txt))
        desc_text.append(txt)
    #Calculate the size of the output image
    img_x=0
    img_y=0
    for j in range(0,num_answers+1):
       img_x+= desc_sizes[j][0]+ans_codes[j].size[0]
       img_y = max(img_y, desc_sizes[j][1],ans_codes[j].size[1])
    #Now create the desired output image
    out_img=Image.new("RGB",(img_x, img_y),(255,255,255))
    drw=ImageDraw.Draw(out_img)
    img_x=0
    img_y=0
    for j in range(0,num_answers+1):
       drw.text((img_x, img_y),desc_text[j],font=font, fill=(0,0,0))
       img_x += desc_sizes[j][0]
       out_img.paste(ans_codes[j],(img_x,img_y))
       img_x += ans_codes[j].size[0]
    fname="patterns/"+(num_format % i)+".png"
    out_img.save(fname)

