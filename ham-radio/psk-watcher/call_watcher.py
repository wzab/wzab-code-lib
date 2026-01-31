#!/usr/bin/env python3
# The script below was created by Wojciech (Voytek) Zabolotny SP5DAA
# on 2025.12.05 with significant help of ChatGPT.
# It is published as PUBLIC DOMAIN
# or under the Creative Commons CC0 Public Domain Dedication
# No warranty of any kind is given.
# You use it on your own risk
import os
import time
import json
import paho.mqtt.client as mqtt
from pyhamtools import LookupLib, Callinfo
import adif_io as af

# --------------------
# Settings
# --------------------
SEARCHED_CALLS = {"VO2NS", "VO2AC", "VY0IRC", }
CHECKED_BANDS = {"160M", "80M","40M","30M","20M",} # Bands to be checked
MY_GRID = "KO02"          # My grid (first 4 letters)
BROKER = "mqtt.pskreporter.info"
PORT = 1883               # MQTT without TLS, TLS = 1884
CLIENT_ID = "FT8_FT4_Watcher"
WATCH_MODES = {"FT8", "FT4"}
#SKIPPED_BANDS = {"60M", } # Bands not counted for DXCC awards

lookup = LookupLib(lookuptype="countryfile")  # use country-files
ci = Callinfo(lookup)

# Subscribe MQTT only for my grid and for selected modes
TOPICS = [
    f"pskr/filter/v2/+/FT8/+/+/+/{MY_GRID}/#",
    f"pskr/filter/v2/+/FT4/+/+/+/{MY_GRID}/#"
]
fout_call = open("watch_call.txt","wt")

# --------------------
# Funkcje pomocnicze
# --------------------
def on_connect(client, userdata, flags, reasonCode, properties=None):
    print(f"✅ Connected to MQTT broker: {BROKER} (reasonCode={reasonCode})")
    for topic in TOPICS:
        client.subscribe(topic)
        print(f"📡 Subscribed topic: {topic}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        tx_call = data.get("sc", "?")
        tx_grid = data.get("sl", "?")
        rx_call = data.get("rc", "?")
        rx_grid = data.get("rl", "?")
        mode = data.get("md", "?")
        snr = data.get("rp", "?")
        freq = data.get("f", "?")
        band = data.get("b", "?")

        info = ci.get_all(tx_call)
        if band.upper() in CHECKED_BANDS:
          stime = time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime())
          report = f"{stime} {tx_call:>10} → {rx_call} "+\
                       f"mode={mode} band={band} SNR={snr} dB freq={freq} Hz "+\
                       f"TX grid={tx_grid} RX grid={rx_grid}"
          call = tx_call.strip()
          if call in SEARCHED_CALLS: 
              print("  " + report)
              fout_call.write(report+"\n")
              fout_call.flush()
              voice_msg = f"{call} seen in band {band}"
              os.system("echo \""+ voice_msg + "\" | RHVoice-test")
          #else:
          #    print(report)
          #    print(tx_call)
    except Exception as e:
        print("⚠ Parsing of the message failed:", e)

def on_disconnect(client, userdata, reasonCode, properties=None):
    print("❌ Disconnected MQTT broker, reasonCode:", reasonCode)

def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print("📩 Confirmed subscription, QoS:", granted_qos)

os.system("echo \"Starting monitoring\" | RHVoice-test")
# --------------------
# MQTT v5 client
# --------------------
client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv5)
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect
client.on_subscribe = on_subscribe

client.enable_logger()  # connection debug 

# Connection to the broker
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()  # odbiór w tle

print(f"🌐 Listening for FT8/FT4 for grid {MY_GRID} on broker {BROKER}…")

# --------------------
# Main loop (working in the background, receiving via callbacks)
# --------------------

try:
    while True:
        time.sleep(1)  # "sleep" instead of "pass" to reduce CPU usage
except KeyboardInterrupt:
    print("🛑 Stop listening…")
    client.loop_stop()
    client.disconnect()
