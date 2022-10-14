#!/bin/bash
for f in *.ipe; do
   ipescript expallviews $f ../figures
done

