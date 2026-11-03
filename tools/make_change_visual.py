"""
Render a before / after visual of overlay changes: docs/changes/<date>-<slug>.png

Each widget is rendered twice on the same simulated race data as the README preview
(tools/make_readme_preview.py): with the code of a base revision (default HEAD, so the
last commit) and with the working tree. Both renders are placed side by side, base on
the left, changed areas framed on both sides. Commit the image with the change: release
notes (tools/gen_release_notes.py) show every image added under docs/changes in their
Visuals section, captioned by --title (stored in the image, with the widget names).
Write the title in English, like the release notes.

Run from project root, before committing the overlay change:
    python tools/make_change_visual.py --scan
        every widget (modern & classic look) whose render changed, and the ones no image covers yet
    python tools/make_change_visual.py black_box --title "..."
    python tools/make_change_visual.py black_box --set black_box.show_motor_map=true --slug motor-map
    python tools/make_change_visual.py relative standings --base HEAD~2 --theme both
    python tools/make_change_visual.py --images before.png after.png --name home --title "..."
        app page screenshots made by a script (same layout: cropped, changes framed)

A widget whose before and after renders are the same is left out of the image (the change
does not show on the simulated race: show it with --set, or write [visual] in the commit
message instead); no image is written if every pair is the same.

--set overrides a widget option in both renders (JSON value, plain text if not JSON),
to show an option that is off by default. Unknown options are ignored by older code.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUTPUT_DIR = os.path.join("docs", "changes")
MARGIN = 24
GAP = 48
LABEL_HEIGHT = 34
# Overlay theme of each look (render file "<widget>.<look>.png", modern look: "<widget>.png")
THEMES = {"modern": "Modern Dark", "classic": "Legacy Grey"}
OPTIONAL_THEMES = {"grey": "Modern Grey"}  # --theme grey only (the scan covers the two looks above)
# Same pixel noise tolerance as the CI visual check (tools/visual_diff.py)
CHANNEL_TOLERANCE = 24
CHANGED_RATIO = 0.002
CELL = 8  # changed areas: grid cells of CELL pixels, joined when they touch
FRAME_PADDING = 3
FRAME_MAX_RATIO = 0.4  # more changed pixels: whole look changed, no frame
FRAME_MAX_COUNT = 6  # more changed areas, or areas covering more than FRAME_MAX_COVER of the image:
FRAME_MAX_COVER = 0.35  # layout moved (cards reflowed), frames would point everywhere
FRAME_COLOR = (255, 176, 32)
PREVIEW_LEFTOVERS = ("brakes.json", "brands.json", "compounds.json")

# Runs inside a source tree (base worktree or working tree), with that tree's code:
# same setup as README preview main(), then renders the asked widgets as PNG files.
RENDER_SCRIPT = r'''
import json, os, pkgutil, sys, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
import tools.make_readme_preview as preview
from PySide6.QtCore import Qt, QTimerEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget
from importlib import import_module

names, themes, overrides, output = (json.loads(sys.argv[1]), json.loads(sys.argv[2]),
                                    json.loads(sys.argv[3]), sys.argv[4])
if not names:  # scan: every widget of this tree
    names = sorted(module.name for module in pkgutil.iter_modules(import_module("neopedal.widget").__path__)
                   if not module.name.startswith("_"))
preview.load_bundled_fonts()
preview.cfg.default.set_default()
for slot in preview.cfg.user.__slots__:
    setattr(preview.cfg.user, slot, preview.copy_setting(getattr(preview.cfg.default, slot)))
for name, options in overrides.items():
    if name in preview.cfg.user.setting:  # widget new in after tree: not in older revision
        preview.cfg.user.setting[name].update(options)
if hasattr(preview, "without_game_pictures"):  # no game logo in published images (older revisions: none)
    preview.without_game_pictures()
import time
fixed_time = time.strptime("2026-06-13 15:04:00", "%Y-%m-%d %H:%M:%S")
for clock in ("neopedal.widget.session", "neopedal.widget._modern.session"):  # same clock in both trees
    try:
        import_module(clock).strftime = lambda fmt, *args: time.strftime(fmt, *(args or (fixed_time,)))
    except ImportError:
        pass
import psutil  # same system readings in both trees (System Performance)
psutil.cpu_percent = lambda *args, **kwargs: 12.0
psutil.virtual_memory = lambda: type("Memory", (), {"used": 9.6 * 1024 ** 3, "total": 32 * 1024 ** 3, "percent": 30.0})()
psutil.Process.cpu_percent = lambda self, *args, **kwargs: 24.0
psutil.Process.memory_full_info = lambda self: type("Memory", (), {"uss": 182 * 1024 ** 2, "rss": 210 * 1024 ** 2})()
sim, data = preview.lmu_api()
preview.api._api, preview.api.read = sim, sim.reader()
preview.set_telemetry(sim, data)
preview.set_vehicles()
preview.set_modules()
style = preview.cfg.user.config.get("overlay_style", {})
for look, theme in themes.items():
    if "overlay_theme" in style:  # older revisions: one look only
        style["overlay_theme"] = theme
    for name in names:
        try:
            module = import_module(f"neopedal.widget.{name}")
        except ModuleNotFoundError:  # new widget: no before render, shown as "(new)"
            continue
        try:
            try:  # modern design (older revisions have none)
                from neopedal.widget._modern import create_widget
            except ImportError:
                widget = module.Realtime(preview.cfg, name)
            else:
                widget = create_widget(module, preview.cfg, name)
            widget.adjustSize()
            if name in getattr(preview, "HISTORY_WIDGETS", ()):  # input history (older revisions: none)
                preview.replay_history(widget, data)
            for _ in range(3):
                widget.timerEvent(QTimerEvent(0))
            widget.adjustSize()
            pixmap = QPixmap(widget.size())
            pixmap.fill(Qt.GlobalColor.transparent)
            widget.render(pixmap, renderFlags=QWidget.RenderFlag.DrawChildren)
            suffix = "" if look == "modern" else f".{look}"
            pixmap.save(os.path.join(output, f"{name}{suffix}.png"))
            widget.deleteLater()
        except Exception:  # one broken widget never stops the others
            print(f"render failed: {name} ({look})", file=sys.stderr)
            traceback.print_exc()
'''


def parse_overrides(values: list[str]) -> dict[str, dict]:
    """--set widget.option=value, value as JSON (plain text if not JSON)"""
    overrides: dict[str, dict] = {}
    for item in values:
        key, _, raw = item.partition("=")
        widget, _, option = key.partition(".")
        if not (widget and option and raw):
            raise SystemExit(f"invalid --set {item!r}, expected widget.option=value")
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        overrides.setdefault(widget, {})[option] = value
    return overrides


def render_tree(tree: str, names: list[str], overrides: dict, output: str, looks: tuple[str, ...] = ("modern",)):
    """Render widgets (every widget if names is empty) with the code of one source tree"""
    os.makedirs(output, exist_ok=True)
    themes = {look: {**THEMES, **OPTIONAL_THEMES}[look] for look in looks}
    leftovers = [os.path.join(tree, name) for name in PREVIEW_LEFTOVERS if not os.path.exists(os.path.join(tree, name))]
    try:
        subprocess.run(
            [sys.executable, "-c", RENDER_SCRIPT, json.dumps(names), json.dumps(themes), json.dumps(overrides), output],
            cwd=tree, check=True,
        )
    finally:
        for path in leftovers:  # user files the preview data writes in the tree, never kept
            if os.path.exists(path):
                os.remove(path)


def render_base(revision: str, names: list[str], overrides: dict, output: str, looks: tuple[str, ...]):
    """Render widgets with the code of a revision (temporary worktree)"""
    with tempfile.TemporaryDirectory() as temp:
        base_tree = os.path.join(temp, "base")
        subprocess.run(["git", "worktree", "add", "--detach", "--quiet", base_tree, revision], cwd=ROOT, check=True)
        try:
            render_tree(base_tree, names, overrides, output, looks)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", base_tree], cwd=ROOT, check=False)


def row_label(stem: str) -> str:
    """Render file stem as row label: "gear", "gear.classic" -> "gear (classic)\""""
    name, _, look = stem.partition(".")
    return f"{name} ({look})" if look else name


