#!/usr/bin/env python3
"""Single source of truth for the demo board layout.

Backend code should use only:
- gpio
- name
- initial_direction
- initial_value

GUI code may additionally use:
- role

The code is developed by Wojciech M. Zabolotny (wzab01@gmail.com) with significant help
from ChatGPT (2026.04.03)

Published under Creative Commons CC0 License

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class BoardLineSpec:
    gpio: int
    name: str
    role: str  # "switch", "button", "led"
    initial_direction: str  # "in", "out", "none"
    initial_value: int = 0


BOARD_LINES: List[BoardLineSpec] = []

for i in range(0, 12):
    BOARD_LINES.append(BoardLineSpec(i, f"sw{i}", "switch", "in", 0))

for i in range(12, 24):
    BOARD_LINES.append(BoardLineSpec(i, f"btn{i}", "button", "in", 1))

for i in range(24, 32):
    BOARD_LINES.append(BoardLineSpec(i, f"led{i}", "led", "out", 0))
