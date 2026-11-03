import QtQuick

// Letter on a color fill: level (round) and tyre compound (square, as in overlays) badges. Whole pixel size
// (even: centered letter on a pixel) and letter sized from the badge, its capitals centered in the badge (cap
// height, not the font line nor the tight ink box, padded below the baseline), placed on screen pixels.
//   TpLetterBadge { letter: "M"; fill: level.color }
//   TpLetterBadge { shape: "square"; letter: "S"; fill: theme.compound("Soft") }
Rectangle {
    id: badge
    property string letter: ""
    property color fill: theme.border
    property string shape: "round"  // "round" | "square" (rounded corners)
    property real size: theme.em * 1.25

    readonly property int side: Math.max(8, Math.round(size / 2) * 2)
    implicitWidth: side
    implicitHeight: side
    radius: shape === "round" ? side / 2 : Math.max(2, Math.round(side * 0.22))
    color: fill
    antialiasing: true

    Rectangle {  // inner rim a shade darker, over the fill: edge stays crisp on any surface (light fills on light cards)
        anchors.fill: parent
        radius: badge.radius
        color: "transparent"
        border.width: 1
        border.color: theme.tint(theme.scrim, "selected")
        antialiasing: true
    }

    readonly property real pixel: 1 / Math.max(1, Screen.devicePixelRatio)  // screen pixel (scaled screens)

    function snap(value) { return Math.round(value / pixel) * pixel }

    TextMetrics {
        id: ink
        text: badge.letter
        font: label.font
    }
    TextMetrics {  // flat capital: its tight top is the cap height (figures as tall)
        id: caps
        text: "H"
        font: label.font
    }
    Text {
        id: label
        text: badge.letter
        textFormat: Text.PlainText
        color: theme.inkOn(badge.fill)  // readable on the fill
        font.pixelSize: Math.max(7, Math.round(badge.side * (badge.letter.length > 1 ? 0.48 : 0.62)))
        font.weight: Font.Bold
        // ink width centered (tight bounds from the pen origin), baseline half a cap height below the middle
        x: badge.snap((badge.width - ink.tightBoundingRect.width) / 2 - ink.tightBoundingRect.x)
        y: badge.snap((badge.height - caps.tightBoundingRect.y) / 2 - baselineOffset)
    }
}
