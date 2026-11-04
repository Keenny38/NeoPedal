"""
Render the README animation: a few overlays on the moving simulated race (a corner driven in a
loop, as the hovered cards of the Overlays page), saved as GIF

Two steps, the GIF writer (Pillow) is not an app dependency:
    python tools/make_readme_animation.py frames <folder>           (repo venv: PNG frames)
    python tools/make_readme_animation.py gif <folder> <output.gif> (any Python with Pillow)
"""

from __future__ import annotations

import os
import sys

WIDTH, HEIGHT = 1280, 400
FPS = 15
SECONDS = 6.0  # demo_data.MOTION_PERIOD: one loop
GIF_WIDTH = 960
# overlay: top left corner on the frame
PLACES = {
    "track_map": (40, 24),
    "rpm_led": (250, 26),
    "black_box": (284, 70),
    "friction_circle": (690, 24),
    "pedal": (875, 24),
    "gear": (995, 24),
    "deltabest": (875, 200),
    "trailing": (690, 290),
    "steering_wheel": (1180, 190),
}


def render_frames(folder: str):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import make_readme_preview as preview
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap
    from PySide6.QtWidgets import QWidget

    from neopedal.demo_data import demo_globals, set_motion, update_once
    from neopedal.ui.widget_preview import LivePreview, _shared_style

    preview.load_bundled_fonts()
    preview.cfg.default.set_default()
    for name in preview.cfg.user.__slots__:
        setattr(preview.cfg.user, name, preview.copy_setting(getattr(preview.cfg.default, name)))
    preview.without_game_pictures()
    lives = {name: LivePreview(preview.cfg, name, preview.cfg.user.setting[name]) for name in PLACES}
    missing = [name for name, live in lives.items() if not live.animated]
    if missing:
        raise SystemExit(f"not animated: {', '.join(missing)}")

    def draw(live: LivePreview, seconds: float) -> QPixmap:
        set_motion(live.session, seconds)
        with _shared_style(), demo_globals(live.session):
            update_once(live.widget)
            live.widget.adjustSize()
            pixmap = QPixmap(live.widget.size())
            pixmap.fill(Qt.GlobalColor.transparent)
            live.widget.render(pixmap, renderFlags=QWidget.RenderFlag.DrawChildren)
        return pixmap

    def drawn_rect(pixmap: QPixmap) -> QRect:
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        rect = QRect()
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha():
                    rect = rect.united(QRect(x, y, 1, 1))
        return rect

    crops: dict[str, QRect] = {}
    os.makedirs(folder, exist_ok=True)
    frames = round(SECONDS * FPS)
    for frame in range(frames):
        seconds = frame / FPS
        image = QPixmap(WIDTH, HEIGHT)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, WIDTH, HEIGHT)
        gradient.setColorAt(0, QColor(22, 25, 30))
        gradient.setColorAt(1, QColor(12, 13, 16))
        painter.fillRect(0, 0, WIDTH, HEIGHT, gradient)
        for name, (x, y) in PLACES.items():
            pixmap = draw(lives[name], seconds)
            if name not in crops:  # same crop every frame: overlays never jump
                crops[name] = drawn_rect(pixmap)
            crop = crops[name]
            painter.drawPixmap(x, y, pixmap, crop.x(), crop.y(), crop.width(), crop.height())
        painter.end()
        image.save(os.path.join(folder, f"frame_{frame:03d}.png"))
    for live in lives.values():
        live.close()
    print(f"saved {frames} frames in {folder}")


def write_gif(folder: str, output: str):
    from PIL import Image

    names = sorted(name for name in os.listdir(folder) if name.startswith("frame_"))
    frames = []
    for name in names:
        with Image.open(os.path.join(folder, name)) as image:
            image = image.convert("RGB")
            image = image.resize((GIF_WIDTH, round(image.height * GIF_WIDTH / image.width)), Image.LANCZOS)
            frames.append(image)
    # one palette for every frame, made from frames along the loop: no color flicker, every color kept
    samples = frames[::max(len(frames) // 8, 1)]
    mosaic = Image.new("RGB", (GIF_WIDTH, sum(frame.height for frame in samples)))
    for index, frame in enumerate(samples):
        mosaic.paste(frame, (0, index * frame.height))
    palette = mosaic.quantize(colors=255, method=Image.Quantize.FASTOCTREE)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    quantized[0].save(output, save_all=True, append_images=quantized[1:], duration=round(1000 / FPS), loop=0,
                      optimize=True, disposal=1)
    print(f"saved {output} {len(frames)} frames ({os.path.getsize(output) // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "frames":
        render_frames(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "gif":
        write_gif(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)
