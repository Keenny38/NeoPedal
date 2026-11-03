#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Lap time reference: community LMU lap times by track & class (published Google Sheet)

The sheet lists, for each track & class, the class reference hotlap ("Class avgW"), a race pace
ladder from ~100% (Alien) to 107% (Offline) of it, and the fastest car with its lap time.
Downloaded as xlsx (exact cell values: lap times to the millisecond; the CSV export rounds them to hundredths,
used only when the xlsx one is unusable), kept as CSV in config folder (works offline), matched to driver stats:
LMU track name & vehicle class to sheet track & class.
"""

from __future__ import annotations

import csv
import http.client
import io
import logging
import math
import os
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # never resolves external entities
import zipfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTN03UvJDm99byA6vQPZHKOCYVvfxLu1zkJAzdaKyROykzEKY2-"
    "Xl1rl1q5znZEf36m88dxMKsY2eaO/pubhtml#gid=1766901750"
)
SHEET_SOURCE = "ohne_speed"  # sheet author, credited in viewer
SHEET_SOURCE_URL = "https://www.youtube.com/@ohne_speed"
CACHE_NAME = "lap_reference.csv"
FAILED_NAME = "lap_reference.failed"  # its time: last download that failed
SHEET_CLASSES = ("LMH", "LMP2wec", "LMP2elms", "LMP3", "LMGT3", "GTE")
MAX_SIZE = 2 * 1024 * 1024
MAX_XLSX_SIZE = 8 * 1024 * 1024  # xlsx of the sheet tab (~80 KB; the whole workbook ~2.4 MB)
MAX_XML_SIZE = 64 * 1024 * 1024  # unpacked part of the xlsx (zip bomb guard)
RETRY_DELAYS = (1.0, 3.0)  # seconds before each new attempt of a download cut by the network or the server
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XLSX_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
# Built-in number formats of xlsx cells (styles.xml lists only custom ones)
XLSX_FORMATS = {0: "General", 1: "0", 2: "0.00", 9: "0%", 10: "0.00%", 20: "h:mm", 21: "h:mm:ss", 45: "mm:ss",
                46: "[h]:mm:ss", 47: "mm:ss.0", 49: "@"}

# Level of each ladder step: ~100%, 101%, 102%, 103%, 104%, 105%, 106%, 107% (and slower), as the sheet
# header (merged cells): Good over 102 & 103%, Midpack over 104 & 105%. A step value is the slowest lap time
# of its step (step + 0.5%: 101% column is 101.5% of class reference).
LEVELS = ("Alien", "Competitive", "Good", "Midpack", "Tail-ender", "Offline")
LADDER_LEVEL = (0, 1, 2, 2, 3, 3, 4, 5)
LEVEL_COLORS = ("#C060FF", "#4C8DFF", "#3FB950", "#D4A72C", "#F0883E", "#8E8E8E")

# Columns of sheet rows: key, track, patch, class best, ladder x8, fastest car, its lap time, best/avg,
# average, class, cars
COL_TRACK, COL_PATCH, COL_BEST, COL_LADDER, COL_CAR, COL_CAR_TIME, COL_CLASS = 1, 2, 3, 4, 12, 13, 16

# Vehicle class (driver stats key, LMU class name) to sheet class
CLASS_ALIASES = {
    "hyper": "LMH", "hypercar": "LMH", "lmh": "LMH", "lmdh": "LMH",
    "lmp2_elms": "LMP2elms", "lmp2elms": "LMP2elms", "elms_lmp2": "LMP2elms",
    "lmp2": "LMP2wec", "lmp2_wec": "LMP2wec", "lmp2wec": "LMP2wec",
    "lmp3": "LMP3",
    "gt3": "LMGT3", "lmgt3": "LMGT3",
    "gte": "GTE", "lmgte": "GTE", "gte_pro": "GTE", "gte_am": "GTE",
}

# Sheet track: (circuit words, any one), (layout words, all required), (words excluded); first match wins
TRACK_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    ("Bahrain (endurance)", ("bahrain", "sakhir"), ("endurance",), ()),
    ("Bahrain (outer)", ("bahrain", "sakhir"), ("outer",), ()),
    ("Bahrain (paddock)", ("bahrain", "sakhir"), ("paddock",), ()),
    ("Bahrain (wec)", ("bahrain", "sakhir"), (), ()),
    ("Barcelona", ("barcelona", "catalunya"), (), ()),
    ("Circuit de la Sarthe (straight)", ("sarthe", "le mans"), ("mulsanne",), ()),
    ("Circuit de la Sarthe (straight)", ("sarthe", "le mans"), ("straight",), ()),
    ("Circuit de la Sarthe", ("sarthe", "le mans"), (), ()),
    ("COTA (national)", ("americas", "cota"), ("national",), ()),
    ("COTA", ("americas", "cota"), (), ()),
    ("Daytona", ("daytona",), (), ()),
    ("Fuji (classic)", ("fuji",), ("classic",), ()),
    ("Fuji (chicane)", ("fuji",), (), ()),
    ("Imola", ("imola", "enzo e dino ferrari"), (), ()),
    ("Interlagos", ("interlagos", "carlos pace"), (), ()),
    ("Laguna Seca", ("laguna seca",), (), ()),
    ("Long Beach", ("long beach",), (), ()),
    ("Monza (curvagrande)", ("monza",), ("curva",), ()),
    ("Monza", ("monza",), (), ()),
    ("Paul Ricard (1A v2 short)", ("ricard",), ("1a", "v2", "short"), ()),
    ("Paul Ricard (1A v2)", ("ricard",), ("1a", "v2"), ()),
    ("Paul Ricard (1A)", ("ricard",), ("1a",), ()),
    ("Paul Ricard (3A)", ("ricard",), ("3a",), ()),
    ("Paul Ricard", ("ricard",), (), ()),
    ("Portimao", ("portimao", "algarve"), (), ()),
    ("Qatar (short)", ("qatar", "lusail", "losail"), ("short",), ()),
    ("Qatar", ("qatar", "lusail", "losail"), (), ()),  # LMU: Losail International, Lusail Short
    ("Road Atlanta", ("road atlanta",), (), ()),
    ("Silverstone (National)", ("silverstone",), ("national",), ("international",)),
    ("Silverstone (International)", ("silverstone",), ("international",), ()),
    ("Silverstone (GP)", ("silverstone",), (), ()),
    ("Sebring (school)", ("sebring",), ("school",), ()),
    ("Sebring", ("sebring",), (), ()),
    ("Spa", ("spa",), (), ()),
)


@dataclass(frozen=True)
class LapReference:
    """Reference lap times of a track & class (seconds, 0 when unknown)"""

    track: str
    vehicle_class: str
    patch: str
    class_best: float  # class reference hotlap
    ladder: tuple[float, ...]  # ~100% to 107% race pace steps
    fastest_car: str
    fastest_time: float

    @property
    def reference(self) -> float:
        """Lap time 100% stands for: class reference hotlap, else from first ladder step"""
        return self.class_best or (self.ladder[0] / 1.005 if self.ladder and self.ladder[0] else 0.0)

    def percent(self, laptime: float) -> float:
        """Lap time in percent of reference (0 if unknown)"""
        reference = self.reference
        return laptime / reference * 100 if reference > 0 and laptime > 0 else 0.0

    def level(self, laptime: float) -> int:
        """Level index (LEVELS) of a lap time on the race pace ladder, -1 if unknown"""
        if laptime <= 0 or not self.ladder or not all(self.ladder):
            return -1
        # Compared as shown (milliseconds): 1:45.170 (game float 105.17047) within "≤ 1:45.170" of sheet 1:45.17
        laptime = round(laptime, 3)
        for step, limit in enumerate(self.ladder):
            if laptime <= limit:
                return LADDER_LEVEL[step]
        return LADDER_LEVEL[-1]

    def level_limit(self, level: int) -> float:
        """Slowest lap time of a level (its last ladder step), 0 if unknown or Offline (no limit)"""
        if not 0 <= level < LADDER_LEVEL[-1] or not self.ladder or not all(self.ladder):
            return 0.0
        return max(limit for limit, step_level in zip(self.ladder, LADDER_LEVEL) if step_level == level)

    def next_level(self, laptime: float) -> tuple[int, float]:
        """Next better level of a lap time & time to find (seconds, from the lap time to the millisecond as level
        compares it), (-1, 0) if top level or unknown"""
        level = self.level(laptime)
        if level <= 0:
            return -1, 0.0
        limit = self.level_limit(level - 1)
        return (level - 1, round(round(laptime, 3) - limit, 3)) if limit else (-1, 0.0)


@dataclass
class LapReferenceTable:
    """References by (sheet track, sheet class), sheet update date"""

    entries: dict[tuple[str, str], LapReference] = field(default_factory=dict)
    updated: str = ""
    precise: bool = False  # lap times to the millisecond (xlsx download), else hundredths (CSV export)
    # Sheet tracks & matched sheet track of each track name, computed once (entries set at parse)
    _tracks: set[str] | None = field(default=None, repr=False, compare=False)
    _matches: dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def tracks(self) -> set[str]:
        if self._tracks is None:
            self._tracks = {track for track, _ in self.entries}
        return self._tracks

    def sheet_track(self, track_name: str) -> str:
        """Sheet track of an LMU track name (cached), empty if none"""
        track = self._matches.get(track_name)
        if track is None:
            track = self._matches[track_name] = match_track(track_name, self.tracks)
        return track

    def find(self, track_name: str, vehicle_key: str, vehicle_class: str = "") -> LapReference | None:
        """Reference of an LMU track name & driver stats vehicle key (class - brand), None if no match

        Args:
            vehicle_class: game class name, when vehicle key has no class (vehicle name).
        """
        track = self.sheet_track(track_name)
        sheet_class = vehicle_class_of(vehicle_key) or (vehicle_class_of(vehicle_class) if vehicle_class else "")
        if not track or not sheet_class:
            return None
        return self.entries.get((track, sheet_class))


def parse_time(text: str) -> float:
    """Lap time "m:ss.xx" to seconds, 0 if not a lap time"""
    match = re.fullmatch(r"\s*(\d+):(\d{1,2}(?:\.\d+)?)\s*", text or "")
    if not match:
        return 0.0
    seconds = int(match.group(1)) * 60 + float(match.group(2))
    return seconds if seconds > 0 else 0.0


def parse_lap_references(text: str) -> LapReferenceTable:
    """References from sheet CSV text (rows that are not reference rows skipped, rows after a CSV error too)"""
    table = LapReferenceTable()
    try:
        _parse_rows(text, table)
    except csv.Error as error:  # NUL byte, unclosed quote at end of a cut off file: rows read so far kept
        logger.warning("LAP REFERENCE: sheet CSV error: %s", error)
    return table


def _parse_rows(text: str, table: LapReferenceTable) -> None:
    for row in csv.reader(io.StringIO(text)):
        if not table.updated:
            for cell in row:
                if cell.startswith("Last updated:"):
                    table.updated = cell.removeprefix("Last updated:").strip()
        if len(row) <= COL_CLASS or row[COL_CLASS] not in SHEET_CLASSES or not row[COL_TRACK]:
            continue
        # Step = slowest lap time of its level: millisecond below the exact value (a lap time to the millisecond is
        # at most the step exactly when at most this), shown times to the nearest millisecond
        ladder = tuple(math.floor(parse_time(cell) * 1000 + 1e-6) / 1000 for cell in row[COL_LADDER:COL_LADDER + 8])
        reference = LapReference(
            track=row[COL_TRACK].strip(),
            vehicle_class=row[COL_CLASS],
            patch=row[COL_PATCH].strip() if row[COL_PATCH].strip() != "N/A" else "",
            class_best=round(parse_time(row[COL_BEST]), 3),
            ladder=ladder,
            fastest_car=row[COL_CAR].strip(),
            fastest_time=round(parse_time(row[COL_CAR_TIME]), 3),
        )
        if reference.reference > 0:
            table.entries[(reference.track, reference.vehicle_class)] = reference
            table.precise = table.precise or bool(re.search(r"\.\d{3,}\s*$", row[COL_LADDER]))


def normalize(text: str) -> str:
    """Lower case, accents & punctuation removed, single spaces"""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def match_track(track_name: str, tracks: set[str] | None = None) -> str:
    """Sheet track of an LMU track name (layout words decide the layout), empty if none"""
    name = f" {normalize(track_name)} "
    for track, circuits, layout, excluded in TRACK_RULES:
        if tracks is not None and track not in tracks:
            continue
        if not any(f" {word} " in name or (" " in word and word in name) for word in circuits):
            continue
        if all(f" {word} " in name for word in layout) and not any(f" {word} " in name for word in excluded):
            return track
    return ""


def vehicle_class_of(vehicle_key: str) -> str:
    """Sheet class of a driver stats vehicle key ("LMP2_ELMS - Oreca", "Hyper", "GT3"), empty if unknown"""
    class_name = vehicle_key.split(" - ", 1)[0].strip().lower().replace(" ", "_").replace("-", "_")
    return CLASS_ALIASES.get(class_name, "")


def csv_url(url: str) -> str:
    """CSV export url of a published Google Sheet url (pubhtml, pub, with or without gid)"""
    return export_url(url, "csv")


def export_url(url: str, kind: str) -> str:
    """Export url ("csv" or "xlsx") of a published Google Sheet url (pubhtml, pub, with or without gid)"""
    parts = urllib.parse.urlsplit(url.strip())
    gid = ""
    for source in (parts.fragment, parts.query):
        found = re.search(r"gid=(\d+)", source)
        if found:
            gid = found.group(1)
            break
    path = re.sub(r"/pubhtml$|/pub$|/edit$|/htmlview$", "", parts.path.rstrip("/"))
    if "/d/e/" in path:
        path += "/pub"
        query = {"output": kind, "single": "true"} if gid else {"output": kind}
    else:
        path += "/export"
        query = {"format": kind}
    if gid:
        query["gid"] = gid
    return urllib.parse.urlunsplit(("https", parts.netloc or "docs.google.com", path, urllib.parse.urlencode(query), ""))


def fetch_sheet(url: str, timeout: float = 15) -> str:
    """Download sheet as CSV text: xlsx export (lap times to the millisecond), else CSV export (hundredths)
    (raise OSError or ValueError)"""
    target = export_url(url, "xlsx")
    if not target.startswith("https://docs.google.com/"):
        raise ValueError("not a Google Sheets url")
    try:  # network errors raised: the CSV export would fail the same way
        text = xlsx_text(download(target, MAX_XLSX_SIZE, timeout))
        if parse_lap_references(text).entries:
            return text
        reason = "no lap time reference"
    except (ValueError, LookupError, zipfile.BadZipFile, ET.ParseError) as error:
        reason = str(error) or type(error).__name__
    logger.info("LAP REFERENCE: xlsx export not used (%s), CSV export downloaded", reason)
    text = download(export_url(url, "csv"), MAX_SIZE, timeout).decode("utf-8-sig", "replace")
    if not parse_lap_references(text).entries:
        raise ValueError("no lap time reference found in sheet")
    return text


def download(target: str, limit: int, timeout: float) -> bytes:
    """Bytes of an url (at most limit), tried again after RETRY_DELAYS when cut by the network or the server
    (raise OSError, ValueError if larger than limit)"""
    from .. import version
    from ..const_app import APP_NAME

    request = urllib.request.Request(target, headers={"User-Agent": f"{APP_NAME}/{version.__version__}"})
    for delay in (*RETRY_DELAYS, None):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read(limit + 1)
            break
        except urllib.error.HTTPError as error:
            if delay is None or (error.code < 500 and error.code != 429):  # wrong address, not published: final
                raise
            reason = f"HTTP {error.code}"
        except http.client.HTTPException as error:  # cut off response (IncompleteRead), bad status line
            if delay is None:
                raise OSError(f"download failed: {type(error).__name__}") from error
            reason = type(error).__name__
        except OSError as error:  # timeout, connection reset; offline (name not resolved): final
            if delay is None or isinstance(getattr(error, "reason", None), socket.gaierror):
                raise
            reason = str(error) or type(error).__name__
        logger.info("LAP REFERENCE: download failed (%s), new attempt in %.0f s", reason, delay)
        time.sleep(delay)
    if len(data) > limit:
        raise ValueError("sheet too large")
    return data


def xlsx_text(data: bytes) -> str:
    """CSV text of the first sheet of an xlsx file: times to the microsecond (m:ss.ffffff), other numbers as shown
    (number format of the cell), text as is (raise ValueError, LookupError, BadZipFile, ParseError)"""
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        names = set(book.namelist())

        def part(name: str) -> ET.Element:
            if book.getinfo(name).file_size > MAX_XML_SIZE:
                raise ValueError("sheet too large")
            return ET.fromstring(book.read(name))

        strings = []
        if "xl/sharedStrings.xml" in names:
            strings = ["".join(text.text or "" for text in item.iter(f"{{{XLSX_NS['m']}}}t"))
                       for item in part("xl/sharedStrings.xml").iterfind("m:si", XLSX_NS)]
        formats = _cell_formats(part("xl/styles.xml")) if "xl/styles.xml" in names else []
        sheet = part(_first_sheet(part, names))
    rows: list[list[str]] = []
    for row in sheet.iterfind("m:sheetData/m:row", XLSX_NS):
        number = int(row.get("r") or len(rows) + 1)
        cells: dict[int, str] = {}
        column = -1
        for cell in row.iterfind("m:c", XLSX_NS):
            column = _column_index(cell.get("r", ""), column + 1)
            cells[column] = _cell_text(cell, strings, formats)
        rows.extend([] for _ in range(number - 1 - len(rows)))
        rows.append([cells.get(index, "") for index in range(max(cells, default=-1) + 1)])
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue()


def _first_sheet(part: Callable[[str], ET.Element], names: set[str]) -> str:
    """Path of first sheet of workbook (order of the tabs)"""
    first = part("xl/workbook.xml").find("m:sheets/m:sheet", XLSX_NS)
    if first is not None and "xl/_rels/workbook.xml.rels" in names:
        for relation in part("xl/_rels/workbook.xml.rels"):
            if relation.get("Id") == first.get(XLSX_REL_NS):
                target = relation.get("Target", "")
                return target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    return "xl/worksheets/sheet1.xml"


def _cell_formats(styles: ET.Element) -> list[str]:
    """Number format code of each cell style"""
    custom = {int(entry.get("numFmtId", "0")): entry.get("formatCode", "")
              for entry in styles.iterfind("m:numFmts/m:numFmt", XLSX_NS)}
    return [custom.get(index, XLSX_FORMATS.get(index, "General"))
            for index in (int(style.get("numFmtId", "0")) for style in styles.iterfind("m:cellXfs/m:xf", XLSX_NS))]


def _column_index(reference: str, default: int) -> int:
    """Column index (0: A) of a cell reference ("AB12"), default if none"""
    letters = re.match(r"[A-Z]+", reference)
    if letters is None:
        return default
    index = 0
    for letter in letters.group(0):
        index = index * 26 + ord(letter) - 64
    return index - 1


def _cell_text(cell: ET.Element, strings: list[str], formats: list[str]) -> str:
    """Text of an xlsx cell: shared or inline text, error, number in its format"""
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        return "".join(text.text or "" for text in cell.iter(f"{{{XLSX_NS['m']}}}t"))
    found = cell.find("m:v", XLSX_NS)
    value = found.text or "" if found is not None else ""
    if kind == "s":
        return strings[int(value)] if value.isdigit() and int(value) < len(strings) else ""
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    if kind != "n" or not value:
        return value  # formula text, error (#DIV/0!)
    try:
        number = float(value)
    except ValueError:
        return value
    style = cell.get("s", "0")
    return format_number(number, formats[int(style)] if style.isdigit() and int(style) < len(formats) else "General")


def format_number(number: float, code: str) -> str:
    """Number as an xlsx format shows it: times (durations) to the microsecond as m:ss.ffffff, percents, decimals
    with quoted text around ("0.0"+"": 1.4+), else general"""
    code = code.split(";")[0]  # positive numbers section
    plain = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', "", code).lower()
    if re.search(r"[hms]", plain) and not re.search(r"[dy]", plain) and plain != "general":
        total = round(number * 86400, 6)  # days to seconds, kept to the microsecond (rounded when read)
        minutes, seconds = divmod(abs(total), 60)
        return f"{'-' if total < 0 else ''}{int(minutes)}:{seconds:09.6f}"
    numeric = re.search(r"[0#?][0#?,]*(?:\.([0#?]*))?", plain)
    if numeric is None or plain == "general":
        return f"{number:.10g}"
    decimals = numeric.group(1) or ""
    if "%" in plain:
        number *= 100
    text = f"{number:.{len(decimals)}f}"
    required = decimals.count("0")
    if len(decimals) > required and "." in text:  # optional decimals (# ?): trailing zeros dropped
        text = text.rstrip("0")
        whole, _, fraction = text.partition(".")
        text = f"{whole}.{fraction.ljust(required, '0')}" if required or fraction else whole
    # Quoted text & percent sign around the number, as in the format ("+" of a patch number)
    before, _, after = code.partition(numeric.group(0)) if numeric.group(0) in code else ("", "", "")
    literal = re.compile(r'"([^"]*)"|\\(.)|(%)')

    def literals(part: str) -> str:
        return "".join("".join(match.groups(default="")) for match in literal.finditer(part))

    return f"{literals(before)}{text}{literals(after)}"


def load_cache(filepath: str) -> tuple[str, float]:
    """Cached sheet CSV text & its time (0 if none)"""
    path = os.path.join(filepath, CACHE_NAME)
    try:
        with open(path, encoding="utf-8") as file:
            return file.read(MAX_SIZE), os.path.getmtime(path)
    except (OSError, UnicodeDecodeError):  # damaged cache: downloaded again
        return "", 0.0


def failed_recently(filepath: str, seconds: float, now: float | None = None) -> bool:
    """A download failed less than `seconds` ago (marker file kept across restarts, removed once one worked)"""
    try:
        stamp = os.path.getmtime(os.path.join(filepath, FAILED_NAME))
    except OSError:
        return False
    return 0 <= (time.time() if now is None else now) - stamp < seconds


def mark_download(filepath: str, failed: bool) -> None:
    """Download failed (marker written: the next page opening waits) or worked (marker removed)"""
    from . import atomic_write

    path = os.path.join(filepath, FAILED_NAME)
    if failed:
        with suppress(OSError), atomic_write(path, raise_error=True) as file:
            file.write("failed")
    else:
        with suppress(OSError):
            os.remove(path)


def cache_time(filepath: str) -> float:
    """Time of cached sheet (0 if none), without reading it"""
    try:
        return os.path.getmtime(os.path.join(filepath, CACHE_NAME))
    except OSError:
        return 0.0


def save_cache(filepath: str, text: str) -> None:
    """Keep sheet CSV text for offline use"""
    from . import atomic_write

    with suppress(OSError), atomic_write(os.path.join(filepath, CACHE_NAME), raise_error=True) as file:
        file.write(text)  # cache only: a failed write (already logged) is fetched again next time
