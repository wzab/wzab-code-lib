#!/bin/sh
TARGET=../figures
for f in *.layers; do 
  BASE=`basename $f .layers`
  DRFILE=${BASE}.drawio
  nr=1
  cat $f | while read line
  do
     ./drawio_select_layers.py --infile ${DRFILE} --layers ${line} --outfile   tmp.drawio
     ./draw.io -x --crop -f pdf -o `pwd`/${TARGET}/${BASE}-${nr}.pdf `pwd`/tmp.drawio
     rm tmp.drawio
     nr=$(($nr + 1))
  done
done

