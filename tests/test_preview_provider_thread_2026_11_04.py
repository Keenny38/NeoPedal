"""Overlay pictures (image://overlaypreview) never read on Qt's image thread (2026-11-04)

The provider is Python: called on Qt's image reader thread it waits for the Python lock, while the UI thread holding
it (window.resize re-binding an Image sourceSize, seen as a hang of test_memory_usage) waits for that thread inside
Qt: app frozen. QML Images of provider URLs load on the UI thread instead.
"""

import re
import threading

from PySide6.QtCore import QByteArray, QCoreApplication, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine

from neopedal.ui.quick import qml_files
from neopedal.ui.quick.preview_provider import PROVIDER_ID, STORE, PreviewProvider

SYNC = 'String(source).indexOf("image://") !== 0'
# Sources carrying store URLs (overlay pictures, played overlay, screen view background, setup wizard tiles)
STORE_SOURCES = re.compile(r"source:.*(preview|liveUrl|shot\.url|backdrop\.source)", re.IGNORECASE)


class RecordingProvider(PreviewProvider):
    def __init__(self):
        super().__init__()
        self.threads: list[threading.Thread] = []

    def requestImage(self, id, size, requestedSize):
        self.threads.append(threading.current_thread())
        return super().requestImage(id, size, requestedSize)


def test_provider_picture_read_on_ui_thread(ui_env):
    from PySide6.QtGui import QColor, QImage

    image = QImage(64, 32, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("red"))
    url = STORE.put("test-thread/picture", image)
    engine = QQmlEngine()
    provider = RecordingProvider()
    engine.addImageProvider(PROVIDER_ID, provider)
    component = QQmlComponent(engine)
    qml = (f'import QtQuick\nImage {{ readonly property bool ready: status === Image.Ready; source: "{url}"; '
           f'asynchronous: {SYNC}; sourceSize.width: 32 }}')
    component.setData(QByteArray(qml.encode()), QUrl())
    item = component.create()
    try:
        assert item is not None, component.errorString()
        assert item.property("ready")  # at once: loaded synchronously
        assert provider.threads == [threading.main_thread()]
    finally:
        STORE.discard("test-thread/picture")
        if item is not None:
            item.deleteLater()
        QCoreApplication.processEvents()


def image_blocks(lines: list[str]):
    """(first line number, lines) of each `Image {` block (brace counted)"""
    for start, line in enumerate(lines):
        if not re.search(r"\bImage\s*\{", line):
            continue
        depth, block = 0, []
        for code in lines[start:]:
            block.append(code)
            depth += code.count("{") - code.count("}")
            if depth <= 0:
                break
        yield start + 1, block


def test_store_pictures_never_asynchronous():
    found = []
    for path in qml_files():
        with open(path, encoding="utf-8") as file:
            lines = file.read().split("\n")
        for number, block in image_blocks(lines):
            text = "\n".join(block)
            if STORE_SOURCES.search(text) and "asynchronous: true" in text:
                found.append(f"{path}:{number}")
    assert not found, "Images of image://overlaypreview URLs must not be asynchronous: " + ", ".join(found)


def test_every_store_picture_uses_the_rule():
    """The rule is written as SYNC (file pictures stay asynchronous)"""
    count = 0
    for path in qml_files():
        with open(path, encoding="utf-8") as file:
            count += file.read().count(SYNC)
    assert count >= 8
