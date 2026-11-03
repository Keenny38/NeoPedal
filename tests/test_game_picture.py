"""Car & circuit pictures of the game in QML pages (components/GamePicture.qml)"""

import time

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlComponent, QQmlEngine


def test_fitted_picture_squeezed_by_its_row_without_binding_loop(ui_env, tmp_path):
    """Mipmap followed the painted size: a car picture squeezed by its row (Results laps header) turned mipmaps on,
    which reloads the picture, box collapsed meanwhile (binding loops on mipmap & shown in the app log)"""
    from neopedal.ui.quick import QML_FOLDER, Theme

    picture = tmp_path / "car.png"
    image = QImage(640, 200, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    assert image.save(str(picture))
    components = QUrl.fromLocalFile(QML_FOLDER + "/components").toString()
    qml = f"""
import QtQuick
import QtQuick.Layouts
import "{components}"
RowLayout {{
    width: 40
    height: 40
    property bool shown: car.shown
    property real carWidth: car.width
    Text {{ Layout.fillWidth: true; text: "Team name long enough to squeeze the picture box" }}
    GamePicture {{ id: car; source: "{QUrl.fromLocalFile(str(picture)).toString()}"; boxHeight: 30; aspect: 1.6; crop: false }}
}}
"""
    engine = QQmlEngine()
    warnings: list[str] = []
    engine.setOutputWarningsToStandardError(False)
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    theme = Theme(None)
    engine.rootContext().setContextProperty("theme", theme)
    component = QQmlComponent(engine)
    component.setData(qml.encode(), QUrl.fromLocalFile(str(tmp_path / "Probe.qml")))
    root = component.create()
    assert root is not None, component.errorString()
    end = time.monotonic() + 5
    while not root.property("shown") and time.monotonic() < end:
        QCoreApplication.processEvents()
    for _ in range(20):  # picture reloaded by a mipmap change, if any
        QCoreApplication.processEvents()
    assert root.property("shown") and root.property("carWidth") > 0
    assert not warnings
    root.deleteLater()
    QCoreApplication.processEvents()
