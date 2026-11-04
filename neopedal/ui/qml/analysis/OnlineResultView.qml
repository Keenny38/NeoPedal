import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import "schedule.js" as Js

// Online race picked (Results & Replays, "Online" list): title, date, track; your place & best lap; a summary of the
// races read; positions lap by lap (you, the winner, the cars around you); whole classification. Export to CSV.
Flickable {
    id: view
    objectName: "onlineResultView"
    readonly property var race: online.selected
    readonly property var mine: race.mine || {}
    contentWidth: width
    contentHeight: column.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    ColumnLayout {
        id: column
        width: view.width - theme.space3
        spacing: theme.space4

        TpStateView {
            Layout.fillWidth: true
            Layout.preferredHeight: theme.em * 12
            visible: view.race.title === undefined
            loading: online.state.loading === true
            empty: true
            glyph: ""  // globe
            title: i18n.tr("No race picked")
            text: i18n.tr("Pick one of your online races in the list.")
            loadingText: i18n.tr("Reading your online races…")
        }

        // Race & your result
        TpSectionCard {
            Layout.fillWidth: true
            visible: view.race.title !== undefined
            eyebrow: Js.joined([view.race.date, view.race.drivers])
            title: view.race.title || ""
            actions: [
                TpButton {
                    objectName: "openLocal"
                    flat: true
                    size: "sm"
                    text: i18n.tr("Open Local Session")
                    tip: i18n.tr("Results file of this race on this computer: replay, events & recorded laps")
                    onClicked: online.openLocal()
                },
                TpButton {
                    objectName: "exportClassification"
                    flat: true
                    size: "sm"
                    glyph: theme.glyphs.export
                    fallback: "CSV"
                    tip: i18n.tr("Export the classification to CSV…")
                    onClicked: online.exportClassification()
                }
            ]
            trailing: [GameLogo { source: view.race.trackLogo || ""; boxWidth: theme.em * 4; boxHeight: theme.em * 1.6 }]
            TpText { Layout.fillWidth: true; role: "subtitle"; text: view.race.track || "" }
            TpText { Layout.fillWidth: true; role: "caption"; visible: text !== ""; text: online.state.note || "" }
            Flow {
                Layout.fillWidth: true
                visible: view.mine.position !== undefined
                spacing: theme.space2
                Pill { text: view.mine.position || ""; tint: theme.accent; tip: i18n.tr("Your place") }
                Pill {
                    visible: (view.mine.classPosition || "") !== "" && view.mine.classPosition !== view.mine.position
                    size: "sm"
                    text: i18n.tr("Class") + " " + (view.mine.classPosition || "")
                    tint: theme.dimText
                }
                Pill { visible: (view.mine.grid || "") !== ""; size: "sm"; text: i18n.tr("Grid") + " " + (view.mine.grid || ""); tint: theme.dimText }
                Pill { visible: (view.mine.best || "") !== ""; size: "sm"; text: view.mine.best || ""; tint: theme.dimText }
                Pill { visible: (view.mine.status || "") !== ""; size: "sm"; text: view.mine.status || ""; tint: theme.warning }
            }
        }

        // The races read
        TpSectionCard {
            objectName: "onlineRanks"
            Layout.fillWidth: true
            visible: online.summary.races !== undefined
            title: i18n.tr("Your Online Races")
            tip: i18n.tr("Races read so far (More Results reads older ones)")
            Flow {
                Layout.fillWidth: true
                visible: online.summary.figures !== undefined
                spacing: theme.space6
                Repeater {
                    model: online.summary.figures || []
                    Column {
                        required property var modelData
                        TpText { role: "numeric"; font.weight: Font.DemiBold; text: modelData.value }
                        TpText { role: "caption"; text: modelData.label }
                    }
                }
            }
            TpText { Layout.fillWidth: true; role: "caption"; visible: text !== ""; text: online.summary.races || "" }
        }

        // Positions lap by lap
        TpSectionCard {
            objectName: "onlineLaps"
            Layout.fillWidth: true
            visible: (online.chart.laps || 0) > 1
            title: i18n.tr("Positions Lap by Lap")
            tip: i18n.tr("You, the winner and the cars around you")
            Canvas {
                id: positions
                objectName: "onlineLapChart"
                Layout.fillWidth: true
                Layout.preferredHeight: theme.em * 12
                readonly property var chart: online.chart
                readonly property color mineColor: theme.accent
                readonly property color winnerColor: theme.gain
                readonly property color otherColor: theme.dimText
                readonly property color gridColor: theme.border
                onChartChanged: requestPaint()
                onWidthChanged: requestPaint()
                // Parts of a line drawn: [lap, place] points, broken at laps without position (0)
                function segments(places) {
                    var parts = [], part = []
                    for (var lap = 0; lap < places.length; ++lap) {
                        if (places[lap] > 0) {
                            part.push([lap, places[lap]])
                        } else if (part.length > 0) {
                            parts.push(part)
                            part = []
                        }
                    }
                    if (part.length > 0)
                        parts.push(part)
                    return parts
                }
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var data = chart
                    var laps = data.laps || 0
                    var cars = Math.max(data.cars || 1, 1)
                    if (laps < 2)
                        return
                    var pad = 6
                    function x(lap) { return pad + (width - pad * 2) * (lap / (laps - 1)) }
                    function y(place) { return pad + (height - pad * 2) * ((place - 1) / Math.max(cars - 1, 1)) }
                    ctx.strokeStyle = gridColor
                    ctx.lineWidth = 1
                    ctx.beginPath()
                    ctx.moveTo(pad, y(1)); ctx.lineTo(width - pad, y(1))
                    ctx.moveTo(pad, y(cars)); ctx.lineTo(width - pad, y(cars))
                    ctx.stroke()
                    var lines = data.lines || []
                    for (var pass = 0; pass < 2; ++pass) {  // others under, you on top
                        for (var i = 0; i < lines.length; ++i) {
                            var line = lines[i]
                            if ((pass === 1) !== line.me)
                                continue
                            ctx.strokeStyle = line.me ? mineColor : line.winner ? winnerColor : otherColor
                            ctx.lineWidth = line.me ? 3 : 1.5
                            ctx.beginPath()
                            var parts = segments(line.positions)
                            for (var part = 0; part < parts.length; ++part) {
                                for (var point = 0; point < parts[part].length; ++point) {
                                    var lap = parts[part][point]
                                    if (point === 0) ctx.moveTo(x(lap[0]), y(lap[1]))
                                    else ctx.lineTo(x(lap[0]), y(lap[1]))
                                }
                            }
                            ctx.stroke()
                        }
                    }
                }
            }
            Flow {  // legend: words & line color (never color alone: names written)
                Layout.fillWidth: true
                spacing: theme.space4
                Repeater {
                    model: online.chart.lines || []
                    Row {
                        required property var modelData
                        spacing: theme.space1
                        Rectangle {
                            width: theme.em
                            height: modelData.me ? 3 : 2
                            anchors.verticalCenter: parent.verticalCenter
                            color: modelData.me ? theme.accent : modelData.winner ? theme.gain : theme.dimText
                        }
                        TpText {
                            role: "caption"
                            font.weight: modelData.me ? Font.DemiBold : Font.Normal
                            text: modelData.name
                        }
                    }
                }
            }
        }

        // Whole classification
        TpSectionCard {
            objectName: "onlineClassification"
            Layout.fillWidth: true
            visible: (view.race.rows || []).length > 0
            title: i18n.tr("Classification")
            Repeater {
                model: view.race.rows || []
                Item {
                    id: resultRow
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    implicitHeight: Math.max(theme.row, rowLayout.implicitHeight + theme.space1 * 2)
                    TpListRow {
                        anchors.fill: parent
                        striped: resultRow.index % 2 === 1
                        emphasized: resultRow.modelData.me
                        hovered: resultArea.containsMouse
                    }
                    MouseArea { id: resultArea; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                    RowLayout {
                        id: rowLayout
                        anchors.fill: parent
                        anchors.leftMargin: theme.space2
                        anchors.rightMargin: theme.space2
                        spacing: theme.space3
                        TpText { role: "numeric"; font.weight: Font.DemiBold; text: resultRow.modelData.position; Layout.preferredWidth: theme.em * 2.6 }
                        TpClassBadge {
                            visible: resultRow.modelData.classLabel !== ""
                            label: resultRow.modelData.classLabel
                            fill: resultRow.modelData.classColor || theme.border
                            position: resultRow.modelData.classPosition.replace("P", "")
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            TpText {
                                Layout.fillWidth: true
                                font.weight: resultRow.modelData.me ? Font.DemiBold : Font.Normal
                                text: resultRow.modelData.nameLine
                            }
                            TpText {
                                Layout.fillWidth: true
                                role: "caption"
                                visible: text !== ""
                                text: resultRow.modelData.drivers
                            }
                        }
                        TpText { role: "caption"; text: resultRow.modelData.car; Layout.preferredWidth: theme.em * 12 }
                        TpText { role: "numeric"; text: resultRow.modelData.best; Layout.preferredWidth: theme.em * 5 }
                        TpText { role: "caption"; text: resultRow.modelData.lapsLine; Layout.preferredWidth: theme.em * 6 }
                    }
                }
            }
        }
    }
}
