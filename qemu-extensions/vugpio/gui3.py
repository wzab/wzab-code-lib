#!/usr/bin/env python3
"""GTK demo frontend for the vugpio backend.

This file intentionally knows nothing about the vhost-user protocol details.
It defines a board layout locally and talks to the backend through a small
controller interface. The backend may be embedded in-process or accessed over
its JSON control socket.
"""

from __future__ import annotations

import argparse
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol, Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from vugpio import (
    GpioControlClient,
    GpioLineConfig,
    VhostUserGpioBackend,
    VIRTIO_GPIO_DIRECTION_IN,
    VIRTIO_GPIO_DIRECTION_OUT,
    build_model_from_config,
)


# ---------------------------------------------------------------------------
# Board description
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InputToggle:
    gpio: int
    label: str


@dataclass(frozen=True)
class InputButton:
    gpio: int
    label: str
    released_value: int = 1
    pressed_value: int = 0


@dataclass(frozen=True)
class OutputIndicator:
    gpio: int
    label: str


@dataclass(frozen=True)
class BoardSpec:
    toggles: Sequence[InputToggle]
    buttons: Sequence[InputButton]
    indicators: Sequence[OutputIndicator]

    def gpio_line_configs(self) -> List[GpioLineConfig]:
        max_gpio = max(
            [line.gpio for line in self.toggles]
            + [line.gpio for line in self.buttons]
            + [line.gpio for line in self.indicators]
        )
        configs: List[Optional[GpioLineConfig]] = [None] * (max_gpio + 1)
        for item in self.toggles:
            configs[item.gpio] = GpioLineConfig(item.label, VIRTIO_GPIO_DIRECTION_IN, 0)
        for item in self.buttons:
            configs[item.gpio] = GpioLineConfig(item.label, VIRTIO_GPIO_DIRECTION_IN, item.released_value)
        for item in self.indicators:
            configs[item.gpio] = GpioLineConfig(item.label, VIRTIO_GPIO_DIRECTION_OUT, 0)
        for idx, cfg in enumerate(configs):
            if cfg is None:
                configs[idx] = GpioLineConfig(f"gpio{idx}")
        return [cfg for cfg in configs if cfg is not None]


DEMO_BOARD = BoardSpec(
    toggles=[InputToggle(i, f"sw{i}") for i in range(0, 12)],
    buttons=[InputButton(i, f"btn{i}") for i in range(12, 24)],
    indicators=[OutputIndicator(i, f"led{i}") for i in range(24, 32)],
)


# ---------------------------------------------------------------------------
# Controller abstraction
# ---------------------------------------------------------------------------

