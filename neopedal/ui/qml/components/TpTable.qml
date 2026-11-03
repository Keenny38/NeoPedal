import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Table of a page: column titles over a list of rows, one look & keyboard model for every table (from the tracks
// table of Driver Stats). The page keeps its columns & cells: header cells (TpHeaderCell, numbers aligned right as
// their cells) are the children, rows come from delegate (a row of rowWidth, TpListRow under its cells).
// - Wider than the page (rowWidth > width): scrolls sideways, titles with the rows; titles stay on top.
// - One Tab stop: Up / Down, Page Up / Page Down, Home / End pick a row (picked), Enter activates it (activated).
// - Rows reach the ListView as table.list (currentIndex, activeFocus for the focus ring of the current row).
//   TpTable {
//       model: backend.rows; rowWidth: pad * 2 + columnsWidth; name: i18n.tr("Classification")
//       TpHeaderCell { width: wPos; text: i18n.tr("Pos") }  TpHeaderCell { width: wLaps; text: ...; align: Qt.AlignRight }
//       delegate: Item { width: table.rowWidth; height: theme.row; TpListRow { ... } Row { ...cells } }
//       onPicked: function(index) { backend.select(index) }
//   }
Item {
    id: table
    property alias model: list.model
    property alias delegate: list.delegate
    property alias reuseItems: list.reuseItems
    property alias listName: list.objectName
    // Row transitions of the page (rows sorted in place, other rows shown): new rows fade in by default
    property alias move: list.move
    property alias moveDisplaced: list.moveDisplaced
    property alias displaced: list.displaced
    property alias populate: list.populate
    readonly property alias list: list
    property real rowWidth: width - scrollWidth  // every column: wider than the table, the table scrolls sideways
    property real pad: theme.space4  // room before the first column (titles & cells)
    property string name: ""  // for screen readers
    property bool divider: true  // line under the titles
    property bool currentOnFocus: false  // first row made current when the table gets focus (nothing picked)
    default property alias headerCells: headerRow.data
    // Width the columns may use (column filling the room: page width minus margins & vertical scroll bar)
    readonly property real availableWidth: width - pad * 2 - scrollWidth
    readonly property real scrollWidth: list.ScrollBar.vertical.visible ? list.ScrollBar.vertical.width : 0
    signal picked(int index)  // row picked with the keyboard
    signal activated(int index)  // Enter on the current row

    function pick(index) {
        if (list.count === 0)
            return
        var next = Math.max(0, Math.min(list.count - 1, index))
        list.currentIndex = next
        list.positionViewAtIndex(next, ListView.Contain)
        picked(next)
    }

    Flickable {  // wide table scrolls sideways on narrow pages
        id: scroll
        anchors.fill: parent
        contentWidth: Math.max(width, table.rowWidth + table.scrollWidth)
        contentHeight: height
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.HorizontalFlick
        interactive: contentWidth > width
        clip: true
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            width: scroll.contentWidth
            height: scroll.height
            spacing: 0

            // Column titles
            Row {
                id: headerRow
                Layout.leftMargin: table.pad
                Layout.topMargin: theme.space4
                Layout.bottomMargin: theme.space2
            }
            Rectangle { visible: table.divider; Layout.fillWidth: true; implicitHeight: 1; color: theme.strokeSubtle }

            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                reuseItems: true  // rows scrolled out fed again (delegates reset their state: ListView.onPooled)
                boundsBehavior: Flickable.StopAtBounds
                activeFocusOnTab: count > 0 || activeFocus
                currentIndex: -1
                onActiveFocusChanged: if (activeFocus && table.currentOnFocus && currentIndex < 0 && count > 0) currentIndex = 0
                highlightFollowsCurrentItem: false
                Accessible.role: Accessible.Table
                Accessible.name: table.name
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionBase } }
                readonly property int pageRows: Math.max(1, Math.floor(height / Math.max(theme.row, 1)) - 1)
                Keys.onUpPressed: table.pick(currentIndex - 1)
                Keys.onDownPressed: table.pick(currentIndex + 1)
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Home) table.pick(0)
                    else if (event.key === Qt.Key_End) table.pick(count - 1)
                    else if (event.key === Qt.Key_PageUp) table.pick(currentIndex - pageRows)
                    else if (event.key === Qt.Key_PageDown) table.pick(currentIndex + pageRows)
                    else return
                    event.accepted = true
                }
                Keys.onReturnPressed: if (currentIndex >= 0) table.activated(currentIndex)
                Keys.onEnterPressed: if (currentIndex >= 0) table.activated(currentIndex)
            }
        }
    }
}
