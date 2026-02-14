#!/usr/bin/env python3
#The script below was created by Wojciech (Voytek) Zabolotny SP5DAA
# on 2025.02.09 with significant help of ChatGPT.
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

#Needed for Jabber notofications
import asyncio
import logging
#logging.basicConfig(level=logging.DEBUG)
import slixmpp
#Python file with Jabber credentials
import jcreds
#It should contain the following definitions:
# jid = "sender@jabber.somewhere" # The sending Jabber account
# password = "strong_password" # Password for the sending Jabber account
# jid2 = "sender@jabber.somewhere" # The sending Jabber account for high priority notfications
# password2 = "strong_password" # Password for the sending Jabber account for high priority notifications
# target = "recipient@jabber.wherever" # The account on which you want to receive notifications

# --------------------
# Settings
# --------------------
MY_GRID = "KO02"          # My grid (first 4 letters)
BROKER = "mqtt.pskreporter.info"
PORT = 1883               # MQTT without TLS, TLS = 1884
CLIENT_ID = "FT8_FT4_Watcher"
WATCH_MODES = {"FT8", "FT4"}
SKIPPED_BANDS = {"60M",} # Bands not counted for DXCC awards
VOICE_ACTIVE = False
JABBER_ACTIVE = True

lookup = LookupLib(lookuptype="countryfile")  # use country-files
ci = Callinfo(lookup)

qsos,headers=af.read_from_file("lotwreport.adi")
dxccs={}
cqzs={}

# Create a selective lists of DXCCs and CQZs done in all bands
for q in qsos:
   if q.get('BAND').upper() not in SKIPPED_BANDS:
      dxccs.setdefault(q.get('BAND'),set()).add(q.get('DXCC'))
      try:
         info = ci.get_all(q.get('CALL'))
         cqzs.setdefault(q.get('BAND'),set()).add(info['cqz'])
      except Exception as e:               
         pass
# Create a global list of DXCC done
dxcc_done=set()
for key,val in dxccs.items():
    dxcc_done |= val

# Create a global list of CQZ done
cqz_done=set()
for key,val in cqzs.items():
    cqz_done |= val
    
print("DXCCs done: ",dxcc_done)
print("CQZs done: ",cqz_done)

# Subscribe MQTT only for my grid and for selected modes
TOPICS = [
    f"pskr/filter/v2/+/FT8/+/+/+/{MY_GRID}/#",
    f"pskr/filter/v2/+/FT4/+/+/+/{MY_GRID}/#"
]
fout_waz = open("watch_waz.txt","wt")
fout_dxcc = open("watch_dxcc.txt","wt")
fout_chlg = open("watch_challenge.txt","wt")

# ------------------------------------------------------------
# Helper functions for Jabber notifications
# ------------------------------------------------------------

class Notifier(slixmpp.ClientXMPP):
    def __init__(self, jid: str, password: str, target_jid: str, text: str):
        super().__init__(jid, password)
        self.target_jid = target_jid
        self.text = text
        self.add_event_handler("session_start", self.start)

    async def start(self, event):
        self.send_presence()
        await self.get_roster()
        self.send_message(mto=self.target_jid, mbody=self.text, mtype="chat")
        self.disconnect()

async def jabber_send(text):
    if JABBER_ACTIVE:
       try:
           xmpp = Notifier(jcreds.jid, jcreds.password, jcreds.target, text)
           xmpp.loop = asyncio.get_running_loop()
           maybe = xmpp.connect()
           ok = await maybe if asyncio.iscoroutine(maybe) else maybe
           if ok is False:
               raise RuntimeError("I couldn't connect to the Jabber server (False returned).")
           await xmpp.disconnected
       except Exception as e:
           print(str(e))
           pass

async def jabber2_send(text):
    if JABBER_ACTIVE:
       try:
           xmpp = Notifier(jcreds.jid2, jcreds.password2, jcreds.target, text)
           xmpp.loop = asyncio.get_running_loop()
           maybe = xmpp.connect()
           ok = await maybe if asyncio.iscoroutine(maybe) else maybe
           if ok is False:
               raise RuntimeError("I couldn't connect to the Jabber server (False returned).")
           await xmpp.disconnected
       except Exception as e:
           print(str(e))
           pass

# ------------------------------------------------------------
# Helper function for voice notification
# ------------------------------------------------------------
def say_message(voice_msg):
    if VOICE_ACTIVE:
        os.system("echo \""+ voice_msg + "\" | RHVoice-test")

# ------------------------------------------------------------
# Helper functions for PSK monitor connection
# ------------------------------------------------------------

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
        if band.upper() not in SKIPPED_BANDS:
          jmsg = ""
          jmsg2 = ""
          stime = time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime())
          report = f"{stime} {tx_call:>10} → {rx_call} "+\
                       f"mode={mode} band={band} SNR={snr} dB freq={freq} Hz "+\
                       f"TX grid={tx_grid} RX grid={rx_grid}"
          if info['cqz'] not in cqz_done: 
              msg = "WAZ  " + report + "\n"
              fout_waz.write(msg+"\n")
              fout_waz.flush()
              jmsg2 += msg
              voice_msg = f"New zone: {tx_call} in band {band}"
              say_message(voice_msg)
          # Check DXCC
          if str(info['adif']) not in dxcc_done:
              msg = "DXCC " + report +"\n"
              fout_dxcc.write(msg)
              fout_dxcc.flush()      
              jmsg += msg
          # Check DXCC Challenge
          if str(info['adif']) not in dxccs[band.upper()]:
              msg = "CHLG " + report + "\n"
              fout_chlg.write(msg)
              fout_chlg.flush()                       
              #jmsg += msg
          if jmsg != "":
              asyncio.run(jabber_send(jmsg))
          if jmsg2 != "":
              asyncio.run(jabber2_send(jmsg))
    except Exception as e:
        print("⚠ Parsing of the message failed:", e)

def on_disconnect(client, userdata, reasonCode, properties=None):
    print("❌ Disconnected MQTT broker, reasonCode:", reasonCode)

def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print("📩 Confirmed subscription, QoS:", granted_qos)

say_message("Starting monitoring")
asyncio.run(jabber_send("Starting monitoring"))
asyncio.run(jabber2_send("Starting monitoring 2"))
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