class GpioFrontendController(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def set_input(self, gpio: int, value: int) -> None: ...


class RemoteBackendController:
    def __init__(self, socket_path: str, on_output: Callable[[int, int], None]):
        self._client = GpioControlClient(socket_path, on_gpio=on_output)

    def start(self) -> None:
        self._client.start()

    def stop(self) -> None:
        self._client.stop()

    def set_input(self, gpio: int, value: int) -> None:
        self._client.set_gpio(gpio, value)


class EmbeddedBackendController:
    def __init__(
        self,
        socket_path: str,
        control_socket: Optional[str],
        board: BoardSpec,
        on_output: Callable[[int, int], None],
        verbose: bool = False,
    ):
        self._model = build_model_from_config(board.gpio_line_configs(), output_callback=on_output)
        self._backend = VhostUserGpioBackend(socket_path, self._model, verbose=verbose)
        self._control_socket = control_socket

    def start(self) -> None:
        self._backend.start()
        if self._control_socket:
            self._backend.enable_gui_control(self._control_socket)

    def stop(self) -> None:
        self._backend.stop()

    def set_input(self, gpio: int, value: int) -> None:
        self._backend.inject_gpio(gpio, value)


# ---------------------------------------------------------------------------
# GTK widgets
# ---------------------------------------------------------------------------

class IndicatorLabel(Gtk.Label):
    _off_color = Gdk.RGBA.from_color(Gdk.color_parse("gray"))
    _on_color = Gdk.RGBA.from_color(Gdk.color_parse("green"))

    def __init__(self, label: str):
        super().__init__(label=label)
        self.change_state(0)

    def change_state(self, state: int) -> bool:
        self.override_background_color(
            Gtk.StateFlags.NORMAL,
            self._on_color if state else self._off_color,
        )
        return False


class InputSwitch(Gtk.Switch):
    def __init__(self, gpio: int):
        super().__init__()
        self.gpio = gpio

    def change_state(self, _state: int) -> bool:
        return False


class InputButtonWidget(Gtk.Button):
    def __init__(self, gpio: int, label: str):
        super().__init__(label=label)
        self.gpio = gpio

    def change_state(self, _state: int) -> bool:
        return False


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class SwitchBoardWindow(Gtk.Window):
    def __init__(self, controller: GpioFrontendController, board: BoardSpec):
        super().__init__(title="GPIO GUI")
        self.controller = controller
        self.board = board
        self.controls: Dict[int, Gtk.Widget] = {}
        self.set_border_width(10)

        self._bouncing_checkbox = Gtk.CheckButton(label="Bouncing")
        self._bouncing_checkbox.set_active(True)
        self._bouncing_duration = Gtk.SpinButton()
        self._bouncing_duration.set_range(0, 300)
        self._bouncing_duration.set_value(200)
        self._bouncing_duration.set_increments(1, 10)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(main)

        main.pack_start(Gtk.Label(label="Stable switches"), True, True, 0)
        main.pack_start(self._build_toggle_row(), True, True, 0)

        main.pack_start(Gtk.Label(label="Buttons"), True, True, 0)
        main.pack_start(self._build_button_row(), True, True, 0)

        main.pack_start(Gtk.Label(label="LEDs"), True, True, 0)
        main.pack_start(self._build_indicator_row(), True, True, 0)

        bounce_row = Gtk.Box(spacing=6)
        bounce_row.pack_start(self._bouncing_checkbox, True, True, 0)
        bounce_row.pack_start(Gtk.Label(label="duration [ms]"), True, True, 0)
        bounce_row.pack_start(self._bouncing_duration, True, True, 0)
        main.pack_start(bounce_row, True, True, 0)

    def _build_toggle_row(self) -> Gtk.Box:
        row = Gtk.Box(spacing=6)
        for item in self.board.toggles:
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            column.pack_start(Gtk.Label(label=str(item.gpio)), True, True, 0)
            widget = InputSwitch(item.gpio)
            widget.connect("state_set", self._on_switch_activated)
            widget.set_active(False)
            self.controls[item.gpio] = widget
            column.pack_start(widget, True, True, 0)
            row.pack_start(column, True, True, 0)
        return row

    def _build_button_row(self) -> Gtk.Box:
        row = Gtk.Box(spacing=6)
        for item in self.board.buttons:
            widget = InputButtonWidget(item.gpio, str(item.gpio))
            widget.connect("button-press-event", self._on_button_clicked, item.pressed_value)
            widget.connect("button-release-event", self._on_button_clicked, item.released_value)
            self.controls[item.gpio] = widget
            row.pack_start(widget, True, True, 0)
        return row

    def _build_indicator_row(self) -> Gtk.Box:
        row = Gtk.Box(spacing=6)
        for item in self.board.indicators:
            widget = IndicatorLabel(str(item.gpio))
            self.controls[item.gpio] = widget
            row.pack_start(widget, True, True, 0)
        return row

    def _generate_bouncing(self) -> Sequence[int]:
        if self._bouncing_checkbox.get_active():
            n_transitions = random.choice((3, 5, 7))
            duration = int(self._bouncing_duration.get_value())
            transitions = [random.randint(0, duration) for _ in range(n_transitions)]
            transitions.sort()
            return transitions
        return (0,)

    def _send_change(self, gpio: int, value: int) -> None:
        self.controller.set_input(gpio, value)

    def _send_bounced_change(self, gpio: int, value: int) -> None:
        if not self._bouncing_checkbox.get_active():
            self._send_change(gpio, value)
            return

        transitions = self._generate_bouncing()
        last = 0
        current = value
        for point in transitions:
            time.sleep(0.001 * (point - last))
            last = point
            self._send_change(gpio, current)
            current = 1 - current

    def _on_switch_activated(self, widget: InputSwitch, state: bool) -> bool:
        value = 1 if state else 0
        self._send_bounced_change(widget.gpio, value)
        return False

    def _on_button_clicked(self, widget: InputButtonWidget, _gparam, state: int) -> bool:
        self._send_bounced_change(widget.gpio, state)
        return True

    def update_output(self, gpio: int, value: int) -> bool:
        control = self.controls.get(gpio)
        if control is not None and hasattr(control, "change_state"):
            getattr(control, "change_state")(value)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GTK demo frontend for vugpio")
    parser.add_argument("--socket-path", default="/tmp/gpio.sock", help="vhost-user socket path")
    parser.add_argument("--control-socket", default="/tmp/gpio-gui.sock", help="JSON control socket path")
    parser.add_argument(
        "--embed-backend",
        action="store_true",
        help="run the backend in-process instead of connecting to an external one",
    )
    parser.add_argument("--verbose", action="store_true", help="enable verbose backend logs in embedded mode")
    args = parser.parse_args()

    window_ref: Dict[str, SwitchBoardWindow] = {}

    def on_output(gpio: int, value: int) -> None:
        window = window_ref.get("window")
        if window is not None:
            GLib.idle_add(window.update_output, gpio, value)

    if args.embed_backend:
        controller: GpioFrontendController = EmbeddedBackendController(
            socket_path=args.socket_path,
            control_socket=args.control_socket,
            board=DEMO_BOARD,
            on_output=on_output,
            verbose=args.verbose,
        )
    else:
        controller = RemoteBackendController(args.control_socket, on_output=on_output)

    controller.start()
    window = SwitchBoardWindow(controller, DEMO_BOARD)
    window_ref["window"] = window
    window.connect("destroy", Gtk.main_quit)
    window.show_all()

    try:
        Gtk.main()
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