def changed_areas(before, after) -> tuple[float, list]:
    """Changed pixel ratio of two same size images (1.0 if size differs), framed areas (QRect list)

    A pixel changed if any channel differs by more than CHANNEL_TOLERANCE (antialiasing noise ignored).
    Changed CELL x CELL cells are joined into areas when they touch. No area when the size differs, when
    more than FRAME_MAX_RATIO of the pixels changed (the whole look changed: nothing to point at), or when
    the areas are too many or too large (FRAME_MAX_COUNT, FRAME_MAX_COVER: the layout moved).
    """
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage

    if before.size() != after.size():
        return 1.0, []
    width, height = after.width(), after.height()
    if not width or not height:
        return 0.0, []
    first = before.convertToFormat(QImage.Format.Format_ARGB32)
    second = after.convertToFormat(QImage.Format.Format_ARGB32)
    stride = first.bytesPerLine()
    data_a = bytes(first.constBits())[:stride * height]
    data_b = bytes(second.constBits())[:stride * height]
    columns, rows = -(-width // CELL), -(-height // CELL)
    cells = set()
    changed = 0
    for y in range(height):
        start = y * stride
        line_a, line_b = data_a[start:start + width * 4], data_b[start:start + width * 4]
        if line_a == line_b:
            continue
        for x in range(width):
            offset = x * 4
            if any(abs(line_a[offset + channel] - line_b[offset + channel]) > CHANNEL_TOLERANCE
                   for channel in range(4)):
                changed += 1
                cells.add((x // CELL, y // CELL))
    ratio = changed / (width * height)
    if ratio <= CHANGED_RATIO or ratio > FRAME_MAX_RATIO:
        return ratio, []
    areas = []
    unseen = set(cells)
    while unseen:
        stack = [unseen.pop()]
        left, top = right, bottom = stack[0]
        while stack:
            cx, cy = stack.pop()
            left, right, top, bottom = min(left, cx), max(right, cx), min(top, cy), max(bottom, cy)
            for nx in range(cx - 1, cx + 2):  # touching cells, diagonals included
                for ny in range(cy - 1, cy + 2):
                    if (nx, ny) in unseen and 0 <= nx < columns and 0 <= ny < rows:
                        unseen.remove((nx, ny))
                        stack.append((nx, ny))
        rect = QRect(left * CELL - FRAME_PADDING, top * CELL - FRAME_PADDING,
                     (right - left + 1) * CELL + FRAME_PADDING * 2, (bottom - top + 1) * CELL + FRAME_PADDING * 2)
        areas.append(rect.intersected(QRect(0, 0, width, height)))
    if (len(areas) > FRAME_MAX_COUNT
            or sum(area.width() * area.height() for area in areas) > FRAME_MAX_COVER * width * height):
        return ratio, []
    return ratio, sorted(areas, key=lambda rect: (rect.top(), rect.left()))


def same_render(before_file: str, after_file: str) -> bool:
    """Both renders exist and look the same (within CI noise tolerance)"""
    from PySide6.QtGui import QImage

    if not (os.path.exists(before_file) and os.path.exists(after_file)):
        return False
    ratio, _ = changed_areas(QImage(before_file), QImage(after_file))
    return ratio <= CHANGED_RATIO


def compose(names: list[str], before_dir: str, after_dir: str, title: str, output: str,
            highlight: bool = True, widgets: list[str] | None = None):
    """Before / after pairs, one row per render file stem ("<widget>" or "<widget>.<look>")"""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QApplication

    from neopedal.main import load_bundled_fonts
    from tools.make_readme_preview import BACKGROUND

    _app = QApplication.instance() or QApplication(sys.argv)
    load_bundled_fonts()
    rows = []
    for name in names:
        before = QPixmap(os.path.join(before_dir, f"{name}.png"))  # null if widget is new
        after = QPixmap(os.path.join(after_dir, f"{name}.png"))
        areas = []
        if highlight and not (before.isNull() or after.isNull()):
            areas = changed_areas(before.toImage(), after.toImage())[1]
        rows.append((before, after, areas))
    label_font = QFont("JetBrains Mono", 12)
    label_metrics = QFontMetrics(label_font)
    label_width = max(label_metrics.horizontalAdvance(f"Before · {row_label(name)}") for name in names)
    column = max(label_width, *(max(before.width(), after.width()) for before, after, _ in rows))  # label never cut
    title_font = QFont("JetBrains Mono", 14, QFont.Weight.Bold)
    title_width = QFontMetrics(title_font).horizontalAdvance(title)
    width = max(MARGIN * 2 + column * 2 + GAP, MARGIN * 2 + title_width)  # title never cut
    height = MARGIN * 2 + LABEL_HEIGHT * 2 + sum(
        max(before.height(), after.height()) + LABEL_HEIGHT for before, after, _ in rows)
    image = QPixmap(width, height)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(title_font)
    painter.setPen(QColor(255, 255, 255, 220))
    painter.drawText(QRectF(MARGIN, MARGIN, width - MARGIN * 2, LABEL_HEIGHT),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
    top = MARGIN + LABEL_HEIGHT * 2
    painter.setFont(label_font)
    frame = QPen(QColor(*FRAME_COLOR, 230), 2)
    for name, (before, after, areas) in zip(names, rows):
        for index, (label, pixmap) in enumerate((("Before", before), ("After", after))):
            left = MARGIN + index * (column + GAP)
            painter.setPen(QColor(255, 255, 255, 150))
            painter.drawText(QRectF(left, top - LABEL_HEIGHT, column, LABEL_HEIGHT),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{label} · {row_label(name)}")
            if pixmap.isNull():
                painter.drawText(QRectF(left, top, column, LABEL_HEIGHT), Qt.AlignmentFlag.AlignLeft, "(new)")
                continue
            painter.drawPixmap(int(left), int(top), pixmap)
            painter.setPen(frame)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for area in areas:  # same place on both sides: the eye finds what changed
                painter.drawRoundedRect(QRectF(area).translated(left, top).adjusted(1, 1, -1, -1), 4, 4)
        top += max(before.height(), after.height()) + LABEL_HEIGHT
    painter.end()
    picture = image.toImage()
    picture.setText("Title", title)  # caption of the image in release notes
    picture.setText("Widgets", ",".join(widgets if widgets is not None else
                                        dict.fromkeys(name.partition(".")[0] for name in names)))
    picture.save(output)


def crop_to_content(before, after) -> tuple:
    """Cut the empty background around both screenshots (corner color), same box when same size"""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage

    def content_box(image) -> QRect:
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
        width, height, stride = image.width(), image.height(), image.bytesPerLine()
        data = bytes(image.constBits())[:stride * height]
        corner = data[(height - 1) * stride + (width - 1) * 4:(height - 1) * stride + width * 4]
        empty = corner * width
        left, right, top, bottom = width, -1, height, -1
        for y in range(height):
            line = data[y * stride:y * stride + width * 4]
            if line == empty:
                continue
            pixels = [line[x * 4:x * 4 + 4] != corner for x in range(width)]
            left, right = min(left, pixels.index(True)), max(right, width - 1 - pixels[::-1].index(True))
            top, bottom = min(top, y), y
        if right < 0:
            return image.rect()
        pad = 8
        return QRect(left, top, right - left + 1, bottom - top + 1).adjusted(
            -pad, -pad, pad, pad).intersected(image.rect())

    first, second = content_box(before), content_box(after)
    if before.size() == after.size():
        first = second = first.united(second)
    return before.copy(first), after.copy(second)


def added_visuals(base: str) -> list[str]:
    """Images of docs/changes added since base: committed since, staged or not yet tracked"""
    def git(*args: str) -> list[str]:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return result.stdout.splitlines()

    paths = git("diff", "--name-only", "--diff-filter=A", base, "--", "docs/changes/*.png")
    paths += git("ls-files", "--others", "--exclude-standard", "--", "docs/changes/*.png")
    return sorted(set(paths))


def covered_widgets(paths: list[str]) -> set[str]:
    """Widget names stored in before / after images (images of app pages store none)"""
    from PySide6.QtGui import QImage

    widgets: set[str] = set()
    for path in paths:
        text = QImage(os.path.join(ROOT, path)).text("Widgets")
        widgets.update(name for name in text.split(",") if name)
    return widgets


def scan(base: str, overrides: dict) -> int:
    """List widgets whose render changed (both looks), exit 1 if a changed widget has no image yet"""
    from PySide6.QtGui import QGuiApplication

    _app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    looks = tuple(THEMES)
    with tempfile.TemporaryDirectory() as temp:
        before_dir, after_dir = os.path.join(temp, "before"), os.path.join(temp, "after")
        render_base(base, [], overrides, before_dir, looks)
        render_tree(ROOT, [], overrides, after_dir, looks)
        before = {name[:-4] for name in os.listdir(before_dir) if name.endswith(".png")}
        after = {name[:-4] for name in os.listdir(after_dir) if name.endswith(".png")}
        changed: dict[str, list[str]] = {}
        from PySide6.QtGui import QImage

        for stem in sorted(before & after):
            first = QImage(os.path.join(before_dir, f"{stem}.png"))
            second = QImage(os.path.join(after_dir, f"{stem}.png"))
            ratio, _ = changed_areas(first, second)
            if ratio > CHANGED_RATIO:
                name, _, look = stem.partition(".")
                note = (f"size {first.width()}x{first.height()} -> {second.width()}x{second.height()}"
                        if first.size() != second.size() else f"{ratio:.1%} of pixels")
                changed.setdefault(name, []).append(f"{look or 'modern'} {note}")
        new = sorted({stem.partition(".")[0] for stem in after - before})
        removed = sorted({stem.partition(".")[0] for stem in before - after})
    visuals = added_visuals(base)
    covered = covered_widgets(visuals)
    print(f"Widget renders changed since {base} (simulated race, modern & classic look):")
    if not (changed or new):
        print("  none. A change that does not show on the simulated race needs --set, or [visual] in the commit.")
    for name, notes in changed.items():
        print(f"  {name:<24} {'; '.join(notes)}{'' if name in covered else '   <- no image yet'}")
    for name in new:
        print(f"  {name:<24} new widget{'' if name in covered else '   <- no image yet'}")
    if removed:
        print(f"Removed widgets: {', '.join(removed)}")
    if visuals:
        print(f"Images added since {base}: {', '.join(os.path.basename(path) for path in visuals)}")
    missing = [name for name in [*changed, *new] if name not in covered]
    if missing:
        theme = " --theme both" if any("classic" in note for name in missing for note in changed.get(name, ())) else ""
        print("\nNo before / after image yet (group the ones of one change in one image):")
        print(f"  python tools/make_change_visual.py {' '.join(missing)}{theme} --title \"...\"")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("widgets", nargs="*", help="widget names, for example black_box")
    parser.add_argument("--base", default="HEAD", help="revision rendered as before (default HEAD)")
    parser.add_argument("--set", action="append", default=[], metavar="WIDGET.OPTION=VALUE",
                        help="option override in both renders (repeatable)")
    parser.add_argument("--theme", choices=("modern", "classic", "grey", "both"), default="modern",
                        help="overlay look rendered (default modern; grey: Modern Grey theme, before = former code)")
    parser.add_argument("--scan", action="store_true",
                        help="list every widget whose render changed, and the ones no image covers yet")
    parser.add_argument("--images", nargs=2, metavar=("BEFORE", "AFTER"),
                        help="compose two screenshots of an app page instead of rendering widgets")
    parser.add_argument("--name", default="", help="row label of --images (default: after file name)")
    parser.add_argument("--no-frame", action="store_true", help="do not frame changed areas")
    parser.add_argument("--slug", default="", help="file name part (default: widget names)")
    parser.add_argument("--title", default="", help="caption on top (default: widget names)")
    args = parser.parse_args()
    overrides = parse_overrides(args.set)
    if args.scan:
        return scan(args.base, overrides)
    if not (args.widgets or args.images):
        parser.error("give widget names, --images BEFORE AFTER, or --scan")
    if args.images and not args.title:
        parser.error("--images needs --title")

    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv[:1])
    with tempfile.TemporaryDirectory() as temp:
        before_dir, after_dir = os.path.join(temp, "before"), os.path.join(temp, "after")
        if args.images:
            from PySide6.QtGui import QImage

            name = args.name or os.path.splitext(os.path.basename(args.images[1]))[0]
            stems, widgets = [name], []  # app page: covers no widget
            before, after = crop_to_content(QImage(args.images[0]), QImage(args.images[1]))
            for folder, image in ((before_dir, before), (after_dir, after)):
                os.makedirs(folder, exist_ok=True)
                image.save(os.path.join(folder, f"{name}.png"))
        else:
            looks = tuple(THEMES) if args.theme == "both" else (args.theme,)
            render_base(args.base, args.widgets, overrides, before_dir, looks)
            render_tree(ROOT, args.widgets, overrides, after_dir, looks)
            stems = [f"{name}{'' if look == 'modern' else '.' + look}" for name in args.widgets for look in looks]
            widgets = list(args.widgets)
        same = [stem for stem in stems
                if same_render(os.path.join(before_dir, f"{stem}.png"), os.path.join(after_dir, f"{stem}.png"))]
        missing = [stem for stem in stems if not os.path.exists(os.path.join(after_dir, f"{stem}.png"))]
        for stem in same:
            print(f"left out: {row_label(stem)} looks the same before and after")
        for stem in missing:
            print(f"left out: {row_label(stem)} has no render (unknown widget, or render failed)")
        stems = [stem for stem in stems if stem not in same and stem not in missing]
        if not stems:
            print("No image written: nothing changed on the simulated race. Show the change with --set, "
                  "or write [visual] in the commit message.")
            return 1
        if not args.images:  # widgets left out are not covered by this image
            widgets = [name for name in widgets if any(stem.partition(".")[0] == name for stem in stems)]
        slug = args.slug or "-".join(name.replace("_", "-") for name in (widgets or [stems[0]]))
        output = os.path.join(OUTPUT_DIR, f"{datetime.date.today().isoformat()}-{slug}.png")
        os.makedirs(os.path.join(ROOT, OUTPUT_DIR), exist_ok=True)
        compose(stems, before_dir, after_dir, args.title or ", ".join(widgets or stems),
                os.path.join(ROOT, output), highlight=not args.no_frame, widgets=widgets)
    print(f"saved {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
