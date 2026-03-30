#!/bin/sh
BASEDIR=$(dirname "$0")
echo 525 > /sys/class/gpio/export
echo in > /sys/class/gpio/btn13/direction
echo both > /sys/class/gpio/btn13/edge
python ${BASEDIR}/irqtest.py
