#!/bin/sh
python3 -m venv testgen
source testgen/bin/activate
pip3 install pylibdmtx
pip3 install Pillow
python3 test_gen.py
