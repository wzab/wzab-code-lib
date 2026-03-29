#!/usr/bin/env python3
import argparse
import json
import random
import socket
import threading
import time
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from vugpio import VhostUserGpioBackend, build_gui3_model

class glb:
    pass

MyControls = {}
backend = None
remote = None

class RemoteControlClient:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass

    def set_gpio(self, gpio: int, value: int) -> None:
        if self.sock is None:
            return
        msg = {"cmd": "set", "gpio": int(gpio), "value": int(value)}
        self.sock.sendall((json.dumps(msg) + "\n").encode())

    def _reader(self) -> None:
        assert self.sock is not None
        f = self.sock.makefile("r", encoding="utf-8")
        for line in f:
            if self.stop_event.is_set():
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("event") == "gpio":
                GLib.idle_add(MyControls[int(msg["gpio"])].change_state, 1 if int(msg["value"]) else 0)

def generate_bouncing():
    if glb.bouncing_active.get_active():
        ntr = random.choice((3, 5, 7))
        duration = int(glb.bouncing_duration.get_value())
        trs = [random.randint(0, duration) for _ in range(ntr)]
        trs.sort()
        return trs
    return (0,)

def send_change(pin, state):
    if remote is not None:
        remote.set_gpio(pin, state)
    else:
        backend.model.inject_input(pin, state)

def send_bounced_change(pin, state):
    if not glb.bouncing_active.get_active():
        send_change(pin, state)
        return
    trs = generate_bouncing()
    last = 0
    cur = state
    for trans in trs:
        time.sleep(0.001 * (trans - last))
        last = trans
        send_change(pin, cur)
        cur = 1 - cur

def recv_change(pin, state):
    GLib.idle_add(MyControls[pin].change_state, state)

class MySwitch(Gtk.Switch):
    def __init__(self, number):
        super().__init__()
        self.number = number
    def change_state(self, state):
        return False

class MyButton(Gtk.Button):
    def __init__(self, number):
        super().__init__(label=str(number))
        self.number = number
    def change_state(self, state):
        return False

class MyLed(Gtk.Label):
    color = Gdk.color_parse("gray")
    rgba0 = Gdk.RGBA.from_color(color)
    color = Gdk.color_parse("green")
    rgba1 = Gdk.RGBA.from_color(color)
    del color
    def __init__(self, number):
        super().__init__(label=str(number))
        self.number = number
        self.state = 0
        self.change_state(0)
    def change_state(self, state):
        self.state = 1 if state else 0
        self.override_background_color(Gtk.StateFlags.NORMAL, self.rgba1 if self.state else self.rgba0)
        return False

class SwitchBoardWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="GPIO GUI")
        self.set_border_width(10)
        mainvbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(mainvbox)

        label = Gtk.Label(label="Stable switches")
        mainvbox.pack_start(label, True, True, 0)
        hbox = Gtk.Box(spacing=6)
        for i in range(0, 12):
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            label = Gtk.Label(label=str(i))
            vbox.pack_start(label, True, True, 0)
            switch = MySwitch(i)
            switch.connect("state_set", self.on_switch_activated)
            switch.set_active(False)
            MyControls[i] = switch
            vbox.pack_start(switch, True, True, 0)
            hbox.pack_start(vbox, True, True, 0)
        mainvbox.pack_start(hbox, True, True, 0)

        label = Gtk.Label(label="Buttons")
        mainvbox.pack_start(label, True, True, 0)
        hbox = Gtk.Box(spacing=6)
        for i in range(12, 24):
            button = MyButton(i)
            button.connect("button-press-event", self.on_button_clicked, 0)
            button.connect("button-release-event", self.on_button_clicked, 1)
            MyControls[i] = button
            hbox.pack_start(button, True, True, 0)
        mainvbox.pack_start(hbox, True, True, 0)

        label = Gtk.Label(label="LEDs")
        mainvbox.pack_start(label, True, True, 0)
        hbox = Gtk.Box(spacing=6)
        for i in range(24, 32):
            led = MyLed(i)
            MyControls[i] = led
            hbox.pack_start(led, True, True, 0)
        mainvbox.pack_start(hbox, True, True, 0)

        hbox = Gtk.Box(spacing=6)
        button = Gtk.CheckButton(label="Bouncing")
        button.set_active(True)
        glb.bouncing_active = button
        hbox.pack_start(button, True, True, 0)
        label = Gtk.Label(label="duration [ms]")
        hbox.pack_start(label, True, True, 0)
        spinner = Gtk.SpinButton()
        spinner.set_range(0, 300)
        spinner.set_value(200)
        spinner.set_increments(1, 10)
        glb.bouncing_duration = spinner
        hbox.pack_start(spinner, True, True, 0)
        mainvbox.pack_start(hbox, True, True, 0)

    def on_switch_activated(self, switch, _gparam):
        state = 1 if switch.get_active() else 0
        send_bounced_change(switch.number, state)
        return True

    def on_button_clicked(self, button, _gparam, state):
        send_bounced_change(button.number, state)
        return True

def main():
    global backend, remote
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", default="/tmp/gpio.sock")
    parser.add_argument("--control-socket")
    parser.add_argument("--embed-backend", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.embed_backend:
        model = build_gui3_model(output_callback=recv_change)
        backend = VhostUserGpioBackend(args.socket_path, model, verbose=args.verbose)
        backend.start()
    else:
        if not args.control_socket:
            parser.error("--control-socket is required unless --embed-backend is used")
        remote = RemoteControlClient(args.control_socket)
        remote.start()

    win = SwitchBoardWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    try:
        Gtk.main()
    finally:
        if remote is not None:
            remote.stop()
        if backend is not None:
            backend.stop()

if __name__ == "__main__":
    main()
