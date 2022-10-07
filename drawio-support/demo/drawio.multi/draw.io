#!/bin/bash

# DRAWIO_DESKTOP shoud point to the directory,
# where drawio-desktop was installed by doing:
# git clone --recursive https://github.com/jgraph/drawio-desktop.git
# cd drawio-desktop
# git checkout v19.0.3 # That version works on Debian/testing. You may need another one
# npm install
# cd drawio/src/main/webapp
# npm install
DRAWIO_DESKTOP=/opt/diagrams_net
(
  cd ${DRAWIO_DESKTOP}/drawio-desktop
  npm start -- $@
)
