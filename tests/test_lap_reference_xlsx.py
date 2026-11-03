"""Community lap times downloaded as xlsx (exact cell values: lap times to the millisecond), download tried again
when cut, CSV export when the xlsx one is unusable"""

import io
import socket
import urllib.error
import urllib.request
import zipfile

import pytest

from neopedal.userfile import lap_reference
from neopedal.userfile.lap_reference import format_number, parse_lap_references, xlsx_text

REAL_FETCH_SHEET = lap_reference.fetch_sheet  # read at import, before conftest makes it offline

DAY = 86400.0
MAIN = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RELS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def sheet_xlsx() -> bytes:
    """xlsx of the community sheet layout: a header, Road Atlanta LMH (times in days, as Google Sheets exports)"""
    strings = ["Last updated: 2026.10.30. 08:48 CEST", "Track", "Road AtlantaLMH", "Road Atlanta",
               "Genesis GMR-001 (v1.43)", "LMH"]
    shared = "".join(f"<si><t>{text}</t></si>" for text in strings)
    ladder = "".join(f'<c r="{column}9" s="2"><v>{(68.725 * (1.005 + 0.01 * step)) / DAY!r}</v></c>'
                     for step, column in enumerate("EFGHIJKL"))
    sheet = (f'<worksheet {MAIN}><sheetData>'
             '<row r="2"><c r="B2" t="s"><v>0</v></c></row>'
             '<row r="8"><c r="B8" t="s"><v>1</v></c></row>'
             '<row r="9"><c r="A9" t="s"><v>2</v></c><c r="B9" t="s"><v>3</v></c><c r="C9" s="1"><v>1.4</v></c>'
             f'<c r="D9" s="2"><v>{68.725 / DAY!r}</v></c>{ladder}<c r="M9" t="s"><v>4</v></c>'
             f'<c r="N9" s="2"><v>{68.577 / DAY!r}</v></c><c r="O9" s="3"><v>-0.0032245</v></c>'
             '<c r="P9" t="e"><v>#DIV/0!</v></c><c r="Q9" t="s"><v>5</v></c><c r="R9"><v>47</v></c></row>'
             '</sheetData></worksheet>')
    styles = (f'<styleSheet {MAIN}><numFmts count="2">'
              '<numFmt numFmtId="164" formatCode="m&quot;:&quot;ss&quot;.&quot;00"/>'
              '<numFmt numFmtId="165" formatCode="0.0&quot;+&quot;"/></numFmts>'
              '<cellXfs count="4"><xf numFmtId="0"/><xf numFmtId="165"/><xf numFmtId="164"/><xf numFmtId="10"/>'
              '</cellXfs></styleSheet>')
    workbook = f'<workbook {MAIN} {RELS}><sheets><sheet name="Laptimes" sheetId="1" r:id="rId3"/></sheets></workbook>'
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId3" Target="worksheets/sheet1.xml"/></Relationships>')
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as book:
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", rels)
        book.writestr("xl/styles.xml", styles)
        book.writestr("xl/sharedStrings.xml", f"<sst {MAIN}>{shared}</sst>")
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    return data.getvalue()


def test_xlsx_sheet_read_to_the_millisecond():
    text = xlsx_text(sheet_xlsx())
    table = parse_lap_references(text)
    assert table.precise and table.updated == "2026.10.30. 08:48 CEST"
    reference = table.entries[("Road Atlanta", "LMH")]
    assert reference.patch == "1.4+"  # number format of the cell kept ("+" literal)
    assert reference.class_best == pytest.approx(68.725)
    # Step 68.725 x 100.5% = 1:09.068625 (CSV export: 1:09.07): slowest lap time of its level 1:09.068
    assert reference.ladder[0] == pytest.approx(69.068)
    assert reference.fastest_time == pytest.approx(68.577)
    assert "-0.32%" in text and "#DIV/0!" in text
    assert lap_reference.LEVELS[reference.level(69.068)] == "Alien"
    assert lap_reference.LEVELS[reference.level(69.069)] == "Competitive"  # over 1:09.068625
    assert lap_reference.LEVELS[reference.level(69.07)] == "Competitive"  # CSV export: Alien


def test_csv_sheet_is_not_precise():
    from tests.test_lap_reference import SHEET

    assert not parse_lap_references(SHEET).precise


@pytest.mark.parametrize(("number", "code", "text"), [
    (68.725 / DAY, 'm":"ss"."00', "1:08.725000"),
    (3700.5 / DAY, "mm:ss.0", "61:40.500000"),
    (1.4, '0.0"+"', "1.4+"),
    (1.23, '0.0?"+"', "1.23+"),
    (1.2, '0.0?"+"', "1.2+"),
    (0.9285714286, "0%", "93%"),
    (-0.0018915, "0.00%", "-0.19%"),
    (47.0, "General", "47"),
    (0.5, "General", "0.5"),
])
def test_number_formats(number, code, text):
    assert format_number(number, code) == text


class Response:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.data[:size]


@pytest.fixture
def online(monkeypatch):
    """Real fetch_sheet (conftest makes it offline), no wait between attempts; answers: list of bytes or errors"""
    monkeypatch.setattr(lap_reference, "fetch_sheet", REAL_FETCH_SHEET)
    monkeypatch.setattr(lap_reference, "RETRY_DELAYS", (0.0, 0.0))
    answers: list = []
    urls: list[str] = []

    def urlopen(request, timeout=0):
        urls.append(request.full_url)
        answer = answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return Response(answer)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return answers, urls


def test_download_tried_again_when_cut(online):
    answers, urls = online
    answers += [TimeoutError("timed out"), urllib.error.HTTPError("u", 503, "busy", {}, None), sheet_xlsx()]
    table = parse_lap_references(lap_reference.fetch_sheet(lap_reference.DEFAULT_SHEET_URL))
    assert table.precise and len(urls) == 3 and "output=xlsx" in urls[0]


def test_download_not_tried_again_when_offline_or_wrong_address(online):
    answers, urls = online
    answers += [urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))]
    with pytest.raises(OSError):
        lap_reference.fetch_sheet(lap_reference.DEFAULT_SHEET_URL)
    answers += [urllib.error.HTTPError("u", 404, "not found", {}, None)]
    with pytest.raises(OSError):
        lap_reference.fetch_sheet(lap_reference.DEFAULT_SHEET_URL)
    assert len(urls) == 2


def test_csv_export_when_xlsx_unusable(online):
    from tests.test_lap_reference import SHEET

    answers, urls = online
    answers += [b"<html>not a zip</html>", SHEET.encode()]
    table = parse_lap_references(lap_reference.fetch_sheet(lap_reference.DEFAULT_SHEET_URL))
    assert table.entries and not table.precise
    assert "output=xlsx" in urls[0] and "output=csv" in urls[1]
