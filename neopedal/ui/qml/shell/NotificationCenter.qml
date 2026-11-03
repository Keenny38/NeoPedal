import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Notification center (popup of the bell in the navigation rail): modes on ("Now"), then messages of the app,
// newest first, in groups by day, filtered by level & searched, with level (icon, color & word), time, repeat count,
// actions (View Log, Create Bug Report, What's New...), Don't Show Again (warnings & errors), Copy & Remove. Clear
// All can be undone while it is open. A message is marked read once clicked, the messages shown once it closes.
// Settings button: Settings > Notification. Esc closes it.
TpPage {
    id: page
    color: theme.surfaceFlyout  // popup window: native drop shadow of Windows popups around it
    border.width: 1
    border.color: theme.strokeSubtle
    // Corners of the popups of pages (Windows 11 rounds the window the same, ShellPopup); content fades in.
    // Square when the system keeps a square window (Windows 10): rounded corners would show the view background
    radius: theme.radiusLg * (backend.roundedCorners ? 1 : 0)
    focus: true
    Keys.onEscapePressed: backend.close()

    function severityLabel(severity) {
        return severity === "error" ? i18n.tr("Error") : severity === "warning" ? i18n.tr("Warning") : i18n.tr("Info")
    }
    function severityColor(severity) {
        return severity === "error" ? theme.loss : severity === "warning" ? theme.warning : theme.info
    }

    TpEnter { target: popupContent }
    ColumnLayout {
        id: popupContent
        anchors.fill: parent
        anchors.margins: theme.padCard
        spacing: theme.space3

        TpCardHeader {
            level: "popup"
            glyph: ""  // bell
            title: i18n.tr("Notifications")
            count: backend.entryCount > 0 ? "" + backend.entryCount : ""
            TpButton {
                flat: true
                size: "sm"
                glyph: theme.glyphs.settings
                fallback: "⚙"
                tip: i18n.tr("Notification Settings")
                onClicked: backend.openSettings()
            }
            TpButton {
                visible: backend.entryCount > 0
                flat: true
                size: "sm"
                text: i18n.tr("Clear All")
                onClicked: backend.clearAll()
            }
            closable: true
            closeTip: i18n.tr("Close") + " (Esc)"
            onClosed: backend.close()
        }

        // Modes on
        TpSectionLabel {
            Layout.fillWidth: true
            visible: backend.active.length > 0
            text: i18n.tr("Now")
        }
        Repeater {
            model: backend.active
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: theme.space3
                Icon { glyph: ""; fallback: "i"; color: theme.info; size: theme.iconSm }  // info
                TpText {
                    Layout.fillWidth: true
                    text: modelData.text
                    textFormat: Text.PlainText
                    color: theme.text
                    elide: Text.ElideRight
                }
                TpButton {
                    visible: modelData.key !== ""
                    size: "sm"
                    flat: true
                    text: i18n.tr("Open")
                    onClicked: backend.runAction(modelData.key)
                }
            }
        }

        TpSectionLabel {
            Layout.fillWidth: true
            Layout.topMargin: backend.active.length > 0 ? theme.space3 : 0
            visible: backend.entryCount > 0
            text: i18n.tr("Messages")
        }
        // Level filter: shown when messages have more than one level
        Flow {
            Layout.fillWidth: true
            visible: [backend.counts.error, backend.counts.warning, backend.counts.info].filter(count => count > 0).length > 1
            spacing: theme.space2
            Repeater {
                model: ["", "error", "warning", "info"]  // "": every message
                TpChip {
                    required property string modelData
                    visible: modelData === "" || count > 0
                    size: "sm"
                    text: modelData === "" ? i18n.tr("All") : modelData === "error" ? i18n.tr("Errors")
                        : modelData === "warning" ? i18n.tr("Warnings") : i18n.tr("Info")
                    count: modelData === "" ? backend.entryCount : (backend.counts[modelData] || 0)
                    showDot: modelData !== ""
                    dotColor: modelData !== "" ? page.severityColor(modelData) : "transparent"
                    selected: backend.filter === modelData
                    onClicked: backend.setFilter(modelData)
                }
            }
        }
        TpSearchField {
            Layout.fillWidth: true
            visible: backend.entryCount > 6 || backend.search !== ""
            placeholderText: i18n.tr("Search messages")
            onSearchChanged: function(text) { backend.setSearch(text) }
            onExitField: page.forceActiveFocus()
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: count > 0
            clip: true
            spacing: theme.space2
            model: backend.messages  // synced in place: a new message inserts one row, a read mark changes one
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            section.property: "day"  // Today, Yesterday, date
            section.delegate: TpSectionLabel {
                required property string section
                width: list.width
                topPadding: theme.space2
                text: section
            }
            delegate: TpListRow {  // unread: tinted in its level color
                id: row
                required property int entryId
                required property string text
                required property string severity
                required property int count
                required property string time
                required property string day
                required property bool read
                required property var actions
                width: list.width
                implicitHeight: rowContent.implicitHeight + theme.padCard * 2
                card: true
                emphasized: !read
                tint: page.severityColor(severity)
                Accessible.role: Accessible.StaticText
                Accessible.name: page.severityLabel(severity) + ", " + day + " " + time + ": " + text
                TapHandler { enabled: !row.read; onTapped: backend.markRead(row.entryId) }  // seen

                ColumnLayout {
                    id: rowContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: theme.padCard
                    spacing: theme.space2
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: theme.space3
                        Icon {
                            glyph: row.severity === "info" ? "" : ""  // info, warning
                            fallback: row.severity === "info" ? "i" : "!"
                            color: page.severityColor(row.severity)
                            size: theme.iconSm
                        }
                        TpText {
                            role: "label"
                            font.weight: Font.DemiBold
                            text: page.severityLabel(row.severity)
                        }
                        TpText {
                            Layout.fillWidth: true
                            role: "caption"
                            tabular: true
                            color: theme.dimOn(row.color)
                            text: row.time + (row.count > 1 ? "  ×" + row.count : "")
                        }
                        TpButton {
                            flat: true
                            size: "xs"
                            glyph: theme.glyphs.copy
                            fallback: "⧉"
                            tip: i18n.tr("Copy")
                            onClicked: backend.copyText(row.entryId)
                        }
                        TpButton {
                            flat: true
                            size: "xs"
                            glyph: theme.glyphs.remove
                            fallback: "✕"
                            tip: i18n.tr("Remove")
                            onClicked: backend.remove(row.entryId)
                        }
                    }
                    TpText {
                        Layout.fillWidth: true
                        text: row.text
                        wrapMode: Text.Wrap
                        elide: Text.ElideNone
                    }
                    Flow {
                        Layout.fillWidth: true
                        visible: row.actions.length > 0 || row.severity !== "info"
                        spacing: theme.space3
                        Repeater {
                            model: row.actions
                            TpButton {
                                required property var modelData
                                size: "sm"
                                text: modelData.label
                                onClicked: backend.runAction(modelData.key)
                            }
                        }
                        TpButton {  // same message (any numbers) only logged from now on
                            visible: row.severity !== "info"
                            flat: true
                            size: "sm"
                            text: i18n.tr("Don't Show Again")
                            onClicked: backend.mute(row.entryId)
                        }
                    }
                }
            }
        }
        TpText {  // search or level filter leaves none
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: backend.entryCount > 0 && list.count === 0
            role: "caption"
            horizontalAlignment: Text.AlignHCenter
            text: i18n.tr("No message found")
        }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: backend.entryCount === 0
            TpStateView {
                anchors.centerIn: parent
                empty: true
                compact: true
                glyph: ""  // bell
                title: i18n.tr("No notifications")
                text: i18n.tr("Errors of background tasks, saving problems, updates found and race reminders are kept here.")
                actionText: backend.canUndoClear ? i18n.tr("Undo") : ""
                onAction: backend.undoClear()
            }
        }
        TpButton {
            Layout.alignment: Qt.AlignHCenter
            visible: backend.mutedCount > 0
            flat: true
            size: "sm"
            text: i18n.tr("Show Muted Messages Again (%1)").arg(backend.mutedCount)
            onClicked: backend.unmuteAll()
        }
    }
}
