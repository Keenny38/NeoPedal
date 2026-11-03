import QtQuick
import QtQuick.Layouts

// Country flag (4:3) cut out of the flag sheet, hidden if none: flag = {"url": sheet file, "clip": [x, y, w, h]}
// (flags.flag_view). Thin outline: white flags stay visible on light pages.
//   TpFlag { flag: card.driver.flag || ({}) }
Image {
    id: flagImage
    property var flag: ({})
    readonly property var clip: flagImage.flag && flagImage.flag.clip ? flagImage.flag.clip : []
    readonly property bool known: flagImage.clip.length === 4
    visible: flagImage.known
    source: flagImage.known ? flagImage.flag.url : ""
    sourceClipRect: flagImage.known ? Qt.rect(flagImage.clip[0], flagImage.clip[1], flagImage.clip[2], flagImage.clip[3])
                                    : Qt.rect(0, 0, 0, 0)
    Layout.preferredHeight: Math.round(theme.em * 0.8)
    Layout.preferredWidth: Math.round(theme.em * 0.8 * 4 / 3)
    Layout.alignment: Qt.AlignVCenter
    fillMode: Image.Stretch
    asynchronous: true
    smooth: true
    mipmap: true
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: theme.strokeSubtle
    }
}
