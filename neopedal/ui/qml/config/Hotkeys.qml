import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Hotkeys category of the Settings page (hotkeyBackend: quick/hotkey_backend.py): global hotkey switch, key bindings by section (General, Spectate, Broadcast Director, Preset,
// Overlays, Module: folded with a click), search & "assigned only" filter, actions sharing a key marked. A key
// button opens the capture dialog (keyboard, mouse & game controller buttons). Clearing (a row or all) is undone
// from the toast. Keys: type to search, Ctrl+F or "/" search, arrows move, Enter / Space capture (header: fold),
// Delete clears, Ctrl+Z undoes the last clear.
TpPage {
    id: page

    readonly property bool compact: width < theme.bpCompact

    function focusSearch() {
        search.forceActiveFocus()
        search.selectAll()
    }
    function openCapture(name) {
        hotkeyBackend.startCapture(name)
        if (hotkeyBackend.captureKey === name)
            capture.open()
    }
    function activate(item) {
        if (!item)
            return
        if (item.header)
            hotkeyBackend.toggleSection(item.section)
        else
            page.openCapture(item.key)
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_F && (event.modifiers & Qt.ControlModifier)) {
            page.focusSearch()
            event.accepted = true
        } else if (event.key === Qt.Key_Z && (event.modifiers & Qt.ControlModifier) && hotkeyBackend.canUndo) {
            hotkeyBackend.undo()
            event.accepted = true
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: theme.padPage
        spacing: theme.space4

        // Title & global hotkey switch
        TpPageHeader {
            title: i18n.tr("Hotkeys")
            count: i18n.trm(hotkeyBackend.assignedCount + " / " + hotkeyBackend.totalCount + " assigned")
            countActive: hotkeyBackend.assignedCount > 0
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: theme.dimText
            lineHeight: 1.1
            text: i18n.tr("Keys, mouse buttons and game controller buttons (wheel, button box) that run an action, also while the game has focus.")
        }

        TpNotice {
            Layout.fillWidth: true
            visible: hotkeyBackend.conflictCount > 0
            text: i18n.trm(hotkeyBackend.conflictCount + " actions share a key with another action")
        }

        // Search, filter & clear all
        // One row (a Flow sizing the search from its own width looped forever inside the Settings page)
        RowLayout {
            Layout.fillWidth: true
            spacing: theme.space3
            TpSearchField {
                id: search
                Layout.fillWidth: true
                Layout.minimumWidth: theme.em * 8
                placeholderText: i18n.tr("Search hotkeys") + "   Ctrl+F"
                onSearchChanged: function(text) { hotkeyBackend.setSearch(text) }
                onExitField: list.forceActiveFocus()
                Keys.onReturnPressed: list.forceActiveFocus()
                Keys.onEnterPressed: list.forceActiveFocus()
            }
            TpChip {
                id: filterChip
                text: i18n.tr("Assigned only")
                count: hotkeyBackend.assignedCount
                selected: hotkeyBackend.assignedOnly
                multi: true
                tip: i18n.tr("Show only actions with a key")
                onClicked: hotkeyBackend.setAssignedOnly(!hotkeyBackend.assignedOnly)
            }
            TpButton {
                id: clearAll
                flat: true
                glyph: theme.glyphs.remove
                text: page.compact ? "" : i18n.tr("Clear All")  // narrow page: icon, name in tooltip
                tip: i18n.tr("Clear every key binding (undo from the notice)")
                enabled: hotkeyBackend.assignedCount > 0
                onClicked: hotkeyBackend.clearAll()
            }
        }

        // Bindings
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: list
                objectName: "hotkeyList"
                anchors.fill: parent
                clip: true
                model: hotkeyBackend.rows
                boundsBehavior: Flickable.StopAtBounds
                highlightFollowsCurrentItem: false
                keyNavigationEnabled: true
                activeFocusOnTab: true
                reuseItems: true
                cacheBuffer: Math.round(theme.em * 30)
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: HotkeyRow {
                    id: rowItem
                    width: ListView.view.width - (list.ScrollBar.vertical.visible ? list.ScrollBar.vertical.width : 0)
                    current: ListView.isCurrentItem
                    editable: true
                    onToggleRequested: { list.currentIndex = rowItem.index; hotkeyBackend.toggleSection(rowItem.section) }
                    onCaptureRequested: { list.currentIndex = rowItem.index; page.openCapture(rowItem.key) }
                    onClearRequested: hotkeyBackend.clear(rowItem.key)
                }

                Keys.onReturnPressed: page.activate(currentItem)
                Keys.onEnterPressed: page.activate(currentItem)
                Keys.onSpacePressed: page.activate(currentItem)
                Keys.onDeletePressed: if (currentItem && !currentItem.header) hotkeyBackend.clear(currentItem.key)
                Keys.onPressed: function(event) {
                    if (search.routeTyped(event))  // type to search, "/" search
                        event.accepted = true
                }
                onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0
            }

            TpStateView {
                anchors.centerIn: parent
                empty: list.count === 0
                glyph: ""  // search
                title: i18n.tr("No hotkey matches the search")
                actionText: i18n.tr("Clear Filters")
                onAction: { hotkeyBackend.clearFilters(); search.clearSearch(); page.focusSearch() }
            }
        }

        Text {
            Layout.fillWidth: true
            elide: Text.ElideRight
            color: theme.dimText
            font.features: { "tnum": 1 }
            text: hotkeyBackend.filtered
                ? i18n.trm(hotkeyBackend.shownCount + " of " + hotkeyBackend.totalCount + " hotkeys shown")
                : i18n.trm(hotkeyBackend.totalCount + " hotkeys")
            textFormat: Text.PlainText
        }
    }

    HotkeyCaptureDialog {
        id: capture
        onClosed: list.forceActiveFocus()  // popups give focus back to the window
    }

    Connections {
        target: hotkeyBackend
        function onFilterChanged() {
            if (search.text !== hotkeyBackend.searchText)
                search.text = hotkeyBackend.searchText
        }
        function onCaptureChanged() {
            if (hotkeyBackend.captureKey === "" && capture.opened)
                capture.close()  // capture ended by the page (closed, released)
        }
    }

}
