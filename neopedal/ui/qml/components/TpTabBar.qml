import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Underlined tabs: icon, text & optional count per tab ({ text, glyph, count }), underline slides to the current tab.
// One Tab stop: arrows, Home & End choose (like TpSegmented). Extra controls after the tabs (right side): children.
// Rule (Development.md): TpTabBar switches between views of a page or panel, TpSegmented picks a filter or a mode.
// Not enough room: tabs keep their texts with less padding (squeezed); minimumWidth tells the room they need then
// (a caller may show a drop-down list instead below it).
//   TpTabBar { model: [{ text: i18n.tr("Fuel"), glyph: "" }, ...]; currentIndex: backend.tab
//              onActivated: function(index) { backend.setTab(index) } }
ColumnLayout {
    id: bar
    property var model: []
    property int currentIndex: 0
    property string name: ""
    default property alias trailing: trailingRow.data
    // Counts of the tabs (-1: none), apart from the model: a count changing never makes the tabs again
    property var counts: []
    signal activated(int index)

    // Widths of the tabs (contents only, from texts: never from .visible), with full and squeezed padding
    readonly property real padFull: theme.em * 1.6
    readonly property real padSqueezed: theme.em * 0.7
    readonly property real contentsWidth: {
        var sum = 0
        for (var i = 0; i < tabRepeater.count; i++) {  // count read: evaluated again once the tabs are made
            var item = tabRepeater.itemAt(i)
            if (item)
                sum += item.contentWidth
        }
        return sum + Math.max(0, tabRepeater.count - 1) * theme.space1
    }
    readonly property real naturalWidth: contentsWidth + tabRepeater.count * padFull
    readonly property real minimumWidth: contentsWidth + tabRepeater.count * padSqueezed
    readonly property bool squeezed: width > 0 && naturalWidth > width - trailingRow.implicitWidth - theme.space4

    function choose(index) {
        if (index >= 0 && index < model.length && index !== currentIndex)
            activated(index)
    }

    Layout.fillWidth: true
    spacing: 0
    activeFocusOnTab: true
    Keys.onLeftPressed: choose(currentIndex - 1)
    Keys.onRightPressed: choose(currentIndex + 1)
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Home) { choose(0); event.accepted = true }
        else if (event.key === Qt.Key_End) { choose(model.length - 1); event.accepted = true }
    }
    Keys.onShortcutOverride: function(event) {
        if ([Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End].indexOf(event.key) >= 0)
            event.accepted = true
    }
    Accessible.role: Accessible.PageTabList
    Accessible.name: name

    RowLayout {
        Layout.fillWidth: true
        spacing: theme.space1
        Repeater {
            id: tabRepeater
            model: bar.model
            AbstractButton {
                id: tabButton
                required property var modelData
                required property int index
                readonly property bool current: bar.currentIndex === index
                readonly property int count: index < bar.counts.length && typeof bar.counts[index] === "number"
                                             ? bar.counts[index]
                                             : typeof modelData.count === "number" ? modelData.count : -1
                readonly property real contentWidth: tabRow.implicitWidth
                implicitHeight: Math.round(theme.controlHeight)
                implicitWidth: contentWidth + (bar.squeezed ? bar.padSqueezed : bar.padFull)
                hoverEnabled: true
                focusPolicy: Qt.NoFocus  // the bar takes Tab, arrows move
                Accessible.role: Accessible.PageTab
                Accessible.name: count >= 0 ? modelData.text + " (" + count + ")" : modelData.text
                Accessible.selected: current
                onClicked: bar.choose(index)
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                background: Rectangle {
                    radius: theme.radiusSm
                    color: tabButton.hovered && !tabButton.current ? theme.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: theme.motionFast } }
                    FocusRing { visible: bar.activeFocus && tabButton.current }
                }
                contentItem: Item {
                    Row {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: theme.space3
                        Icon {
                            glyph: tabButton.modelData.glyph || ""
                            size: theme.iconSm
                            color: tabButton.current ? theme.accent : theme.dimText
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TpText {
                            text: tabButton.modelData.text
                            textFormat: Text.PlainText
                            color: tabButton.current ? theme.text : theme.dimText
                            font.weight: tabButton.current ? Font.DemiBold : Font.Normal
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TpCountBadge {  // items of the view (laps, incidents...): never glued to the text
                            visible: tabButton.count >= 0
                            size: "sm"
                            tone: tabButton.current ? "accent" : "neutral"
                            text: tabButton.count
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }
        Item { Layout.fillWidth: true }
        RowLayout {
            id: trailingRow
            spacing: theme.space3
        }
    }
    Item {  // underline: slides to current tab
        Layout.fillWidth: true
        implicitHeight: 2
        Rectangle { anchors.fill: parent; color: theme.strokeSubtle }
        Rectangle {
            // count read: itemAt alone is never evaluated again once tab buttons are made (null at start)
            readonly property Item target: tabRepeater.count > bar.currentIndex ? tabRepeater.itemAt(bar.currentIndex) : null
            x: target ? target.x : 0
            width: target ? target.width : 0
            height: 2
            radius: 1
            color: theme.accent
            Behavior on x { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
            Behavior on width { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
        }
    }
}
