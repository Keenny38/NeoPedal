import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import "schedule.js" as Js

// Online races you drove (Results & Replays, "Online" list): kind (daily, weekly & special, championships), your
// races newest first (your place, Driver & Safety Rank changes), More Results for older ones. Read from RaceControl
// with the game sign in ("online" backend, see quick/online_results.py); a race picked shows on the right.
ColumnLayout {
    id: onlineList
    objectName: "onlineResults"
    spacing: theme.space2

    TpSegmented {
        objectName: "onlineKind"
        Layout.fillWidth: true
        Layout.leftMargin: theme.padCard
        Layout.rightMargin: theme.padCard
        Layout.topMargin: theme.space2
        name: i18n.tr("Races")
        options: [i18n.tr("Daily"), i18n.tr("Weekly & Special"), i18n.tr("Championships")]
        currentIndex: online.state.kind || 0
        onActivated: function(index) { online.setKind(index) }
    }

    ListView {
        id: raceList
        objectName: "onlineList"
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: online.rows
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        delegate: Item {
            id: raceRow
            required property var modelData
            required property int index
            readonly property bool selected: online.state.selectedKey === modelData.key
            width: raceList.width
            implicitHeight: rowColumn.implicitHeight + theme.space2 * 2
            TpListRow {
                anchors.fill: parent
                selected: raceRow.selected
                hovered: rowArea.containsMouse
            }
            MouseArea {
                id: rowArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: online.select(raceRow.modelData.key)
            }
            ColumnLayout {
                id: rowColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: theme.padCard
                anchors.rightMargin: theme.padCard
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    spacing: theme.space2
                    TpText {
                        Layout.fillWidth: true
                        font.weight: Font.DemiBold
                        text: raceRow.modelData.title
                    }
                    Pill {
                        visible: (raceRow.modelData.mine.position || "") !== ""
                        size: "sm"
                        text: raceRow.modelData.mine.position || ""
                        tint: theme.accent
                    }
                }
                TpText {
                    Layout.fillWidth: true
                    role: "caption"
                    text: Js.joined([raceRow.modelData.date, raceRow.modelData.track, raceRow.modelData.split])
                }
                TpText {
                    Layout.fillWidth: true
                    role: "caption"
                    visible: text !== ""
                    text: raceRow.modelData.mine.ranksLine || ""
                }
            }
        }
        footer: ColumnLayout {
            width: raceList.width
            spacing: theme.space2
            TpButton {
                objectName: "moreOnline"
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: theme.space2
                visible: online.rows.length > 0 && online.state.more === true
                enabled: online.state.loading !== true
                flat: true
                size: "sm"
                text: i18n.tr("More Results")
                onClicked: online.more()
            }
            TpSpinner { Layout.alignment: Qt.AlignHCenter; visible: online.state.loading === true }
            TpText {
                Layout.fillWidth: true
                Layout.leftMargin: theme.padCard
                role: "caption"
                wrap: true
                visible: text !== ""
                text: online.state.error || ""
            }
        }
        TpStateView {
            anchors.centerIn: parent
            visible: raceList.count === 0 && online.state.loading !== true
            empty: raceList.count === 0
            glyph: ""  // globe
            title: i18n.tr("No online race of this kind")
            text: i18n.tr("Your online races are read from RaceControl while Le Mans Ultimate runs.")
            actionText: i18n.tr("Read Again")
            onAction: online.readAgain()
        }
    }
}
