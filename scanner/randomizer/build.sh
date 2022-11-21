#!/bin/bash
python3 -m venv testgen
source testgen/bin/activate
pip3 install pylibdmtx
pip3 install Pillow 
pip3 install pyyaml
pip3 install oscrypto
pip3 install msgpack
python3 rand_test_pl.py pyt.yaml 0001
