#!/bin/bash
set -e
variant=1
rm -rf pdfs
rm -rf keys
mkdir pdfs
mkdir keys
while (( $variant <= $1 )); do
   vartext=`printf %4.4d $variant`
   echo $vartext
   ./rand_test_pl.py $2 $vartext
   pdflatex test.tex
   pdflatex test.tex
   mv test.pdf pdfs/test_${vartext}.pdf
   mv test.key keys/test_${vartext}.key
   variant=$(($variant + 1 ))
done 

