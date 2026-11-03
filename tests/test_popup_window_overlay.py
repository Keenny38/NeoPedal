"""Popups open once their page is in the app window

A page made before the app shows it moves to the app window (QQuickWidget); the item a popup is declared in
follows, while a popup's own Overlay.overlay stays on the former window: no parent once that window is gone, open()
does nothing (live 2026-11-02: Weekly Leaderboard, Register…, lap library, math channels, setup comparison,
track notes dialogs, stream token confirmation never opened). Offscreen tests keep one window and never show it,
so the rule is checked in the QML: popups keep their declaring item as parent and center & size on
TpPopup.overlayItem (that item's window overlay), or parent to an item's overlay (page.Overlay.overlay).
"""

import re
from pathlib import Path

import neopedal

QML = Path(neopedal.__file__).parent / "ui" / "qml"
OWN_OVERLAY = re.compile(r"(?<![\w.])Overlay\.overlay")  # popup's own attached overlay (not item.Overlay.overlay)


def code_lines(path: Path):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("//", 1)[0]
        if code.strip():
            yield number, code


def test_no_popup_uses_its_own_overlay():
    found = [f"{path.relative_to(QML)}:{number}: {code.strip()}"
             for path in sorted(QML.rglob("*.qml")) for number, code in code_lines(path)
             if OWN_OVERLAY.search(code)]
    assert not found, "\n".join(found)


def test_popups_center_on_their_window_overlay():
    popup = (QML / "components" / "TpPopup.qml").read_text(encoding="utf-8")
    assert "readonly property Item overlayItem: parent ? parent.Overlay.overlay : null" in popup
    for name in ("components/TpDialog.qml", "components/TpUnsavedDialog.qml", "config/DeletedPresets.qml",
                 "config/PresetBackups.qml", "config/PresetComparePanel.qml", "config/PresetTransfer.qml",
                 "telemetry/LapLibraryPanel.qml", "telemetry/MathChannels.qml", "telemetry/RecentlyDeleted.qml"):
        text = (QML / name).read_text(encoding="utf-8")
        assert "anchors.centerIn: overlayItem" in text, name
        assert not re.search(r"^    parent:", text, re.MULTILINE), name  # declaring item kept as parent
