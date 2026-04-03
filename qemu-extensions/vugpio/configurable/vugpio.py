#!/usr/bin/env python3
"""Python vhost-user virtio-gpio backend.

Developed by Wojciech M. Zabolotny (wzab01@gmail.com) with significant help
from ChatGPT (2026.04.03)

Published under Creative Commons CC0 License

This backend implements a compact, self-contained virtio-gpio device that can
be used with QEMU over vhost-user. It was developed against the Linux
`gpio-virtio` driver and shaped by behaviour observed from rust-vmm's
`vhost-device-gpio`.

Highlights:
- two virtqueues: request queue and event queue
- line names, directions, values and IRQ type configuration
- optional UNIX control socket for driving inputs from a separate GUI process
- conservative transport defaults chosen for interoperability with QEMU/Linux
- optional detailed tracing for protocol-level debugging

"""

from __future__ import annotations

import argparse
import array
import dataclasses
from dataclasses import dataclass, field
import errno
import json
import logging
import mmap
import os
import selectors
import socket
import struct
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

LOG = logging.getLogger("vugpio")
__version__ = "007"

# ---------------------------------------------------------------------------
# vhost-user constants
# ---------------------------------------------------------------------------

VHOST_USER_GET_FEATURES = 1
VHOST_USER_SET_FEATURES = 2
VHOST_USER_SET_OWNER = 3
VHOST_USER_RESET_OWNER = 4
VHOST_USER_SET_MEM_TABLE = 5
VHOST_USER_SET_VRING_NUM = 8
VHOST_USER_SET_VRING_ADDR = 9
VHOST_USER_SET_VRING_BASE = 10
VHOST_USER_GET_VRING_BASE = 11
VHOST_USER_SET_VRING_KICK = 12
VHOST_USER_SET_VRING_CALL = 13
VHOST_USER_SET_VRING_ERR = 14
VHOST_USER_GET_PROTOCOL_FEATURES = 15
VHOST_USER_SET_PROTOCOL_FEATURES = 16
VHOST_USER_GET_QUEUE_NUM = 17
VHOST_USER_SET_VRING_ENABLE = 18
VHOST_USER_GET_CONFIG = 24

VHOST_USER_VERSION = 0x1
VHOST_USER_REPLY_MASK = 0x4
VHOST_USER_NEED_REPLY_MASK = 0x8

# vhost-user "backend features"
VHOST_USER_F_PROTOCOL_FEATURES = 30

# vhost-user protocol features
VHOST_USER_PROTOCOL_F_MQ = 0
VHOST_USER_PROTOCOL_F_REPLY_ACK = 3
VHOST_USER_PROTOCOL_F_CONFIG = 9

# virtio generic features
VIRTIO_F_NOTIFY_ON_EMPTY = 24
VIRTIO_F_VERSION_1 = 32
VIRTIO_RING_F_INDIRECT_DESC = 28
VIRTIO_RING_F_EVENT_IDX = 29

# virtio-gpio feature bits
VIRTIO_GPIO_F_IRQ = 0

# virtio-gpio request types
VIRTIO_GPIO_MSG_GET_LINE_NAMES = 0x0001
VIRTIO_GPIO_MSG_GET_NAMES = VIRTIO_GPIO_MSG_GET_LINE_NAMES  # compatibility alias
VIRTIO_GPIO_MSG_GET_DIRECTION = 0x0002
VIRTIO_GPIO_MSG_SET_DIRECTION = 0x0003
VIRTIO_GPIO_MSG_GET_VALUE = 0x0004
VIRTIO_GPIO_MSG_SET_VALUE = 0x0005
VIRTIO_GPIO_MSG_IRQ_TYPE = 0x0006

VIRTIO_GPIO_STATUS_OK = 0x0
VIRTIO_GPIO_STATUS_ERR = 0x1
VIRTIO_GPIO_IRQ_STATUS_INVALID = 0x0
VIRTIO_GPIO_IRQ_STATUS_VALID = 0x1

# virtio-gpio line directions (per spec / Linux driver expectations)
VIRTIO_GPIO_DIRECTION_NONE = 0
VIRTIO_GPIO_DIRECTION_OUT = 1
VIRTIO_GPIO_DIRECTION_IN = 2

# irq types
VIRTIO_GPIO_IRQ_TYPE_NONE = 0
VIRTIO_GPIO_IRQ_TYPE_EDGE_RISING = 1
VIRTIO_GPIO_IRQ_TYPE_EDGE_FALLING = 2
VIRTIO_GPIO_IRQ_TYPE_EDGE_BOTH = 3
VIRTIO_GPIO_IRQ_TYPE_LEVEL_HIGH = 4
VIRTIO_GPIO_IRQ_TYPE_LEVEL_LOW = 8

VRING_DESC_F_NEXT = 1
VRING_DESC_F_WRITE = 2
VRING_DESC_F_INDIRECT = 4

REQUEST_NAMES = {
    1: "GET_FEATURES",
    2: "SET_FEATURES",
    3: "SET_OWNER",
    4: "RESET_OWNER",
    5: "SET_MEM_TABLE",
    8: "SET_VRING_NUM",
    9: "SET_VRING_ADDR",
    10: "SET_VRING_BASE",
    11: "GET_VRING_BASE",
    12: "SET_VRING_KICK",
    13: "SET_VRING_CALL",
    14: "SET_VRING_ERR",
    15: "GET_PROTOCOL_FEATURES",
    16: "SET_PROTOCOL_FEATURES",
    17: "GET_QUEUE_NUM",
    18: "SET_VRING_ENABLE",
    24: "GET_CONFIG",
}

_t0 = time.monotonic()
def _ts() -> str:
    return f"{time.monotonic() - _t0:9.6f}"

TRACE_ENABLED = False

def _trace(*args, force: bool = False, **kwargs) -> None:
    if force or TRACE_ENABLED:
        print(*args, **kwargs)

def gpio_direction_name(direction: int) -> str:
    return {
        VIRTIO_GPIO_DIRECTION_NONE: "none",
        VIRTIO_GPIO_DIRECTION_OUT: "out",
        VIRTIO_GPIO_DIRECTION_IN: "in",
    }.get(direction, f"unknown({direction})")


U32 = struct.Struct("<I")
U64 = struct.Struct("<Q")
VRING_STATE = struct.Struct("<II")
VRING_ADDR = struct.Struct("<IIQQQQ")
MEM_HEADER = struct.Struct("<II")
MEM_REGION = struct.Struct("<QQQQ")
VHOST_HDR = struct.Struct("<III")

# virtio-gpio structs
VIRTIO_GPIO_REQ = struct.Struct("<HHI")    # rtype:u16 gpio:u16 value:u32
VIRTIO_GPIO_IRQ_REQ = struct.Struct("<H")
VIRTIO_GPIO_CFG = struct.Struct("<H2xI")    # ngpio + padding + gpio_names_size
MAX_MSG_SIZE = 0x1000


# ---------------------------------------------------------------------------
# Reusable GPIO model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GpioLineConfig:
    """Declarative configuration of one GPIO line.

    This keeps board layout description outside of the protocol/backend logic,
    so different frontends can define their own line sets without modifying the
    transport implementation.
    """

    name: str
    direction: int = VIRTIO_GPIO_DIRECTION_NONE
    initial_value: int = 0
    irq_type: int = VIRTIO_GPIO_IRQ_TYPE_NONE


