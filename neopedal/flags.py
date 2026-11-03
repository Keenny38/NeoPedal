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
Country flags (flag-icons, MIT): one sheet of 4:3 flags (images/flags.png, cells in code order of
images/flags.json, made by tools/build_flags.py)

Codes as games & RaceControl give them: ISO 3166 alpha-2 ("FR"), alpha-3 ("FRA") or sport codes ("GER").
Overlays draw cut out flags (flag_pixmap, GUI thread); QML pages show the sheet clipped (flag_clip).
"""

from __future__ import annotations

import functools
import json
import logging
import os

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap

from .userfile import APP_ROOT

SHEET_FILE = os.path.join(APP_ROOT, "images", "flags.png")
INDEX_FILE = os.path.join(APP_ROOT, "images", "flags.json")
ASPECT = 4 / 3  # flag width / height
MAX_PIXMAPS = 256  # cut out flags kept (code & size), cache emptied beyond
# ISO 3166 alpha-3 & alpha-2 pairs (Qt reads alpha-2 only)
ALPHA3 = """
AFG AF ALA AX ALB AL DZA DZ ASM AS AND AD AGO AO AIA AI ATA AQ ATG AG ARG AR ARM AM ABW AW AUS AU AUT AT AZE AZ
BHS BS BHR BH BGD BD BRB BB BLR BY BEL BE BLZ BZ BEN BJ BMU BM BTN BT BOL BO BES BQ BIH BA BWA BW BVT BV BRA BR
IOT IO BRN BN BGR BG BFA BF BDI BI CPV CV KHM KH CMR CM CAN CA CYM KY CAF CF TCD TD CHL CL CHN CN CXR CX CCK CC
COL CO COM KM COG CG COD CD COK CK CRI CR CIV CI HRV HR CUB CU CUW CW CYP CY CZE CZ DNK DK DJI DJ DMA DM DOM DO
ECU EC EGY EG SLV SV GNQ GQ ERI ER EST EE SWZ SZ ETH ET FLK FK FRO FO FJI FJ FIN FI FRA FR GUF GF PYF PF ATF TF
GAB GA GMB GM GEO GE DEU DE GHA GH GIB GI GRC GR GRL GL GRD GD GLP GP GUM GU GTM GT GGY GG GIN GN GNB GW GUY GY
HTI HT HMD HM VAT VA HND HN HKG HK HUN HU ISL IS IND IN IDN ID IRN IR IRQ IQ IRL IE IMN IM ISR IL ITA IT JAM JM
JPN JP JEY JE JOR JO KAZ KZ KEN KE KIR KI PRK KP KOR KR KWT KW KGZ KG LAO LA LVA LV LBN LB LSO LS LBR LR LBY LY
LIE LI LTU LT LUX LU MAC MO MDG MG MWI MW MYS MY MDV MV MLI ML MLT MT MHL MH MTQ MQ MRT MR MUS MU MYT YT MEX MX
FSM FM MDA MD MCO MC MNG MN MNE ME MSR MS MAR MA MOZ MZ MMR MM NAM NA NRU NR NPL NP NLD NL NCL NC NZL NZ NIC NI
NER NE NGA NG NIU NU NFK NF MKD MK MNP MP NOR NO OMN OM PAK PK PLW PW PSE PS PAN PA PNG PG PRY PY PER PE PHL PH
PCN PN POL PL PRT PT PRI PR QAT QA REU RE ROU RO RUS RU RWA RW BLM BL SHN SH KNA KN LCA LC MAF MF SPM PM VCT VC
WSM WS SMR SM STP ST SAU SA SEN SN SRB RS SYC SC SLE SL SGP SG SXM SX SVK SK SVN SI SLB SB SOM SO ZAF ZA SGS GS
SSD SS ESP ES LKA LK SDN SD SUR SR SJM SJ SWE SE CHE CH SYR SY TWN TW TJK TJ TZA TZ THA TH TLS TL TGO TG TKL TK
TON TO TTO TT TUN TN TUR TR TKM TM TCA TC TUV TV UGA UG UKR UA ARE AE GBR GB USA US UMI UM URY UY UZB UZ VUT VU
VEN VE VNM VN VGB VG VIR VI WLF WF ESH EH YEM YE ZMB ZM ZWE ZW XKX XK
"""
# Sport codes (IOC, FIA entry lists) unlike ISO alpha-3 -> alpha-2
SPORT_CODES = {
    "GER": "de", "NED": "nl", "SUI": "ch", "POR": "pt", "DEN": "dk", "RSA": "za", "UAE": "ae", "KSA": "sa",
    "GRE": "gr", "CRO": "hr", "SLO": "si", "BUL": "bg", "LAT": "lv", "MAS": "my", "INA": "id", "PHI": "ph",
    "TPE": "tw", "CHI": "cl", "URU": "uy", "PAR": "py", "IRI": "ir", "ALG": "dz", "ANG": "ao", "MOZ": "mz",
    "ZIM": "zw", "MON": "mc", "HKG": "hk", "MAC": "mo", "KUW": "kw", "OMA": "om", "QAT": "qa", "BAH": "bh",
    "IRL": "ie", "IRE": "ie", "ENG": "gb-eng", "SCO": "gb-sct", "WAL": "gb-wls", "NIR": "gb-nir", "UK": "gb",
}

logger = logging.getLogger(__name__)


@functools.cache
def flag_index() -> dict[str, int]:
    """Cell of each code of flag sheet (lower case: "fr", "gb-sct"), empty if sheet index missing"""
    try:
        with open(INDEX_FILE, encoding="utf-8") as file:
            data = json.load(file)
        cell, columns, codes = data["cell"], int(data["columns"]), data["codes"]
        _layout[:] = [int(cell[0]), int(cell[1]), columns]
        return {str(code): index for index, code in enumerate(codes)}
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        logger.warning("FLAGS: index not read: %s", INDEX_FILE)
        return {}


_layout: list[int] = [64, 48, 16]  # cell width, cell height, columns (from index)


@functools.lru_cache(maxsize=512)
def flag_code(value: str) -> str:
    """Flag code of a country code as given (alpha-2, alpha-3, sport code; any case), "" if no flag"""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return ""
    index = flag_index()
    code = text.lower()
    if len(code) == 2 or "-" in code:
        return code if code in index else ""
    code = SPORT_CODES.get(text.upper()) or alpha3_codes().get(text.upper(), "")
    return code if code in index else ""


@functools.cache
def alpha3_codes() -> dict[str, str]:
    """ISO alpha-3 -> flag code"""
    words = ALPHA3.split()
    return {words[index]: words[index + 1].lower() for index in range(0, len(words), 2)}


def flag_rect(code: str) -> QRect | None:
    """Cell of flag in sheet (code as given), None if no flag"""
    position = flag_index().get(flag_code(code))
    if position is None:
        return None
    width, height, columns = _layout
    return QRect(position % columns * width, position // columns * height, width, height)


def flag_clip(code: str) -> list[int]:
    """[x, y, width, height] of flag in sheet for QML Image sourceClipRect, [] if no flag"""
    rect = flag_rect(code)
    return [] if rect is None else [rect.x(), rect.y(), rect.width(), rect.height()]


def flag_view(code: str) -> dict:
    """Flag of country code for QML (TpFlag): {"url": sheet file, "clip": [x, y, width, height]}, {} if no flag"""
    clip = flag_clip(code)
    return {"url": sheet_url(), "clip": clip} if clip else {}


def sheet_url() -> str:
    """Flag sheet file URL (QML Image source)"""
    from PySide6.QtCore import QUrl

    return QUrl.fromLocalFile(SHEET_FILE).toString()


_pixmaps: dict[tuple[str, int, float], QPixmap] = {}


def flag_pixmap(code: str, height: float, ratio: float = 2.0) -> QPixmap:
    """Flag of height (logical pixels, width 4:3), sharp at device pixel ratio; null if no flag (GUI thread)

    Only the flag's cell is read from the sheet file (once per code & size).
    """
    rect = flag_rect(code)
    if rect is None or height <= 0:
        return QPixmap()
    key = (flag_code(code), round(height), ratio)
    pixmap = _pixmaps.get(key)
    if pixmap is None:
        if len(_pixmaps) >= MAX_PIXMAPS:
            _pixmaps.clear()
        reader = QImageReader(SHEET_FILE)
        reader.setClipRect(rect)
        image = reader.read()
        if image.isNull():
            logger.warning("FLAGS: sheet not read: %s", reader.errorString())
            pixmap = QPixmap()
        else:
            size = QSize(max(round(height * ASPECT * ratio), 1), max(round(height * ratio), 1))
            image = image.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            pixmap = QPixmap.fromImage(image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
            pixmap.setDevicePixelRatio(ratio)
        _pixmaps[key] = pixmap
    return pixmap
