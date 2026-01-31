#  Copyright 2019, 2023, 2025 Andreas Krüger, DJ3EI
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

# This is an ADIF parser in Python.

# It knows nothing about ADIF data types or enumerations,
# everything is a string, so it is fairly simple.

# But it does correcly handle things like:
# <notes:66>In this QSO, we discussed ADIF and in particular the <eor> marker.
# So, in that sense, this parser is somewhat sophisticated.

# Main result of parsing: List of QSOs.
# Each QSO is one Python dict.
# Keys in that dict are ADIF field names in upper case,
# value for a key is whatever was found in the ADIF, as a string.
# Order of QSOs in the list is same as in ADIF file.

import math
import re
from collections.abc import MutableMapping
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

PROGRAMM_VERSION = "0.6.0"


class AdifError(Exception):
    """Base error."""

    pass


class AdifHeaderWithoutEOHError(AdifError):
    """Error for header found, but not terminated with <EOH>"""

    pass


class AdifDuplicateFieldError(AdifError):
    """Error for duplicate fileds in one QSO record or in the header."""

    pass


class _SaneStringMapping(MutableMapping[str, str]):
    def __init__(self, raw: dict[str, str]):
        self._d: dict[str, str] = {}
        for key in raw.keys():
            value = raw[key]
            if value is None or len(value) == 0:
                pass
            else:
                self._d[key.upper()] = str(value)

    def __getitem__(self, key: str) -> str:
        return self._d[key.upper()]

    def __setitem__(self, key: str, value: str) -> None:
        if value is None or value == "":
            ku = key.upper()
            if ku in self._d:
                del self._d[ku]
        else:
            self._d[key.upper()] = str(value)

    def __delitem__(self, key: str) -> None:
        del self._d[key.upper()]

    def __iter__(self) -> Iterator[str]:
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)


class QSO(_SaneStringMapping):

    def __str__(self) -> str:
        return qso_to_adif(self)


# Some type definition; however, it may change.
class Headers(_SaneStringMapping):
    def __str__(self) -> str:
        return headers_to_adif(self)


def qso_from_dict(d: dict[str, str]) -> QSO:
    """Official API to convert a Python dict to a QSO.

    Intended to be stable long-term.
    """
    return QSO(d)


def headers_from_dict(d: dict[str, str]) -> Headers:
    """Official API to convert a Python dict to ADIF file headers.

    Has a slim chance to remain stable long-term.
    """
    return Headers(d)


def read_from_string(adif_string: str) -> tuple[list[QSO], Headers]:
    """Read an ADIF string. Return QSO list and any headers found."""
    # The ADIF file header keys and values, if any.
    adif_headers: dict[str, str] = {}

    header_field_re = re.compile(r"<((eoh)|(\w+)\:(\d+)(\:[^>]+)?)>", re.IGNORECASE)
    field_re = re.compile(r"<((eor)|(\w+)\:(\d+)(\:[^>]+)?)>", re.IGNORECASE)

    qsos: list[QSO] = []
    cursor = 0
    if adif_string[0] != "<":
        # Input has ADIF header. Read all header fields.
        eoh_found = False
        while not eoh_found:
            header_field_mo = header_field_re.search(adif_string, cursor)
            if header_field_mo:
                if header_field_mo.group(2):
                    eoh_found = True
                    cursor = header_field_mo.end(0)
                else:
                    field = header_field_mo.group(3).upper()
                    value_start = header_field_mo.end(0)
                    value_end = value_start + int(header_field_mo.group(4))
                    value = adif_string[value_start:value_end]
                    if field in adif_headers:
                        raise AdifDuplicateFieldError(
                            f'Duplication in ADI header, {field} previously "{adif_headers[field]}", now "{value}".'
                        )
                    adif_headers[field] = value
                    cursor = value_end
            else:
                raise AdifHeaderWithoutEOHError(
                    "<EOF> marker missing after ADIF header."
                )

    one_qso: dict[str, str] = {}
    field_mo = field_re.search(adif_string, cursor)
    while field_mo:
        if field_mo.group(2):
            # <eor> found:
            qsos.append(qso_from_dict(one_qso))
            one_qso = {}
            cursor = field_mo.end(0)
        else:
            # Field found:
            field = field_mo.group(3).upper()
            value_start = field_mo.end(0)
            value_end = value_start + int(field_mo.group(4))
            value = adif_string[value_start:value_end]
            if field in one_qso:
                raise AdifDuplicateFieldError(
                    f'Duplication in qso {one_qso}, {field} previously "{one_qso[field]}", now "{value}".'
                )
            one_qso[field] = value
            cursor = value_end
        field_mo = field_re.search(adif_string, cursor)

    return (qsos, headers_from_dict(adif_headers))


def read_from_file(filename: str, encoding: str = "UTF-8") -> tuple[list[QSO], Headers]:
    """Read ADIF from a file."""
    with open(filename, encoding=encoding) as adif_file:
        adif_string = adif_file.read()
        return read_from_string(adif_string)


_ONE_DAY = timedelta(days=1)


