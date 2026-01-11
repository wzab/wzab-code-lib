#!/bin/env python3
# This is a PUBLIC DOMAIN (CC0) code for finding the information 
# (e.g., the state for WAS) about the US callsigns.
import aiohttp
import aiosqlite
import asyncio
import json
import re
import time
import sys
from typing import Optional

CACHE_DB = "callsign_cache.db"
CACHE_TTL = 7 * 24 * 3600  # 7 dni

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia"
}


# ---------- DB ----------

async def init_db():
    async with aiosqlite.connect(CACHE_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS callsign_cache (
                callsign TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)
        await db.commit()


async def load_from_cache(callsign: str) -> Optional[dict]:
    async with aiosqlite.connect(CACHE_DB) as db:
        async with db.execute(
            "SELECT data, timestamp FROM callsign_cache WHERE callsign = ?",
            (callsign,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            data, ts = row
            if time.time() - ts > CACHE_TTL:
                return None

            return json.loads(data)


async def save_to_cache(callsign: str, data: dict):
    async with aiosqlite.connect(CACHE_DB) as db:
        await db.execute(
            "REPLACE INTO callsign_cache (callsign, data, timestamp) VALUES (?, ?, ?)",
            (callsign, json.dumps(data), int(time.time()))
        )
        await db.commit()


# ---------- PARSER ----------

def parse_callook_data(data: dict) -> Optional[dict]:
    if data.get("status") != "VALID":
        return None

    address_line2 = data.get("address", {}).get("line2", "")
    state_code = None

    m = re.search(r",\s*([A-Z]{2})\s+\d{5}", address_line2)
    if m:
        state_code = m.group(1)

    location = data.get("location", {})

    return {
        "callsign": data.get("current", {}).get("callsign"),
        "name": data.get("name"),
        "state_code": state_code,
        "state_name": STATE_NAMES.get(state_code),
        "latitude": float(location["latitude"]) if location.get("latitude") else None,
        "longitude": float(location["longitude"]) if location.get("longitude") else None,
        "gridsquare": location.get("gridsquare"),
        "license_class": data.get("current", {}).get("operClass"),
    }


# ---------- API ----------

async def fetch_from_callook(callsign: str) -> Optional[dict]:
    url = f"https://callook.info/{callsign}/json"
    headers = {
        "User-Agent": "ham-radio-lookup/1.0 (aiohttp)"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


async def lookup_callsign(callsign: str) -> Optional[dict]:
    callsign = callsign.strip().upper()

    if not re.match(r"^[A-Z0-9]{3,}$", callsign):
        raise ValueError("Invalid callsign format")

    # 1️⃣ cache
    cached = await load_from_cache(callsign)
    if cached:
        return parse_callook_data(cached)

    # 2️⃣ API
    data = await fetch_from_callook(callsign)
    if not data:
        return None

    # 3️⃣ save
    await save_to_cache(callsign, data)

    return parse_callook_data(data)


# ---------- DEMO ----------

async def main():
    await init_db()
    while True:
        sys.stdout.write("Callsign:\n")
        cs = sys.stdin.readline().strip()
    #for cs in ("K4MPM", "W6XYZ", "N0CALL"):
        info = await lookup_callsign(cs)
        print(cs, "→", info)


if __name__ == "__main__":
    asyncio.run(main())
