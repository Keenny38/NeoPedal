import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import "schedule.js" as Js

// Upcoming Races: daily online races of Le Mans Ultimate to come, read from the public RaceControl site (no sign in,
// no game ticket), by tier: cards, compact list or timeline of the next hours. Each race: next start & time to it
// (pulses just before), track, your personal best & level of each class driven there, length, track or cars not
// owned, reminder set. A race opens a menu: register in the game, driver stats, recorded laps, race calculator,
// reminder, calendar export. Filters: search, owned tracks only.
TpPage {
    id: page

    readonly property var status: backend.status
    readonly property int columns: width >= theme.bpWide ? 3 : width >= theme.bpCompact ? 2 : 1
    readonly property bool filtered: backend.search !== "" || backend.ownedOnly
    property string menuKey: ""
    property real menuStart: 0  // start of the timeline block clicked (0: card or list, the race's next start)

    // Menu of a race: below the button, or at a point of the card or row clicked (below its title line)
    // (entries made when it opens: a click while it fades out opens it once closed, with entries of then)
    // Another tile of the same list while it is open: moved there at once (area: the list holding the tiles)
    function openMenu(key, button, start, at) {
        page.menuKey = key
        page.menuStart = start || 0
        var area = button
        while (area && area.objectName !== "racePane" && area.objectName !== "raceTimeline")
            area = area.parent
        if (area && area.objectName === "racePane")
            area = area.contentItem
        var point = at === undefined ? Qt.point(0, button.height + theme.space1) : at
        raceMenu.toggleAt(button, point.x, point.y, area || null)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: theme.padPage
        spacing: theme.space3

        TpPageHeader {
            Layout.fillWidth: true
            title: i18n.tr("Upcoming Races")
            subtitle: page.status.age ? i18n.tr("Last read: %1").replace("%1", page.status.age) : ""
            TpSpinner {
                visible: page.status.loading === true
                Layout.alignment: Qt.AlignVCenter
            }
            TpButton {
                objectName: "requestsButton"
                size: "sm"
                text: i18n.tr("Requests")
                tip: i18n.tr("Requests sent to GitHub, the lap times sheet and the public RaceControl site since the app started")
                onClicked: {
                    requestsDialog.report = backend.requestsReport()
                    requestsDialog.open()
                }
            }
            TpButton {
                objectName: "readAgain"
                size: "sm"
                glyph: theme.glyphs.refresh
                fallback: "↻"
                text: i18n.tr("Read Again")
                shortcut: "F5"
                enabled: page.status.loading !== true && page.status.off !== true
                onClicked: backend.readAgain()
            }
        }

        TpNotice {
            objectName: "statusNotice"
            Layout.fillWidth: true
            visible: (page.status.note || "") !== ""
            text: page.status.note || ""
            tone: page.status.level === "warning" ? theme.warning : theme.accent
            glyph: page.status.level === "warning" ? "" : ""  // warning, info
            fallback: page.status.level === "warning" ? "!" : "i"
            actionText: page.status.off === true ? i18n.tr("Open Option") : ""
            onAction: backend.openOnlineOption()
        }

        // Filters: search, view, owned tracks only
        Flow {
            objectName: "filters"
            Layout.fillWidth: true
            spacing: theme.space2
            TpSearchField {
                id: raceSearch
                objectName: "raceSearch"
                width: theme.em * 15  // French placeholder whole
                placeholderText: i18n.tr("Search races…")
                onSearchChanged: function(text) { backend.setSearch(text) }
                Connections {
                    target: backend
                    function onFiltersCleared() { if (raceSearch.text !== "") raceSearch.clearSearch() }
                }
            }
            TpSegmented {
                objectName: "viewMode"
                name: i18n.tr("View")
                options: [{ glyph: "", text: "", tip: i18n.tr("Cards") },
                          { glyph: "", text: "", tip: i18n.tr("List") },
                          { glyph: "", text: "", tip: i18n.tr("Timeline") }]
                currentIndex: backend.view
                onActivated: function(index) { backend.setView(index) }
            }
            TpSegmented {
                objectName: "timelineHours"
                visible: backend.view === 2
                name: i18n.tr("Hours shown")
                options: ["3 h", "6 h", "12 h"]
                currentIndex: [3, 6, 12].indexOf(backend.timelineHours)
                onActivated: function(index) { backend.setTimelineHours([3, 6, 12][index]) }
            }
            TpChip {
                objectName: "ownedOnly"
                text: i18n.tr("Owned Cars & Tracks")
                selected: backend.ownedOnly
                multi: true
                tip: i18n.tr("Hide races and servers needing a car or a track you don't own")
                onClicked: backend.setOwnedOnly(!backend.ownedOnly)
            }
            TpButton {
                visible: page.filtered
                flat: true
                size: "sm"
                text: i18n.tr("Clear Filters")
                onClicked: backend.clearFilters()
            }
        }

        // Daily races: timeline of the next hours, or one section per tier
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ScrollPane {  // timeline view too while no race is shown: its empty, filtered or loading state
                anchors.fill: parent
                visible: backend.view !== 2 || empty
                empty: backend.count === 0
                emptyTitle: i18n.tr("No daily race to come")
                filtered: page.filtered
                    Repeater {
                        model: backend.dailyModel  // rows updated in place: cards kept (clicks, open menu)
                        ColumnLayout {
                            id: tierGroup
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: theme.space3
                            RowLayout {
                                spacing: theme.space3
                                TpSectionLabel { text: tierGroup.modelData.tierText }
                                TpText {
                                    role: "caption"
                                    visible: text !== ""
                                    text: tierGroup.modelData.frequency
                                }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                visible: backend.view === 0
                                columns: page.columns
                                columnSpacing: theme.space4
                                rowSpacing: theme.space4
                                uniformCellWidths: true
                                Repeater {
                                    model: backend.view === 0 ? backend.raceModel(tierGroup.modelData.tier) : null
                                    EventCard { onMenuRequested: function(key, card, at) { page.openMenu(key, card, 0, at) } }
                                }
                                Filler { cards: tierGroup.modelData.count; columns: page.columns }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                visible: backend.view === 1
                                spacing: theme.space1
                                Repeater {
                                    model: backend.view === 1 ? backend.raceModel(tierGroup.modelData.tier) : null
                                    EventRow { onMenuRequested: function(key, row, at) { page.openMenu(key, row, 0, at) } }
                                }
                            }
                        }
                    }
                }
                MouseArea {  // press beside the blocks (under the timeline): menu closed
                    anchors.fill: parent
                    visible: backend.view === 2
                    onPressed: function(mouse) {
                        raceMenu.close()
                        mouse.accepted = false
                    }
                }
            Timeline {
                objectName: "raceTimeline"
                anchors.fill: parent
                visible: backend.view === 2 && backend.count > 0
                data_: backend.timeline
                lanes: backend.timelineModel
                onMenuRequested: function(key, button, start) { page.openMenu(key, button, start) }
            }
        }
    }

    // Requests sent to online services since the app started (journal in memory, nothing saved)
    TpDialog {
        id: requestsDialog
        objectName: "requestsDialog"
        parent: page.Overlay.overlay
        property var report: []
        title: i18n.tr("Requests")
        acceptText: i18n.tr("Close")
        showCancel: false
        width: Math.min(parent ? parent.width - theme.em * 2 : theme.em * 40, theme.em * 40)
        TpText {
            Layout.fillWidth: true
            visible: requestsDialog.report.length === 0
            role: "caption"
            wrap: true
            text: i18n.tr("Nothing sent since the app started.")
        }
        Repeater {
            model: requestsDialog.report
            ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: theme.space1
                TpSectionLabel { text: modelData.name + " · " + modelData.summary }
                Repeater {
                    model: modelData.lines
                    TpText {
                        required property var modelData
                        Layout.fillWidth: true
                        role: "caption"
                        elide: Text.ElideRight
                        text: modelData.when + "  " + modelData.text
                    }
                }
            }
        }
    }

    // Menu of a race, championship or co-op event (entries made by the backend when opened): a separator between
    // two sections, entries of a same "menu" in one submenu (its row shows the checked entry, as the reminder set)
    TpMenu {
        id: raceMenu
        objectName: "raceMenu"
        // Row of a submenu made by the menu (not destroyable from QML): removed with its submenu
        function clear(menu) {
            while (menu.count > 0) {
                var sub = menu.itemAt(0).subMenu
                if (sub) {
                    clear(sub)
                    menu.removeMenu(sub)
                } else {
                    menu.takeItem(0).destroy()
                }
            }
        }
        onOpening: fill(backend.raceActions(page.menuKey, page.menuStart))
        // Entries made in the page (an item: placed in the scene, owned until destroyed here), moved into the menu
        function fill(entries) {
            clear(raceMenu)
            var section = null
            var sub = null
            for (var i = 0; i < entries.length; ++i) {
                var entry = entries[i]
                if (section !== null && entry.section !== section)
                    addItem(raceMenuSeparator.createObject(page))
                section = entry.section
                if (!entry.menu) {
                    sub = null
                    addItem(raceMenuEntry.createObject(page, { entry: entry }))
                    continue
                }
                if (sub === null || sub.title !== entry.menu) {
                    sub = raceSubMenu.createObject(raceMenu, { title: entry.menu })
                    addMenu(sub)
                    sub.row = itemAt(count - 1)
                    sub.row.enabled = false  // enabled by its first enabled entry
                }
                sub.addItem(raceMenuEntry.createObject(page, { entry: entry }))
                if (entry.enabled)
                    sub.row.enabled = true
                if (entry.checked === true)
                    sub.row.shortcut = entry.text
            }
        }
    }
    Component {
        id: raceMenuEntry
        TpMenuItem {
            property var entry: ({})
            objectName: "raceMenuEntry"
            text: entry.text || ""
            enabled: entry.enabled === true
            checkable: entry.checked !== undefined
            checked: entry.checked === true
            onTriggered: {
                backend.runRaceAction(page.menuKey, entry.id, entry.vehicle, page.menuStart)
            }
        }
    }
    Component { id: raceMenuSeparator; MenuSeparator {} }
    Component { id: raceSubMenu; TpMenu { property Item row: null } }

    // Scrolling list of a tab, its empty or loading state in the middle
    component ScrollPane: Flickable {
        id: pane
        objectName: "racePane"  // menu of its tiles placed in its content (see openMenu)
        property bool empty: false
        property bool filtered: false
        property string emptyTitle: ""
        property alias spacing: paneColumn.spacing
        default property alias content: paneColumn.data
        contentWidth: width
        contentHeight: paneColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        MouseArea {  // press beside the tiles (under them): menu closed (a press on a tile keeps it, moved there)
            width: pane.contentWidth
            height: Math.max(pane.contentHeight, pane.height)  // empty room below the tiles too
            onPressed: function(mouse) {
                raceMenu.close()
                mouse.accepted = false
            }
        }
        ColumnLayout {
            id: paneColumn
            width: pane.width - theme.space3  // room for the scroll bar
            spacing: theme.space5
        }
        TpStateView {
            parent: pane  // centered in the shown room (content of an empty pane has no height: half cut off)
            anchors.centerIn: parent
            visible: pane.empty
            loading: backend.status.loading === true && backend.status.read !== true
            empty: pane.empty
            glyph: ""  // calendar
            title: pane.emptyTitle
            text: pane.filtered ? i18n.tr("No race matches the filters.")
                  : (backend.status.note || "") !== "" ? "" : i18n.tr("Races are read from RaceControl while Le Mans Ultimate runs.")
            actionText: pane.filtered ? i18n.tr("Clear Filters") : ""
            onAction: backend.clearFilters()
            loadingText: i18n.tr("Reading races…")
        }
    }

    // Empty cells after the cards of a grid holding less than a row: cards keep the width of a cell
    component Filler: Repeater {
        property int cards: 0
        property int columns: 1
        model: cards > 0 && cards < columns ? columns - cards : 0
        Item { Layout.fillWidth: true }
    }

    // Time to a start: accent when close, pulses just before, green dot while running
    component UntilPill: Pill {
        property var race: ({})
        visible: (race.until || "") !== ""
        text: race.until || ""
        dot: race.running === true || race.imminent === true
        pulsing: race.running === true || race.imminent === true
        tint: race.running === true ? theme.gain : race.soon === true ? theme.accent : theme.dimText
    }

    // Your personal best & community level of each class driven on the track ("Never driven here" else)
    component PersonalBests: Flow {
        id: bestsFlow
        property var personal: ({})
        readonly property var bests: personal.bests || []
        visible: personal.known !== undefined
        spacing: theme.space3
        TpText {
            visible: bestsFlow.bests.length === 0
            role: "caption"
            text: i18n.tr("Never driven here")
        }
        Repeater {
            model: bestsFlow.bests
            Item {
                id: bestItem
                required property var modelData
                implicitWidth: bestRow.implicitWidth
                implicitHeight: bestRow.implicitHeight
                ToolTip.visible: bestArea.containsMouse
                ToolTip.text: i18n.tr("Your personal best") + " · " + modelData.vehicle
                              + (modelData.level !== "" ? " · " + modelData.level : "")
                RowLayout {
                    id: bestRow
                    spacing: theme.space1
                    TpText { role: "caption"; text: bestItem.modelData.vehicleClass }
                    TpText { role: "numeric"; font.weight: Font.DemiBold; text: bestItem.modelData.best }
                    Pill {
                        visible: bestItem.modelData.letter !== ""
                        size: "sm"
                        text: bestItem.modelData.letter
                        tint: bestItem.modelData.color || theme.dimText
                    }
                }
                MouseArea { id: bestArea; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
            }
        }
    }

    // Fact of a race with its icon (sessions, weather, settings), hidden when unknown
    component FactLine: RowLayout {
        id: fact
        property string glyph: ""
        property string text: ""
        visible: fact.text !== ""
        Layout.fillWidth: true
        spacing: theme.space2
        Icon {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: theme.iconMd
            glyph: fact.glyph
            size: theme.iconSm
            color: theme.dimText
        }
        TpText { Layout.fillWidth: true; role: "caption"; wrap: true; text: fact.text }
    }

    // Daily, weekly or special race; a click opens its menu below the title (no menu button: same menu)
    component EventCard: TpSectionCard {
        id: card
        required property var modelData
        property bool showTier: false
        readonly property var race: modelData
        // every following start shown (kept by the backend: cards are made again at each list update)
        readonly property bool expanded: backend.expandedStarts.indexOf(card.race.key) >= 0
        signal menuRequested(string key, Item card, point at)
        objectName: "raceCard"
        fillContent: false
        Layout.fillWidth: true
        Layout.fillHeight: true
        eyebrow: card.showTier ? card.race.tierText : ""
        title: card.race.title
        tip: i18n.tr("Register in the game, driver stats, recorded laps, race calculator, reminder & calendar")
        clickable: true
        onOpened: card.menuRequested(card.race.key, card, Qt.point(card.pad, card.bodyY - theme.space2))
        trailing: [GameLogo { source: card.race.trackLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 2.4 }]
        RowLayout {  // next start, time to it, reminder set
            Layout.fillWidth: true
            spacing: theme.space3
            TpText { role: "display"; tabular: true; text: card.race.start }
            UntilPill { race: card.race }
            Pill {
                visible: card.race.reminder > 0
                size: "sm"
                glyph: "\uEA8F"  // bell
                fallback: "!"
                text: i18n.tr("%1 min").replace("%1", card.race.reminder)
                tint: theme.accent
                tip: i18n.tr("Reminder set")
            }
            Item { Layout.fillWidth: true }
        }
        TpText { Layout.fillWidth: true; role: "subtitle"; text: card.race.track }
        PersonalBests { Layout.fillWidth: true; personal: card.race.personal || {} }
        Rectangle {  // facts of the race below
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: theme.space1
            color: theme.border
        }
        FactLine { glyph: "\uE916"; text: Js.joined([card.race.sessions, card.race.trackTime]) }  // stopwatch
        FactLine { glyph: card.race.wet === true ? "\uEB42" : "\uE706"; text: card.race.weather }  // water drop, sun
        Pill {  // track or cars you don't own
            visible: card.race.owned !== ""
            size: "sm"
            text: card.race.owned
            glyph: ""  // warning
            fallback: "!"
            tint: theme.warning
        }
        Flow {  // following starts: the first ones, all of them once expanded
            Layout.fillWidth: true
            visible: card.race.later.length > 0
            spacing: theme.space2
            TpText { role: "caption"; text: i18n.tr("Then") }
            Repeater {
                model: card.expanded ? card.race.later : card.race.laterFirst
                TpText { required property var modelData; role: "caption"; tabular: true; text: modelData }
            }
            TpButton {
                objectName: "moreStarts"
                visible: card.race.later.length > Js.LATER
                flat: true
                size: "xs"
                text: card.expanded ? i18n.tr("Fewer") : i18n.tr("+%1 more").replace("%1", card.race.later.length - Js.LATER)
                onClicked: backend.setStartsExpanded(card.race.key, !card.expanded)
                Accessible.description: card.expanded ? i18n.tr("Expanded") : i18n.tr("Collapsed")
            }
        }
    }

    // Race of the compact list: start, time to it, title, track, classes, your best, requirement; a click opens its
    // menu below the line
    component EventRow: Item {
        id: raceRow
        required property var modelData
        required property int index
        property bool showTier: false
        readonly property var race: modelData
        signal menuRequested(string key, Item row, point at)
        objectName: "raceRow"
        Layout.fillWidth: true
        readonly property real lineHeight: Math.max(theme.rowTall, rowContent.implicitHeight + theme.space2 * 2)
        implicitHeight: lineHeight
        TpListRow {
            anchors.fill: parent
            striped: raceRow.index % 2 === 1
            hovered: rowArea.containsMouse
            emphasized: raceRow.race.reminder > 0
        }
        ToolTip.visible: rowArea.containsMouse
        ToolTip.text: i18n.tr("Register in the game, driver stats, recorded laps, race calculator, reminder & calendar")
        ToolTip.delay: theme.tipDelay
        MouseArea {
            id: rowArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: raceRow.menuRequested(raceRow.race.key, raceRow, Qt.point(theme.space3, raceRow.lineHeight + theme.space1))
        }
        RowLayout {
            id: rowContent
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: theme.space3
            anchors.rightMargin: theme.space2
            height: raceRow.lineHeight
            spacing: theme.space3
            TpText {
                role: "numeric"
                font.weight: Font.DemiBold
                text: raceRow.race.start
                Layout.preferredWidth: theme.em * 6
            }
            UntilPill { race: raceRow.race; Layout.preferredWidth: theme.em * 5.5 }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                TpText {
                    Layout.fillWidth: true
                    font.weight: Font.DemiBold
                    text: raceRow.showTier ? Js.joined([raceRow.race.tierText, raceRow.race.title]) : raceRow.race.title
                }
                TpText {
                    Layout.fillWidth: true
                    role: "caption"
                    text: Js.joined([raceRow.race.track, raceRow.race.length, raceRow.race.owned])
                }
            }
            TpText {
                role: "numeric"
                visible: text !== ""
                text: Js.bestText(raceRow.race.personal)
            }
        }
    }

    // Next hours of the daily races: one lane per race under its tier, a block per start (width: its length)
    component Timeline: ColumnLayout {
        id: line
        property var data_: ({})
        property var lanes: null  // model of the lanes (kept while time goes by: blocks placed from data_.now)
        readonly property real now: data_.now || 0
        readonly property real period: data_.period || 1
        signal menuRequested(string key, Item button, real start)
        readonly property real labelWidth: theme.em * 12
        spacing: theme.space1
        Item {  // hour marks
            id: marks
            Layout.fillWidth: true
            implicitHeight: theme.em * 1.4
            Repeater {
                model: line.data_.marks || []
                TpText {
                    required property var modelData
                    role: "caption"
                    tabular: true
                    text: modelData.text
                    x: line.labelWidth + modelData.at * (marks.width - line.labelWidth)
                }
            }
        }
        Repeater {
            model: line.lanes
            ColumnLayout {
                id: lane
                required property var modelData
                Layout.fillWidth: true
                spacing: theme.space1
                TpSectionLabel {
                    visible: lane.modelData.tierText !== ""
                    Layout.topMargin: theme.space2
                    text: lane.modelData.tierText
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: theme.space2
                    ColumnLayout {
                        Layout.preferredWidth: line.labelWidth - theme.space2
                        Layout.maximumWidth: line.labelWidth - theme.space2
                        spacing: 0
                        TpText { Layout.fillWidth: true; font.weight: Font.DemiBold; text: lane.modelData.title }
                        TpText { Layout.fillWidth: true; role: "caption"; text: lane.modelData.track }
                    }
                    Item {
                        id: laneTrack
                        Layout.fillWidth: true
                        Rectangle {  // now
                            z: 2
                            width: Math.max(1, Math.round(theme.em * 0.12))
                            height: parent.height
                            color: theme.loss
                        }
                        implicitHeight: theme.em * 2.4
                        Rectangle {
                            anchors.fill: parent
                            radius: theme.radiusSm
                            color: theme.tint(theme.text, "stripe")
                        }
                        Repeater {
                            model: lane.modelData.items
                            Rectangle {
                                id: block
                                required property var modelData
                                objectName: "timelineBlock"
                                readonly property real begin: Math.max(modelData.start, line.now)
                                x: (begin - line.now) / line.period * laneTrack.width
                                width: Math.max((Math.min(modelData.end, line.now + line.period) - begin) / line.period
                                                * laneTrack.width - 2, theme.em * 0.6)
                                height: laneTrack.height
                                radius: theme.radiusSm
                                // close or hovered: stronger tint (no accent hover border)
                                color: theme.tint(theme.accent, modelData.soon || blockArea.containsMouse ? "strong" : "selected")
                                clip: true
                                TpText {
                                    anchors.fill: parent
                                    anchors.leftMargin: theme.space1
                                    verticalAlignment: Text.AlignVCenter
                                    role: "caption"
                                    tabular: true
                                    font.weight: Font.DemiBold
                                    text: block.modelData.time
                                }
                                MouseArea {
                                    id: blockArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: line.menuRequested(block.modelData.key, block, block.modelData.start)
                                }
                                ToolTip.visible: blockArea.containsMouse
                                ToolTip.text: block.modelData.tip
                            }
                        }
                    }
                }
            }
        }
        TpText {
            Layout.fillWidth: true
            role: "caption"
            wrap: true
            text: i18n.tr("Next %1 hours. Click a race for its menu.").replace("%1", line.data_.hours || 6)
        }
        Item { Layout.fillHeight: true }
    }
}