def time_on(one_qso: QSO) -> datetime:
    """Convert the on-time of a QSO to Python datetime."""
    date = one_qso["QSO_DATE"]
    y = int(date[0:4])
    mo = int(date[4:6])
    d = int(date[6:8])
    time = one_qso["TIME_ON"]
    h = int(time[0:2])
    mi = int(time[2:4])
    s = int(time[4:6]) if len(time) == 6 else 0
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def time_off(one_qso: QSO) -> datetime:
    """Convert the off-time of a QSO to Python datetime."""
    if "QSO_DATE_OFF" in one_qso:
        date = one_qso["QSO_DATE_OFF"]
        y = int(date[0:4])
        mo = int(date[4:6])
        d = int(date[6:8])
        time = one_qso["TIME_OFF"]
        h = int(time[0:2])
        mi = int(time[2:4])
        s = int(time[4:6]) if len(time) == 6 else 0
        return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    else:
        date = one_qso["QSO_DATE"]
        y = int(date[0:4])
        mo = int(date[4:6])
        d = int(date[6:8])
        time = one_qso["TIME_OFF"]
        h = int(time[0:2])
        mi = int(time[2:4])
        s = int(time[4:6]) if len(time) == 6 else 0
        time_off_maybe = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
        if time_on(one_qso) < time_off_maybe:
            return time_off_maybe
        else:
            return time_off_maybe + _ONE_DAY


def degrees_from_location(adif: str) -> float:
    """Convert an ADIF location string to degrees."""
    x = adif[0]
    deg_i = int(adif[1:4])
    min = float(adif[5:])
    deg = deg_i + min / 60
    return deg if x in ["N", "E", "n", "e"] else -deg


def location_from_degrees(degrees: float, lat: bool) -> str:
    """Convert degrees to an ADIF location string, either latitude or longitude.

    If the `lat` parameter is true, N / S are used,
    if false, E / W.
    """
    if lat:
        if degrees < 0.0:
            x = "S"
        else:
            x = "N"
    else:
        if degrees < 0.0:
            x = "W"
        else:
            x = "E"
    degrees_abs = abs(degrees)
    deg_num = int(math.floor(degrees_abs))
    min_num = (degrees_abs - deg_num) * 60
    return f"{x}{deg_num:03d} {min_num:06.3f}"


def headers_to_adif(headers: Headers) -> str:
    """Transform some headers to an ADIF string."""
    result = ""
    for key in sorted(headers.keys()):
        value = headers[key]
        if value is None:
            pass  # Can't really happen.
        else:
            value_s = str(value)
            if 0 == len(value_s) or key is None or 0 == len(key):
                pass  # Can't really happen.
            else:
                if 0 == len(result):
                    result = f" <{key}:{len(value_s)}>{value_s}"
                else:
                    result += f" <{key}:{len(value_s)}>{value_s}"
    result += " <EOH>\n"
    return result


_ESSENTIAL_KEYS = [
    "QSO_DATE",
    "TIME_ON",
    "CALL",
    "FREQ",
    "MODE",
]


def qso_to_adif(qso: QSO) -> str:
    """Transform a qso to an ADIF string."""
    result = ""
    for key in _ESSENTIAL_KEYS:
        if key in qso:
            value = qso[key]
            if value is None:
                pass  # Can't really happen.
            else:
                value_s = str(value)
                if 0 == len(value_s) or key is None or 0 == len(key):
                    pass  # Can't really happen.
                else:
                    if 0 == len(result):
                        result = f"<{key}:{len(value_s)}>{value_s.upper()}"
                    else:
                        result += f" <{key}:{len(value_s)}>{value_s.upper()}"

    for key in sorted(k for k in qso.keys() if k not in _ESSENTIAL_KEYS):
        value = qso[key]
        if value is None:
            pass  # Can't really happen.
        else:
            value_s = str(value)
            if 0 == len(value_s) or key is None or 0 == len(key):
                pass  # Can't really happen.
            else:
                if 0 == len(result):
                    result = f"<{key}:{len(value_s)}>{value_s}"
                else:
                    result += f" <{key}:{len(value_s)}>{value_s}"

    result += " <EOR>\n"

    return result


def write_to_file(
    filename: str,
    qsos: list[QSO],
    headers: Optional[Headers] = None,
    encoding: str = "UTF-8",
) -> None:
    with open(filename, encoding=encoding) as adif_file:
        adif_file.write("ADI file written by Python's adif_io\n")
        if headers is None:
            headers = Headers({})
        if "ADIF_VER" not in headers:
            adif_file.write(" <ADIF_VER:5>3.1.6")
        if "CREATED_TIMESTAMP" not in headers:
            dt = datetime.utcnow().strftime("%Y%m%d %H%M%S")
            adif_file.write(f" <CREATED_TIMESTAMP:{len(dt)}>{dt}")
        if "PROGRAMID" not in headers:
            adif_file.write(" <PROGRAMID:14>Python adif_io")
        if "PROGRAMMVERSION" not in headers:
            adif_file.write(
                f" <PROGRAMMVERSION:{len(PROGRAMM_VERSION)}>{PROGRAMM_VERSION}"
            )
        adif_file.write(headers_to_adif(headers))

        for qso in qsos:
            adif_file.write(qso_to_adif(qso))