@dataclass
class GpioLine:
    name: str
    direction: int = VIRTIO_GPIO_DIRECTION_NONE
    value: int = 0
    irq_type: int = VIRTIO_GPIO_IRQ_TYPE_NONE


class CallbackDispatcher:
    """Fan-out helper for backend output notifications."""

    def __init__(self) -> None:
        self._callbacks: List[Callable[[int, int], None]] = []
        self._lock = threading.RLock()

    def add(self, callback: Optional[Callable[[int, int], None]]) -> None:
        if callback is None:
            return
        with self._lock:
            self._callbacks.append(callback)

    def remove(self, callback: Callable[[int, int], None]) -> None:
        with self._lock:
            self._callbacks = [cb for cb in self._callbacks if cb != callback]

    def __call__(self, gpio: int, value: int) -> None:
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            cb(gpio, value)


class GpioModel:
    def __init__(self, lines: Sequence[GpioLine], output_callback: Optional[Callable[[int, int], None]] = None):
        if not lines:
            raise ValueError("GpioModel requires at least one line")
        self.lines: List[GpioLine] = list(lines)
        self.ngpio = len(self.lines)
        self.lock = threading.RLock()
        self.output_dispatcher = CallbackDispatcher()
        self.output_dispatcher.add(output_callback)
        self.event_queue_buffers: List[Tuple[int, int]] = []  # compatibility placeholder

    @classmethod
    def from_config(
        cls,
        configs: Sequence[GpioLineConfig],
        output_callback: Optional[Callable[[int, int], None]] = None,
    ) -> "GpioModel":
        lines = [
            GpioLine(
                name=cfg.name,
                direction=cfg.direction,
                value=1 if cfg.initial_value else 0,
                irq_type=cfg.irq_type,
            )
            for cfg in configs
        ]
        return cls(lines, output_callback=output_callback)

    def add_output_callback(self, callback: Callable[[int, int], None]) -> None:
        self.output_dispatcher.add(callback)

    def names_blob(self) -> bytes:
        with self.lock:
            names = b"".join((ln.name.encode("utf-8") + b"\x00") for ln in self.lines)
        return names

    def names_size(self) -> int:
        return len(self.names_blob())

    def get_direction(self, gpio: int) -> int:
        with self.lock:
            return self.lines[gpio].direction

    def set_direction(self, gpio: int, direction: int) -> None:
        if direction not in (
            VIRTIO_GPIO_DIRECTION_NONE,
            VIRTIO_GPIO_DIRECTION_OUT,
            VIRTIO_GPIO_DIRECTION_IN,
        ):
            raise ValueError(f"invalid gpio direction {direction}")
        with self.lock:
            self.lines[gpio].direction = direction

    def get_value(self, gpio: int) -> int:
        with self.lock:
            return self.lines[gpio].value

    def set_value_from_guest(self, gpio: int, value: int) -> None:
        with self.lock:
            self.lines[gpio].value = 1 if value else 0
        self.output_dispatcher(gpio, 1 if value else 0)

    def set_irq_type(self, gpio: int, irq_type: int) -> None:
        with self.lock:
            self.lines[gpio].irq_type = irq_type

    def get_irq_type(self, gpio: int) -> int:
        with self.lock:
            return self.lines[gpio].irq_type

    def inject_input(self, gpio: int, value: int) -> None:
        with self.lock:
            self.lines[gpio].value = 1 if value else 0

    def config_blob(self) -> bytes:
        return VIRTIO_GPIO_CFG.pack(self.ngpio, self.names_size())


def build_model_from_config(
    configs: Sequence[GpioLineConfig],
    output_callback: Optional[Callable[[int, int], None]] = None,
) -> GpioModel:
    return GpioModel.from_config(configs, output_callback=output_callback)


def default_demo_line_configs() -> List[GpioLineConfig]:
    configs: List[GpioLineConfig] = []
    configs.extend(
        GpioLineConfig(name=f"sw{i}", direction=VIRTIO_GPIO_DIRECTION_IN)
        for i in range(0, 12)
    )
    configs.extend(
        GpioLineConfig(name=f"btn{i}", direction=VIRTIO_GPIO_DIRECTION_IN, initial_value=1)
        for i in range(12, 24)
    )
    configs.extend(
        GpioLineConfig(name=f"led{i}", direction=VIRTIO_GPIO_DIRECTION_OUT)
        for i in range(24, 32)
    )
    return configs



def board_line_configs_from_module() -> List[GpioLineConfig]:
    """Load GPIO line configuration from boardconfig.BOARD_LINES.

    This intentionally ignores any GUI-only metadata such as "role".
    """
    from boardconfig import BOARD_LINES

    direction_map = {
        "none": VIRTIO_GPIO_DIRECTION_NONE,
        "in": VIRTIO_GPIO_DIRECTION_IN,
        "out": VIRTIO_GPIO_DIRECTION_OUT,
    }

    max_gpio = max(line.gpio for line in BOARD_LINES)
    configs: List[Optional[GpioLineConfig]] = [None] * (max_gpio + 1)
    for line in BOARD_LINES:
        configs[line.gpio] = GpioLineConfig(
            name=line.name,
            direction=direction_map[line.initial_direction],
            initial_value=1 if line.initial_value else 0,
        )

    for gpio, cfg in enumerate(configs):
        if cfg is None:
            configs[gpio] = GpioLineConfig(name=f"gpio{gpio}")

    return [cfg for cfg in configs if cfg is not None]


def build_demo_model(output_callback: Optional[Callable[[int, int], None]] = None) -> GpioModel:
    return build_model_from_config(default_demo_line_configs(), output_callback=output_callback)


# Backward-compatible alias used by existing local scripts.
build_gui3_model = build_demo_model

# ---------------------------------------------------------------------------
# Memory and queue state
# ---------------------------------------------------------------------------

@dataclass
class MemoryRegion:
    guest_addr: int
    size: int
    user_addr: int
    mmap_offset: int
    fd: int
    mm: mmap.mmap

    def contains_user(self, addr: int, size: int = 1) -> bool:
        return self.user_addr <= addr and (addr + size) <= (self.user_addr + self.size)

    def offset_for_user(self, addr: int) -> int:
        return self.mmap_offset + (addr - self.user_addr)


