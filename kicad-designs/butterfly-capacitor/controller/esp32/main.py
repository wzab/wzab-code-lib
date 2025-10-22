# main.py -- ESP32 MicroPython + Microdot + asyncio WebSocket
# Circular dial GUI (0..12059), buttons, text input.
# Sends value to server via WebSocket in real-time and prints to serial (DAC_VALUE)
# This code is a result of a long discussion of Wojciech Zabolotny (wzab01@gmail.com, SP5DAA)
# with ChatGPT, available at https://chatgpt.com/share/68c7fdbd-6d40-800c-8983-f73a21130e31
# I (W.Zabolotny) make it publicly available for all interested people.
# It will be finally used to control the butterfly capacitor in a MagLoop antenna
# as discussed in https://www.reddit.com/r/amateurradio/comments/1nauoub/controller_for_magloop_antenna_capacitor_how_to/
# Please note that you will need a private Wokwi Gateway enabled to test that code in simulation.

import sys
import ujson
import network
import time
import uasyncio as asyncio

NSTEPS=12060

import microdot
from microdot import Microdot, Response
# Work around Wokwi flat FS limitations
sys.modules["microdot.microdot"] = microdot
import microdot_helpers
sys.modules["microdot.helpers"] = microdot_helpers
import microdot_websocket
sys.modules["microdot.websocket"] = microdot_websocket
from microdot.websocket import with_websocket

import stepper
motor=stepper.stepper(p1=5,p2=6,p3=7,p4=8,nsteps=12060)

# ---------------- Wi-Fi config ----------------
#WIFI_SSID = "Wokwi-GUEST"
#WIFI_PASS = ""
w = open("wifi.txt","r").readlines()
WIFI_SSID = w[0].strip()
WIFI_PASS = w[1].strip()

# ---------------- Web server ------------------
app = Microdot()
Response.default_content_type = 'text/html'

# Shared state
current_value = 0
ws_clients = []

# ---------------- Utilities ------------------
def load_html():
    try:
        with open("html.txt", "r") as f:
            return f.read()
    except Exception as e:
        print("Error loading html.txt:", e)
        return "<h1>Error loading html.txt</h1>"

INDEX_HTML = load_html()

# ---------------- Routes ------------------
@app.get("/")
async def index(request):
    return INDEX_HTML

@app.route("/ws")
@with_websocket
async def ws_route(request, ws):
    global current_value
    ws_clients.append(ws)
    try:
        # Send current value immediately
        await ws.send(ujson.dumps({"value": current_value}))

        while True:
            msg = await ws.receive()
            if msg is None:
                break
            if isinstance(msg, (bytes, bytearray, memoryview)):
                msg = bytes(msg).decode("utf-8")
            data = ujson.loads(msg)
            v = int(data.get("value", 0))
            current_value = max(0, min(NSTEPS-1, v))
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)
        print("Client disconnected")


# ---------------- Background broadcast ------------------
async def broadcast_loop():
    global current_value
    last_sent = None
    while True:
        if last_sent != current_value:
            motor.move(current_value)
            msg_bytes = ujson.dumps({"value": current_value}).encode("utf-8")
            for ws in ws_clients[:]:
                try:
                    await ws.send(msg_bytes)
                except Exception:
                    ws_clients.remove(ws)
            print("DAC_VALUE =", current_value)
            last_sent = current_value
        await asyncio.sleep_ms(20)  # throttle updates

# ---------------- Wi-Fi connect ------------------
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi:", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASS)
        t0 = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), t0) > 15000:
                raise RuntimeError("Wi-Fi connection timed out")
            time.sleep_ms(200)
    ip = wlan.ifconfig()[0]
    print("Wi-Fi connected, IP:", ip)
    return ip

# ---------------- Main ------------------
async def main():
    ip = connect_wifi()
    print("Open -> http://%s/" % ip)

    # Start server as background task
    server_task = asyncio.create_task(app.start_server(host="0.0.0.0", port=80))
    # Start the broadcast loop
    asyncio.create_task(broadcast_loop())

    # Keep main alive
    while True:
        await asyncio.sleep(3600)

try:
    asyncio.run(main())
except (KeyboardInterrupt, Exception) as e:
    print("Stopped:", e)