class GuestMemoryMap:
    def __init__(self) -> None:
        self.regions: List[MemoryRegion] = []
        self._page_size = mmap.PAGESIZE

    def _flush_region(self, r: MemoryRegion, off: int, length: int) -> None:
        if length <= 0:
            return
        page_off = off & ~(self._page_size - 1)
        end = off + length
        page_end = (end + self._page_size - 1) & ~(self._page_size - 1)
        try:
            r.mm.flush(page_off, page_end - page_off)
        except (BufferError, OSError, ValueError):
            try:
                r.mm.flush()
            except Exception:
                pass

    def flush_user(self, addr: int, size: int) -> None:
        r = self.find_region_for_user(addr, size)
        self._flush_region(r, r.offset_for_user(addr), size)

    def flush_guest(self, addr: int, size: int) -> None:
        r = self.find_region_for_guest(addr, size)
        self._flush_region(r, self._guest_offset(r, addr), size)

    def reset(self) -> None:
        for r in self.regions:
            try:
                r.mm.close()
            except Exception:
                pass
            try:
                os.close(r.fd)
            except OSError:
                pass
        self.regions.clear()

    def add_regions(self, regions: List[MemoryRegion]) -> None:
        self.reset()
        self.regions = regions

    def find_region_for_user(self, addr: int, size: int = 1) -> MemoryRegion:
        for r in self.regions:
            if r.contains_user(addr, size):
                return r
        raise KeyError(f"user address 0x{addr:x} size={size} not in any mapped region")

    def find_region_for_guest(self, addr: int, size: int = 1) -> MemoryRegion:
        for r in self.regions:
            if r.guest_addr <= addr and (addr + size) <= (r.guest_addr + r.size):
                return r
        raise KeyError(f"guest address 0x{addr:x} size={size} not in any mapped region")

    def _guest_offset(self, r: MemoryRegion, addr: int) -> int:
        return r.mmap_offset + (addr - r.guest_addr)

    def read(self, addr: int, size: int) -> bytes:
        # For vring tables QEMU passes user-space addresses in SET_VRING_ADDR.
        r = self.find_region_for_user(addr, size)
        off = r.offset_for_user(addr)
        return r.mm[off:off + size]

    def write(self, addr: int, data: bytes) -> None:
        r = self.find_region_for_user(addr, len(data))
        off = r.offset_for_user(addr)
        r.mm[off:off + len(data)] = data
        self._flush_region(r, off, len(data))

    def read_guest(self, addr: int, size: int) -> bytes:
        # Descriptors' addr fields are guest physical addresses.
        r = self.find_region_for_guest(addr, size)
        off = self._guest_offset(r, addr)
        return r.mm[off:off + size]

    def write_guest(self, addr: int, data: bytes) -> None:
        r = self.find_region_for_guest(addr, len(data))
        off = self._guest_offset(r, addr)
        r.mm[off:off + len(data)] = data
        self._flush_region(r, off, len(data))


@dataclass
class VirtQueue:
    index: int
    size: int = 0
    desc_user_addr: int = 0
    avail_user_addr: int = 0
    used_user_addr: int = 0
    enabled: bool = False
    started: bool = False
    event_idx_enabled: bool = False
    kick_fd: Optional[int] = None
    call_fd: Optional[int] = None
    err_fd: Optional[int] = None
    last_avail_idx: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)

    def configured(self) -> bool:
        return (
            self.size > 0
            and self.desc_user_addr != 0
            and self.avail_user_addr != 0
            and self.used_user_addr != 0
        )


# ---------------------------------------------------------------------------
# Queue access helpers (split virtqueues only)
# ---------------------------------------------------------------------------

@dataclass
class Desc:
    index: int
    addr: int
    length: int
    flags: int
    next: int


@dataclass
class Chain:
    head: int
    descriptors: List[Desc]
    readable: List[Desc]
    writable: List[Desc]


@dataclass
class ArmedEventBuffer:
    gpio: int
    head: int
    writable: List[Desc]


class QueueAccessor:
    DESC_STRUCT = struct.Struct("<QIHH")
    U16 = struct.Struct("<H")
    USED_ELEM = struct.Struct("<II")

    def __init__(self, mem: GuestMemoryMap, q: VirtQueue) -> None:
        self.mem = mem
        self.q = q

    def avail_idx(self) -> int:
        return self.U16.unpack(self.mem.read(self.q.avail_user_addr + 2, 2))[0]

    def used_idx(self) -> int:
        return self.U16.unpack(self.mem.read(self.q.used_user_addr + 2, 2))[0]

    def avail_ring_entry(self, slot: int) -> int:
        off = self.q.avail_user_addr + 4 + slot * 2
        return self.U16.unpack(self.mem.read(off, 2))[0]

    def _desc_from_table_user(self, table_user_addr: int, index: int) -> Desc:
        off = table_user_addr + index * 16
        addr, length, flags, nxt = self.DESC_STRUCT.unpack(self.mem.read(off, 16))
        return Desc(index=index, addr=addr, length=length, flags=flags, next=nxt)

    def _desc_from_table_guest(self, table_guest_addr: int, index: int) -> Desc:
        off = table_guest_addr + index * 16
        addr, length, flags, nxt = self.DESC_STRUCT.unpack(self.mem.read_guest(off, 16))
        return Desc(index=index, addr=addr, length=length, flags=flags, next=nxt)

    def desc(self, index: int) -> Desc:
        return self._desc_from_table_user(self.q.desc_user_addr, index)

    def _collect_indirect(self, table_guest_addr: int, table_len: int) -> Tuple[List[Desc], List[Desc], List[Desc]]:
        if table_len % 16 != 0:
            raise RuntimeError("indirect descriptor length must be multiple of 16")
        count = table_len // 16
        out: List[Desc] = []
        readable: List[Desc] = []
        writable: List[Desc] = []
        idx = 0
        seen = set()
        while True:
            if idx in seen:
                raise RuntimeError("indirect descriptor loop")
            if idx >= count:
                raise RuntimeError("indirect descriptor index out of range")
            seen.add(idx)
            d = self._desc_from_table_guest(table_guest_addr, idx)
            # make indirect-desc entries visible in dumps
            dd = Desc(index=0x10000 + idx, addr=d.addr, length=d.length, flags=d.flags, next=d.next)
            out.append(dd)
            if d.flags & VRING_DESC_F_WRITE:
                writable.append(dd)
            else:
                readable.append(dd)
            if d.flags & VRING_DESC_F_NEXT:
                idx = d.next
            else:
                break
        return out, readable, writable

    def collect_chain(self, head: int) -> Chain:
        out: List[Desc] = []
        readable: List[Desc] = []
        writable: List[Desc] = []
        idx = head
        seen = set()
        while True:
            if idx in seen:
                raise RuntimeError("descriptor loop")
            seen.add(idx)
            d = self.desc(idx)
            if d.flags & VRING_DESC_F_INDIRECT:
                ind_out, ind_readable, ind_writable = self._collect_indirect(d.addr, d.length)
                out.extend(ind_out)
                readable.extend(ind_readable)
                writable.extend(ind_writable)
            else:
                out.append(d)
                if d.flags & VRING_DESC_F_WRITE:
                    writable.append(d)
                else:
                    readable.append(d)
            if d.flags & VRING_DESC_F_NEXT:
                idx = d.next
            else:
                break
        return Chain(head=head, descriptors=out, readable=readable, writable=writable)

    def add_used(self, head: int, length: int) -> None:
        used_idx = self.used_idx()
        slot = used_idx % self.q.size
        off = self.q.used_user_addr + 4 + slot * 8
        _trace(
            f"{_ts()} vugpio: add_used head={head} len={length} used_idx_before={used_idx} "
            f"slot={slot} off=0x{off:x}",
            flush=True,
        )
        self.mem.write(off, self.USED_ELEM.pack(head, length))
        self.mem.write(self.q.used_user_addr + 2, self.U16.pack((used_idx + 1) & 0xFFFF))
        _trace(
            f"{_ts()} vugpio: add_used used_idx_after={(used_idx + 1) & 0xFFFF}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# JSON control socket
# ---------------------------------------------------------------------------

class GpioJsonServer:
    """Simple JSON line-oriented control channel for external frontends."""

    def __init__(self, socket_path: str, model: GpioModel, inject_callback: Optional[Callable[[int, int], None]] = None) -> None:
        self.socket_path = socket_path
        self.model = model
        self.inject_callback = inject_callback
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.clients_lock = threading.RLock()
        self.clients: List[socket.socket] = []

    def start(self) -> None:
        os.makedirs(os.path.dirname(self.socket_path) or ".", exist_ok=True)
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.socket_path)
        self.sock.listen(8)
        self.thread = threading.Thread(target=self._run, name="gpio-control", daemon=True)
        self.thread.start()
        _trace(f"{_ts()} vugpio: gui-control listening on {self.socket_path}", flush=True)

    def stop(self) -> None:
        self.stop_event.set()
        with self.clients_lock:
            for c in list(self.clients):
                try:
                    c.close()
                except OSError:
                    pass
            self.clients.clear()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    def broadcast_gpio(self, gpio: int, value: int) -> None:
        payload = (json.dumps({"event": "gpio", "gpio": gpio, "value": value}) + "\n").encode()
        dead: List[socket.socket] = []
        with self.clients_lock:
            for c in self.clients:
                try:
                    c.sendall(payload)
                except OSError:
                    dead.append(c)
            for c in dead:
                try:
                    c.close()
                except OSError:
                    pass
                if c in self.clients:
                    self.clients.remove(c)

    def _run(self) -> None:
        assert self.sock is not None
        while not self.stop_event.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                if self.stop_event.is_set():
                    break
                continue
            with self.clients_lock:
                self.clients.append(conn)
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            conn.sendall((json.dumps({"event": "hello", "ngpio": self.model.ngpio}) + "\n").encode())
            for idx, line in enumerate(self.model.lines):
                conn.sendall((json.dumps({
                    "event": "line",
                    "gpio": idx,
                    "name": line.name,
                    "direction": line.direction,
                    "value": line.value,
                }) + "\n").encode())
            f = conn.makefile("r", encoding="utf-8", newline="\n")
            for line in f:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("cmd") == "set":
                    gpio = int(msg["gpio"])
                    value = int(msg["value"])
                    if self.inject_callback is not None:
                        self.inject_callback(gpio, value)
                    else:
                        self.model.inject_input(gpio, value)
        except OSError:
            pass
        finally:
            with self.clients_lock:
                if conn in self.clients:
                    self.clients.remove(conn)
            try:
                conn.close()
            except OSError:
                pass


class GpioControlClient:
    """Frontend-side JSON control client.

    GUI code can use this client without importing backend internals.
    """

    def __init__(self, socket_path: str, on_gpio: Optional[Callable[[int, int], None]] = None) -> None:
        self.socket_path = socket_path
        self.on_gpio = on_gpio
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.ngpio: Optional[int] = None
        self.line_info: Dict[int, Dict[str, object]] = {}

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)
        self.thread = threading.Thread(target=self._reader, name="gpio-control-client", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def set_gpio(self, gpio: int, value: int) -> None:
        if self.sock is None:
            raise RuntimeError("control client is not connected")
        msg = {"cmd": "set", "gpio": int(gpio), "value": int(value)}
        self.sock.sendall((json.dumps(msg) + "\n").encode())

    def _reader(self) -> None:
        assert self.sock is not None
        f = self.sock.makefile("r", encoding="utf-8", newline="\n")
        for line in f:
            if self.stop_event.is_set():
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = msg.get("event")
            if event == "hello":
                self.ngpio = int(msg["ngpio"])
            elif event == "line":
                self.line_info[int(msg["gpio"])] = msg
            elif event == "gpio" and self.on_gpio is not None:
                self.on_gpio(int(msg["gpio"]), 1 if int(msg["value"]) else 0)


# Backward-compatible alias.
GuiControlServer = GpioJsonServer

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class VhostUserGpioBackend:
    NUM_QUEUES = 2
    QUEUE_SIZE = 256

    def __init__(self, socket_path: str, model: GpioModel, *, verbose: bool = False) -> None:
        self.socket_path = socket_path
        self.model = model
        self.verbose = verbose

        self.mem = GuestMemoryMap()
        self.queues = [VirtQueue(index=i) for i in range(self.NUM_QUEUES)]

        self.owner_set = False
        self.backend_features_acked = 0
        self.acked_protocol_features = 0
        self.get_features_count = 0
        self.get_protocol_features_count = 0

        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.started_event = threading.Event()
        self.sel = selectors.DefaultSelector()
        self.lock = threading.RLock()
        self.gui_server: Optional[GpioJsonServer] = None
        self.armed_event_buffers: List[ArmedEventBuffer] = []


    def inject_gpio(self, gpio: int, value: int) -> None:
        old_value = self.model.get_value(gpio)
        self.model.inject_input(gpio, value)
        new_value = self.model.get_value(gpio)
        if self._queue_runnable(1):
            try:
                self._process_event_queue(1)
                self._emit_irq_event_if_armed(gpio, old_value, new_value)
            except Exception as exc:
                _trace(f"{_ts()} vugpio: inject_gpio event processing failed: {exc!r}", flush=True)

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        os.makedirs(os.path.dirname(self.socket_path) or ".", exist_ok=True)
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        self.thread = threading.Thread(target=self._run, name="vugpio", daemon=True)
        self.thread.start()
        self.started_event.wait(2.0)

    def stop(self) -> None:
        self.stop_event.set()
        if self.gui_server is not None:
            self.gui_server.stop()
            self.gui_server = None
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self._reset_state("stop")

    def enable_gui_control(self, control_socket: str) -> None:
        self.gui_server = GpioJsonServer(control_socket, self.model, inject_callback=self.inject_gpio)
        self.gui_server.start()

    # -- reset/debug --------------------------------------------------------

    def _reset_state(self, reason: str) -> None:
        _trace(f"{_ts()} vugpio: reset_state reason={reason}", flush=True)
        self.owner_set = False
        self.backend_features_acked = 0
        self.acked_protocol_features = 0
        self.get_features_count = 0
        self.get_protocol_features_count = 0
        self.mem.reset()
        self.armed_event_buffers.clear()
        for q in self.queues:
            if q.kick_fd is not None:
                try:
                    self.sel.unregister(q.kick_fd)
                except Exception:
                    pass
            for attr in ("kick_fd", "call_fd", "err_fd"):
                fd = getattr(q, attr)
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    setattr(q, attr, None)
            q.size = 0
            q.desc_user_addr = 0
            q.avail_user_addr = 0
            q.used_user_addr = 0
            q.enabled = False
            q.started = False
            q.event_idx_enabled = False
            q.last_avail_idx = 0
        self._debug_dump_queues(reason)


    def _queue_runnable(self, qindex: int) -> bool:
        q = self.queues[qindex]
        return q.enabled and q.configured() and q.kick_fd is not None and q.call_fd is not None

    def _debug_dump_queues(self, label: str) -> None:
        _trace(f"{_ts()} vugpio: queues after {label}", flush=True)
        for q in self.queues:
            _trace(
                f"{_ts()} vugpio: q{q.index} size={q.size} enabled={q.enabled} started={q.started} "
                f"desc=0x{q.desc_user_addr:x} avail=0x{q.avail_user_addr:x} used=0x{q.used_user_addr:x} "
                f"kick_fd={q.kick_fd} call_fd={q.call_fd} err_fd={q.err_fd} last_avail_idx={q.last_avail_idx}",
                flush=True,
            )

    # -- core server --------------------------------------------------------

    def _run(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.socket_path)
        self.sock.listen(1)
        self.started_event.set()
        LOG.info("listening on %s", self.socket_path)
        _trace(f"{_ts()} vugpio: listening on {self.socket_path}", flush=True)

        while not self.stop_event.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                if self.stop_event.is_set():
                    break
                continue
            self._reset_state("new-frontend")
            conn.settimeout(1.0)
            _trace(f"{_ts()} vugpio: frontend connected", flush=True)
            _trace(f"{_ts()} vugpio: waiting for further handshake...", flush=True)
            _trace(f"{_ts()} vugpio: mode=rustvmm-style-full (full features, conservative kicks)", flush=True)
            try:
                self._serve_connection(conn)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                self._reset_state("frontend-disconnect")
                _trace(f"{_ts()} vugpio: frontend disconnected", flush=True)

    def _serve_connection(self, conn: socket.socket) -> None:
        self._rx_buffer = bytearray()
        self._fd_buckets: List[Tuple[int, List[int]]] = []
        while not self.stop_event.is_set():
            try:
                _trace(f"{_ts()} vugpio: waiting for next message...", flush=True)
                req, flags, payload, fds = self._recv_msg(conn)
            except TimeoutError:
                _trace(
                    f"{_ts()} vugpio: timeout waiting owner={self.owner_set} "
                    f"acked_features=0x{self.backend_features_acked:x} "
                    f"acked_pfeatures=0x{self.acked_protocol_features:x} "
                    f"get_features_count={self.get_features_count}",
                    flush=True,
                )
                continue
            if req is None:
                return
            _trace(
                f"{_ts()} vugpio: recv request={req}({REQUEST_NAMES.get(req,'UNKNOWN')}) "
                f"flags=0x{flags:x} size={len(payload)} fds={fds}",
                flush=True,
            )
            try:
                self._handle_msg(conn, req, flags, payload, fds)
                _trace(f"{_ts()} vugpio: handled request={req}", flush=True)
            finally:
                for fd in fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    def _message_needs_fd(self, req: int, payload: bytes) -> bool:
        if req == VHOST_USER_SET_MEM_TABLE:
            return True
        if req in (VHOST_USER_SET_VRING_KICK, VHOST_USER_SET_VRING_CALL, VHOST_USER_SET_VRING_ERR):
            if len(payload) < 8:
                return False
            (u64_val,) = U64.unpack(payload[:8])
            return not bool(u64_val & (1 << 8))
        return False

    def _next_complete_message(self) -> Optional[Tuple[int, int, bytes]]:
        if len(self._rx_buffer) < VHOST_HDR.size:
            return None
        req, flags, size = VHOST_HDR.unpack(self._rx_buffer[:VHOST_HDR.size])
        total = VHOST_HDR.size + size
        if len(self._rx_buffer) < total:
            return None
        payload = bytes(self._rx_buffer[VHOST_HDR.size:total])
        del self._rx_buffer[:total]
        return req, flags, payload

    def _claim_fds_for_message(self, req: int, payload: bytes) -> List[int]:
        if not self._message_needs_fd(req, payload):
            return []
        if not self._fd_buckets:
            return []
        _nbytes, fds = self._fd_buckets.pop(0)
        return fds

    def _recv_msg(self, conn: socket.socket) -> Tuple[Optional[int], int, bytes, List[int]]:
        parsed = self._next_complete_message()
        if parsed is not None:
            req, flags, payload = parsed
            return req, flags, payload, self._claim_fds_for_message(req, payload)

        cmsg_space = socket.CMSG_SPACE(16 * array.array("i").itemsize)
        while True:
            try:
                data, ancdata, _flags, _addr = conn.recvmsg(MAX_MSG_SIZE, cmsg_space)
            except socket.timeout:
                raise TimeoutError
            except OSError as exc:
                if exc.errno in (errno.EPIPE, errno.ECONNRESET):
                    return None, 0, b"", []
                raise

            if not data:
                _trace(f"{_ts()} vugpio: EOF while reading from socket", flush=True)
                return None, 0, b"", []

            fds: List[int] = []
            for level, ctype, cdata in ancdata:
                if level == socket.SOL_SOCKET and ctype == socket.SCM_RIGHTS:
                    arr = array.array("i")
                    arr.frombytes(cdata[: len(cdata) - (len(cdata) % arr.itemsize)])
                    fds.extend(arr.tolist())

            self._rx_buffer.extend(data)
            if fds:
                self._fd_buckets.append((len(data), fds))

            parsed = self._next_complete_message()
            if parsed is not None:
                req, flags, payload = parsed
                return req, flags, payload, self._claim_fds_for_message(req, payload)

    def _send_reply(self, conn: socket.socket, request: int, payload: bytes = b"") -> None:
        hdr = VHOST_HDR.pack(request, VHOST_USER_VERSION | VHOST_USER_REPLY_MASK, len(payload))
        if self.verbose:
            _trace(f"{_ts()} vugpio: send reply request={request} size={len(payload)}", flush=True)
        conn.sendall(hdr + payload)

    def _maybe_ack(self, conn: socket.socket, request: int, flags: int, ok: bool = True) -> None:
        if (flags & VHOST_USER_NEED_REPLY_MASK) and (self.acked_protocol_features & (1 << VHOST_USER_PROTOCOL_F_REPLY_ACK)):
            _trace(f"{_ts()} vugpio: REPLY_ACK request={request} ok={ok}", flush=True)
            self._send_reply(conn, request, U64.pack(0 if ok else 1))

    # -- request handling ---------------------------------------------------

    def _handle_msg(self, conn: socket.socket, request: int, flags: int, payload: bytes, fds: List[int]) -> None:
        if request == VHOST_USER_GET_FEATURES:
            # Be conservative here: only advertise features we implement
            # with high confidence. In particular, EVENT_IDX and
            # NOTIFY_ON_EMPTY subtly affect notification semantics and may
            # cause the guest to miss request completions if not handled
            # exactly like a production backend.
            feats = (
                (1 << VHOST_USER_F_PROTOCOL_FEATURES)
                | (1 << VIRTIO_F_VERSION_1)
                | (1 << VIRTIO_RING_F_INDIRECT_DESC)
                | (1 << VIRTIO_GPIO_F_IRQ)
            )
            self.get_features_count += 1
            _trace(f"{_ts()} vugpio: GET_FEATURES count={self.get_features_count} -> 0x{feats:x}", flush=True)
            self._send_reply(conn, request, U64.pack(feats))
            return

        if request == VHOST_USER_GET_PROTOCOL_FEATURES:
            pfeats = (
                (1 << VHOST_USER_PROTOCOL_F_MQ)
                | (1 << VHOST_USER_PROTOCOL_F_CONFIG)
                | (1 << VHOST_USER_PROTOCOL_F_REPLY_ACK)
            )
            self.get_protocol_features_count += 1
            _trace(f"{_ts()} vugpio: GET_PROTOCOL_FEATURES count={self.get_protocol_features_count} -> 0x{pfeats:x}", flush=True)
            self._send_reply(conn, request, U64.pack(pfeats))
            return

        if request == VHOST_USER_SET_PROTOCOL_FEATURES:
            (self.acked_protocol_features,) = U64.unpack(payload[:8])
            _trace(f"{_ts()} vugpio: SET_PROTOCOL_FEATURES acked=0x{self.acked_protocol_features:x}", flush=True)
            return

        if request == VHOST_USER_SET_OWNER:
            self.owner_set = True
            _trace(f"{_ts()} vugpio: SET_OWNER owner=True", flush=True)
            return

        if request == VHOST_USER_RESET_OWNER:
            self._reset_state("RESET_OWNER")
            return

        if request == VHOST_USER_GET_QUEUE_NUM:
            _trace(f"{_ts()} vugpio: GET_QUEUE_NUM -> {self.NUM_QUEUES}", flush=True)
            self._send_reply(conn, request, U64.pack(self.NUM_QUEUES))
            return

        if request == VHOST_USER_GET_CONFIG:
            # request payload is offset:u32 size:u32 flags:u32 payload...
            if len(payload) < 12:
                self._send_reply(conn, request, b"")
                return
            off, size, cfg_flags = struct.unpack_from("<III", payload, 0)
            cfg = bytearray(payload[:12])
            blob = self.model.config_blob()
            data = blob[off:off + size]
            if len(data) < size:
                data = data + b"\x00" * (size - len(data))
            cfg.extend(data)
            self._send_reply(conn, request, bytes(cfg))
            return

        if request == VHOST_USER_SET_FEATURES:
            (self.backend_features_acked,) = U64.unpack(payload[:8])
            _trace(f"{_ts()} vugpio: SET_FEATURES acked=0x{self.backend_features_acked:x}", flush=True)
            for q in self.queues:
                q.event_idx_enabled = bool(self.backend_features_acked & (1 << VIRTIO_RING_F_EVENT_IDX))
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_SET_MEM_TABLE:
            self._handle_set_mem_table(payload, fds)
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_SET_VRING_NUM:
            index, num = VRING_STATE.unpack(payload[:8])
            self.queues[index].size = num
            self._debug_dump_queues("SET_VRING_NUM")
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_SET_VRING_ADDR:
            index, ring_flags, desc, used, avail, _log = VRING_ADDR.unpack(payload[:40])
            q = self.queues[index]
            q.desc_user_addr = desc
            q.used_user_addr = used
            q.avail_user_addr = avail
            _trace(f"{_ts()} vugpio: SET_VRING_ADDR q={index} flags=0x{ring_flags:x} desc=0x{desc:x} avail=0x{avail:x} used=0x{used:x}", flush=True)
            self._debug_dump_queues("SET_VRING_ADDR")
            _trace(f"{_ts()} vugpio: q{index} runnable={self._queue_runnable(index)}", flush=True)
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_SET_VRING_BASE:
            index, base = VRING_STATE.unpack(payload[:8])
            q = self.queues[index]
            q.last_avail_idx = base
            q.started = False
            _trace(f"{_ts()} vugpio: SET_VRING_BASE q={index} base={base}", flush=True)
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_GET_VRING_BASE:
            index, _reserved = VRING_STATE.unpack(payload[:8])
            q = self.queues[index]
            q.started = False
            _trace(f"{_ts()} vugpio: GET_VRING_BASE q={index} -> {q.last_avail_idx}", flush=True)
            self._send_reply(conn, request, VRING_STATE.pack(index, q.last_avail_idx))
            return

        if request == VHOST_USER_SET_VRING_KICK:
            self._handle_set_vring_fd(payload, fds, "kick")
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_SET_VRING_CALL:
            self._handle_set_vring_fd(payload, fds, "call")
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_SET_VRING_ERR:
            self._handle_set_vring_fd(payload, fds, "err")
            self._maybe_ack(conn, request, flags, True)
            return

        if request == VHOST_USER_SET_VRING_ENABLE:
            index, enable = VRING_STATE.unpack(payload[:8])
            self.queues[index].enabled = bool(enable)
            _trace(f"{_ts()} vugpio: SET_VRING_ENABLE q={index} enable={enable}", flush=True)
            if self.queues[index].enabled and not self.queues[index].configured():
                _trace(f"{_ts()} vugpio: WARNING q={index} enabled before full vring configuration", flush=True)
            self._debug_dump_queues("SET_VRING_ENABLE")
            runnable = self._queue_runnable(index)
            _trace(f"{_ts()} vugpio: q{index} runnable={runnable}", flush=True)
            if runnable:
                try:
                    if index == 0:
                        _trace(f"{_ts()} vugpio: prime request queue q=0 after enable", flush=True)
                        self._process_request_queue(index)
                    elif index == 1:
                        _trace(f"{_ts()} vugpio: prime event queue q=1 after enable", flush=True)
                        self._process_event_queue(index)
                except Exception as exc:
                    _trace(f"{_ts()} vugpio: queue prime after enable failed: {exc!r}", flush=True)
            self._maybe_ack(conn, request, flags, True)
            return

        _trace(f"{_ts()} vugpio: unhandled request={request}({REQUEST_NAMES.get(request,'UNKNOWN')})", flush=True)
        self._maybe_ack(conn, request, flags, True)

    def _handle_set_mem_table(self, payload: bytes, fds: List[int]) -> None:
        num_regions, _padding = MEM_HEADER.unpack(payload[:8])
        off = 8
        regions: List[MemoryRegion] = []
        for i in range(num_regions):
            guest_addr, size, user_addr, mmap_offset = MEM_REGION.unpack(payload[off:off + MEM_REGION.size])
            off += MEM_REGION.size
            fd = os.dup(fds[i])
            map_len = mmap_offset + size
            mm = mmap.mmap(fd, map_len, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ | mmap.PROT_WRITE)
            _trace(
                f"{_ts()} vugpio: mem region i={i} guest=0x{guest_addr:x} size=0x{size:x} "
                f"user=0x{user_addr:x} offset=0x{mmap_offset:x}",
                flush=True,
            )
            regions.append(MemoryRegion(guest_addr, size, user_addr, mmap_offset, fd, mm))
        self.mem.add_regions(regions)

    def _handle_set_vring_fd(self, payload: bytes, fds: List[int], which: str) -> None:
        (u64_val,) = U64.unpack(payload[:8])
        index = u64_val & 0xFF
        nofd = bool(u64_val & (1 << 8))
        q = self.queues[index]
        attr = f"{which}_fd"
        old = getattr(q, attr)
        if old is not None and which == "kick":
            try:
                self.sel.unregister(old)
            except Exception:
                pass
        if old is not None:
            try:
                os.close(old)
            except OSError:
                pass
            setattr(q, attr, None)
        if nofd:
            _trace(f"{_ts()} vugpio: SET_VRING_{which.upper()} q={index} NOFD", flush=True)
        else:
            if not fds:
                raise RuntimeError(f"SET_VRING_{which.upper()} missing fd (payload=0x{u64_val:x})")
            new_fd = os.dup(fds[0])
            setattr(q, attr, new_fd)
            if which == "kick":
                os.set_blocking(new_fd, False)
                self.sel.register(new_fd, selectors.EVENT_READ, data=index)
        _trace(f"{_ts()} vugpio: SET_VRING_{which.upper()} q={index} fd={getattr(q, attr)}", flush=True)
        _trace(f"{_ts()} vugpio: q{index} runnable={self._queue_runnable(index)}", flush=True)

    # -- data plane (minimal, request queue only) ---------------------------

    def poll_kicks_once(self, timeout: float = 0.0) -> None:
        try:
            events = self.sel.select(timeout)
        except Exception:
            return
        for key, _mask in events:
            fd = key.fd
            qindex = key.data
            try:
                os.read(fd, 8)
            except OSError:
                pass
            q = self.queues[qindex]
            q.started = True
            _trace(f"{_ts()} vugpio: kick q={qindex}", flush=True)
            if qindex == 0:
                self._process_request_queue(qindex)
            elif qindex == 1:
                self._process_event_queue(qindex)

    def _process_request_queue(self, qindex: int) -> None:
        q = self.queues[qindex]
        if not (q.enabled and q.configured()):
            return
        accessor = QueueAccessor(self.mem, q)
        avail_idx = accessor.avail_idx()
        _trace(f"{_ts()} vugpio: process_request_queue q={qindex} avail_idx={avail_idx} last_avail_idx={q.last_avail_idx}", flush=True)
        while q.last_avail_idx != avail_idx:
            slot = q.last_avail_idx % q.size
            head = accessor.avail_ring_entry(slot)
            chain = accessor.collect_chain(head)
            self._dump_chain(qindex, chain)
            q.last_avail_idx = (q.last_avail_idx + 1) & 0xFFFF
            try:
                self._handle_gpio_chain(q, accessor, chain)
            except Exception as exc:
                _trace(f"{_ts()} vugpio: process_request_queue failed: {exc!r}", flush=True)
                try:
                    self._complete_chain(q, accessor, chain, bytes([VIRTIO_GPIO_STATUS_ERR, 0]))
                except Exception as exc2:
                    _trace(f"{_ts()} vugpio: completing errored chain failed: {exc2!r}", flush=True)
                break


    def _process_event_queue(self, qindex: int) -> None:
        q = self.queues[qindex]
        if not (q.enabled and q.configured()):
            return
        accessor = QueueAccessor(self.mem, q)
        avail_idx = accessor.avail_idx()
        _trace(f"{_ts()} vugpio: process_event_queue q={qindex} avail_idx={avail_idx} last_avail_idx={q.last_avail_idx}", flush=True)
        while q.last_avail_idx != avail_idx:
            slot = q.last_avail_idx % q.size
            head = accessor.avail_ring_entry(slot)
            chain = accessor.collect_chain(head)
            self._dump_chain(qindex, chain)
            q.last_avail_idx = (q.last_avail_idx + 1) & 0xFFFF
            gpio = 0
            try:
                if chain.readable:
                    req_desc = chain.readable[0]
                    req = self.mem.read_guest(req_desc.addr, req_desc.length)
                    if len(req) >= VIRTIO_GPIO_IRQ_REQ.size:
                        (gpio,) = VIRTIO_GPIO_IRQ_REQ.unpack_from(req, 0)
            except Exception as exc:
                _trace(f"{_ts()} vugpio: failed to parse eventq request: {exc!r}", flush=True)
            if self.model.get_irq_type(gpio) == VIRTIO_GPIO_IRQ_TYPE_NONE:
                _trace(f"{_ts()} vugpio: event buffer for gpio={gpio} returned INVALID (irq disabled)", flush=True)
                self._complete_event_buffer(ArmedEventBuffer(gpio=gpio, head=head, writable=list(chain.writable)), VIRTIO_GPIO_IRQ_STATUS_INVALID)
                continue
            self.armed_event_buffers.append(ArmedEventBuffer(gpio=gpio, head=head, writable=list(chain.writable)))
            _trace(f"{_ts()} vugpio: armed event buffer gpio={gpio} head={head} writable={len(chain.writable)} total_armed={len(self.armed_event_buffers)}", flush=True)


    def _complete_event_buffer(self, ev: ArmedEventBuffer, status: int) -> None:
        q = self.queues[1]
        accessor = QueueAccessor(self.mem, q)
        response = bytes([status])
        remaining = response
        written = 0
        _trace(f"{_ts()} vugpio: complete_event_buffer gpio={ev.gpio} head={ev.head} status={status} armed_left={len(self.armed_event_buffers)}", flush=True)
        for d in ev.writable:
            chunk = remaining[: d.length]
            if chunk:
                self.mem.write_guest(d.addr, chunk)
            if len(chunk) < d.length:
                self.mem.write_guest(d.addr + len(chunk), b"\x00" * (d.length - len(chunk)))
            written += len(chunk)
            remaining = remaining[d.length:]
            if not remaining:
                break
        accessor.add_used(ev.head, written)
        self._signal_used(q)


    def _return_irq_buffer_for_gpio(self, gpio: int, status: int) -> bool:
        for idx, ev in enumerate(self.armed_event_buffers):
            if ev.gpio == gpio:
                self.armed_event_buffers.pop(idx)
                self._complete_event_buffer(ev, status)
                return True
        return False


    def _irq_should_fire(self, gpio: int, old_value: int, new_value: int) -> bool:
        irq_type = self.model.get_irq_type(gpio)
        if irq_type == VIRTIO_GPIO_IRQ_TYPE_NONE:
            return False
        if irq_type == VIRTIO_GPIO_IRQ_TYPE_EDGE_RISING:
            return old_value == 0 and new_value == 1
        if irq_type == VIRTIO_GPIO_IRQ_TYPE_EDGE_FALLING:
            return old_value == 1 and new_value == 0
        if irq_type == VIRTIO_GPIO_IRQ_TYPE_EDGE_BOTH:
            return old_value != new_value
        if irq_type == VIRTIO_GPIO_IRQ_TYPE_LEVEL_HIGH:
            return new_value == 1
        if irq_type == VIRTIO_GPIO_IRQ_TYPE_LEVEL_LOW:
            return new_value == 0
        return False


    def _emit_irq_event_if_armed(self, gpio: int, old_value: int, new_value: int) -> None:
        if not self.armed_event_buffers:
            _trace(f"{_ts()} vugpio: no armed event buffers for gpio={gpio}", flush=True)
            return
        q = self.queues[1]
        if not q.enabled or not q.configured():
            _trace(f"{_ts()} vugpio: event queue not runnable for gpio={gpio}", flush=True)
            return
        if not self._irq_should_fire(gpio, old_value, new_value):
            _trace(f"{_ts()} vugpio: irq not triggered gpio={gpio} old={old_value} new={new_value} type={self.model.get_irq_type(gpio)}", flush=True)
            return
        for idx, ev in enumerate(self.armed_event_buffers):
            if ev.gpio == gpio:
                self.armed_event_buffers.pop(idx)
                _trace(f"{_ts()} vugpio: emit_irq_event gpio={gpio} old={old_value} new={new_value} head={ev.head} armed_left={len(self.armed_event_buffers)}", flush=True)
                self._complete_event_buffer(ev, VIRTIO_GPIO_IRQ_STATUS_VALID)
                return
        _trace(f"{_ts()} vugpio: no matching armed event buffer for gpio={gpio}", flush=True)

    def _dump_chain(self, qindex: int, chain: Chain) -> None:
        _trace(
            f"{_ts()} vugpio: chain dump q={qindex} head={chain.head} "
            f"n_desc={len(chain.descriptors)} n_readable={len(chain.readable)} "
            f"n_writable={len(chain.writable)}",
            flush=True,
        )
        readable_ids = {id(d) for d in chain.readable}
        writable_ids = {id(d) for d in chain.writable}
        for d in chain.descriptors:
            role = []
            if id(d) in readable_ids:
                role.append("R")
            if id(d) in writable_ids:
                role.append("W")
            role_s = "".join(role) or "-"
            _trace(
                f"{_ts()} vugpio:   desc idx={d.index} role={role_s} addr=0x{d.addr:x} len={d.length} "
                f"flags=0x{d.flags:x} next={d.next}",
                flush=True,
            )

    def _handle_gpio_chain(self, q: VirtQueue, accessor: QueueAccessor, chain: Chain) -> None:
        if len(chain.readable) < 1:
            raise RuntimeError("expected at least one readable descriptor")
        req_desc = chain.readable[0]
        req = self.mem.read_guest(req_desc.addr, req_desc.length)
        _trace(
            f"{_ts()} vugpio: req raw len={len(req)} req_addr=0x{req_desc.addr:x} "
            f"bytes={req[:min(len(req),32)].hex()}",
            flush=True,
        )
        if len(req) < VIRTIO_GPIO_REQ.size:
            raise RuntimeError("short gpio request")
        rtype, gpio, value = VIRTIO_GPIO_REQ.unpack_from(req, 0)
        _trace(
            f"{_ts()} vugpio: gpio request parsed type=0x{rtype:x} gpio={gpio} value={value} "
            f"n_readable={len(chain.readable)} n_writable={len(chain.writable)}",
            flush=True,
        )

        status = VIRTIO_GPIO_STATUS_OK
        payload = b""

        if gpio >= self.model.ngpio and rtype != VIRTIO_GPIO_MSG_GET_LINE_NAMES:
            status = VIRTIO_GPIO_STATUS_ERR
        else:
            try:
                if rtype == VIRTIO_GPIO_MSG_GET_LINE_NAMES:
                    payload = self.model.names_blob()
                elif rtype == VIRTIO_GPIO_MSG_GET_DIRECTION:
                    direction = self.model.get_direction(gpio)
                    _trace(
                        f"{_ts()} vugpio: GET_DIRECTION gpio={gpio} -> {direction} ({gpio_direction_name(direction)})",
                        flush=True,
                    )
                    payload = bytes([direction])
                elif rtype == VIRTIO_GPIO_MSG_SET_DIRECTION:
                    _trace(
                        f"{_ts()} vugpio: SET_DIRECTION gpio={gpio} value={value} ({gpio_direction_name(value)})",
                        flush=True,
                    )
                    self.model.set_direction(gpio, value)
                    payload = b"\x00"
                elif rtype == VIRTIO_GPIO_MSG_GET_VALUE:
                    payload = bytes([self.model.get_value(gpio)])
                elif rtype == VIRTIO_GPIO_MSG_SET_VALUE:
                    self.model.set_value_from_guest(gpio, value)
                    if self.gui_server is not None:
                        self.gui_server.broadcast_gpio(gpio, 1 if value else 0)
                    payload = b"\x00"
                elif rtype == VIRTIO_GPIO_MSG_IRQ_TYPE:
                    self.model.set_irq_type(gpio, value)
                    if value == VIRTIO_GPIO_IRQ_TYPE_NONE:
                        returned = self._return_irq_buffer_for_gpio(gpio, VIRTIO_GPIO_IRQ_STATUS_INVALID)
                        _trace(f"{_ts()} vugpio: IRQ_TYPE none gpio={gpio} returned_buffer={returned}", flush=True)
                    payload = b"\x00"
                else:
                    status = VIRTIO_GPIO_STATUS_ERR
            except Exception:
                status = VIRTIO_GPIO_STATUS_ERR

        resp = bytes([status]) + payload
        if not chain.writable:
            _trace(f"{_ts()} vugpio: WARNING no writable descriptors in request chain", flush=True)
        self._complete_chain(q, accessor, chain, resp)

    def _complete_chain(self, q: VirtQueue, accessor: QueueAccessor, chain: Chain, response: bytes) -> None:
        remaining = response
        written = 0
        _trace(
            f"{_ts()} vugpio: complete_chain head={chain.head} resp_len={len(response)} "
            f"resp_hex={response[:32].hex()} n_writable={len(chain.writable)}",
            flush=True,
        )
        for d in chain.writable:
            chunk = remaining[: d.length]
            _trace(
                f"{_ts()} vugpio:   write desc addr=0x{d.addr:x} dlen={d.length} chunk_len={len(chunk)} "
                f"chunk_hex={chunk.hex()}",
                flush=True,
            )
            if chunk:
                self.mem.write_guest(d.addr, chunk)
            if len(chunk) < d.length:
                self.mem.write_guest(d.addr + len(chunk), b"\x00" * (d.length - len(chunk)))
            written += len(chunk)
            remaining = remaining[d.length:]
            if not remaining:
                break
        accessor.add_used(chain.head, written)
        self._signal_used(q)

    def _signal_used(self, q: VirtQueue) -> None:
        if q.call_fd is None:
            _trace(f"{_ts()} vugpio: signal_used skipped (no call_fd)", flush=True)
            return
        try:
            os.write(q.call_fd, struct.pack("<Q", 1))
            _trace(f"{_ts()} vugpio: signal_used call_fd={q.call_fd}", flush=True)
        except OSError as exc:
            _trace(f"{_ts()} vugpio: signal_used failed: {exc!r}", flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a vhost-user virtio-gpio backend compatible with QEMU."
    )
    parser.add_argument(
        "--socket-path",
        default="/tmp/gpio.sock",
        help="UNIX socket path used by QEMU for the vhost-user backend (default: %(default)s)",
    )
    parser.add_argument(
        "--control-socket",
        help="optional UNIX socket used by an external GUI/controller process",
    )
    parser.add_argument(
        "--log-level",
        choices=("debug", "info", "warning", "error"),
        default="info",
        help="logging verbosity for standard logging output (default: %(default)s)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable detailed protocol trace output (implies --log-level debug unless overridden)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="compatibility shortcut for --log-level warning and disabled protocol trace",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()

    global TRACE_ENABLED
    TRACE_ENABLED = args.verbose and not args.quiet

    if args.quiet:
        log_level = logging.WARNING
    elif args.verbose and args.log_level == "info":
        log_level = logging.DEBUG
    else:
        log_level = getattr(logging, args.log_level.upper())

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    LOG.info("starting vugpio_rvmm_%s", __version__)

    def output_cb(gpio: int, value: int) -> None:
        _trace(f"{_ts()} vugpio: output gpio={gpio} value={value}", flush=True)

    model = build_model_from_config(board_line_configs_from_module(), output_callback=output_cb)
    backend = VhostUserGpioBackend(args.socket_path, model, verbose=args.verbose)
    backend.start()
    if args.control_socket:
        backend.enable_gui_control(args.control_socket)

    try:
        while True:
            backend.poll_kicks_once(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()


if __name__ == "__main__":
    main()
