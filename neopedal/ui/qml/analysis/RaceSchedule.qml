import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import "schedule.js" as Js

// Upcoming Races: online races of Le Mans Ultimate to come, read from RaceControl with the game sign in. Tabs:
// daily races by tier (cards, compact list or timeline of the next hours), weekly & special events, championships
// (rounds, sessions of the current round on demand), co-op events (leaderboard on demand), servers hosted by players.
// Each race: next start & time to it (pulses just before), track, classes, your personal best & level of each class
// driven there, sessions, track time & weather, settings, registrations, Safety Rank needed (lock & text when yours
// is lower), cars or track not owned, reminder set. A race opens a menu: driver stats, recorded laps, race
// calculator, reminder, field of the next start, calendar export. Filters: search, classes, owned cars only, Open to
// Me (races your Safety Rank opens, servers without password & not full). Last read shown while the game is closed.
TpPage {
    id: page

    readonly property var status: backend.status
    readonly property int columns: width >= theme.bpWide ? 3 : width >= theme.bpCompact ? 2 : 1
    readonly property bool classFilter: backend.tab !== 3  // co-op events give no car class: chips hidden there
    readonly property bool filtered: backend.search !== "" || backend.ownedOnly
                                     || (classFilter && backend.classChoices.some(function(choice) { return choice.selected }))
    readonly property var tabs: [
        { text: i18n.tr("Daily Races"), glyph: "" },  // calendar
        { text: i18n.tr("Weekly & Special"), glyph: "" },  // clock
        { text: i18n.tr("Championships"), glyph: "" },  // flag
        { text: i18n.tr("Co-op"), glyph: "" },  // people
        { text: i18n.tr("Hosted Servers"), glyph: "" }  // network device
    ]
    property string menuKey: ""
    property real menuStart: 0  // start of the timeline block clicked (0: card or list, the race's next start)
    property string timelineField: ""  // field asked from a timeline block (detail key), shown under the timeline
    property string timelineFieldTitle: ""
    property string timelinePractice: ""  // practice servers asked from a timeline block (detail key)
    property string timelinePracticeTitle: ""

    function count(index) {
        return index < backend.counts.length ? backend.counts[index] : 0
    }
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
            status: [
                Pill {
                    objectName: "rankPill"
                    text: page.status.rank || ""
                    glyph: ""  // shield
                    fallback: "SR"
                    tint: page.status.rankKnown === true ? theme.accent : theme.dimText
                    tip: page.status.rankKnown === true
                         ? i18n.tr("Your Safety Rank: races it does not open are marked with a lock")
                         : i18n.tr("Safety Rank unknown: start Le Mans Ultimate once with online ranks on to read it")
                }
            ]
            TpSwitch {
                objectName: "openOnly"
                checkable: false  // follows backend
                checked: backend.openOnly
                text: i18n.tr("Open to Me")
                tip: i18n.tr("Hide races your Safety Rank does not open, and locked or full servers")
                onClicked: backend.setOpenOnly(!backend.openOnly)
                Accessible.role: Accessible.CheckBox
            }
            TpSpinner {
                visible: page.status.loading === true
                Layout.alignment: Qt.AlignVCenter
            }
            TpButton {
                objectName: "requestsButton"
                size: "sm"
                text: i18n.tr("Requests")
                tip: i18n.tr("Requests sent to RaceControl, GitHub and the lap times sheet since the app started")
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
            actionText: page.status.off === true ? i18n.tr("Open Option")
                        : page.status.noGame === true ? i18n.tr("Start Le Mans Ultimate") : ""
            onAction: page.status.off === true ? backend.openOnlineOption() : backend.startGame()
        }

        TpTabBar {
            objectName: "scheduleTabs"
            Layout.fillWidth: true
            name: i18n.tr("Races")
            model: page.tabs
            counts: backend.counts
            currentIndex: backend.tab
            onActivated: function(index) { backend.setTab(index) }
        }

        // Filters: search, view (races) or sort (servers), owned cars only, classes
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
                visible: backend.tab <= 1
                name: i18n.tr("View")
                options: backend.tab === 0
                         ? [{ glyph: "", text: "", tip: i18n.tr("Cards") },
                            { glyph: "", text: "", tip: i18n.tr("List") },
                            { glyph: "", text: "", tip: i18n.tr("Timeline") }]
                         : [{ glyph: "", text: "", tip: i18n.tr("Cards") },
                            { glyph: "", text: "", tip: i18n.tr("List") }]
                // weekly tab: cards unless the list is chosen (timeline of the daily tab: cards here)
                currentIndex: backend.tab === 0 ? backend.view : (backend.view === 1 ? 1 : 0)
                onActivated: function(index) { backend.setView(index) }
            }
            TpSegmented {
                objectName: "timelineHours"
                visible: backend.tab === 0 && backend.view === 2
                name: i18n.tr("Hours shown")
                options: ["3 h", "6 h", "12 h"]
                currentIndex: [3, 6, 12].indexOf(backend.timelineHours)
                onActivated: function(index) { backend.setTimelineHours([3, 6, 12][index]) }
            }
            TpSegmented {
                objectName: "serverSort"
                visible: backend.tab === 4
                name: i18n.tr("Sort")
                options: [i18n.tr("Players"), i18n.tr("Region"), i18n.tr("Name")]
                currentIndex: backend.serverSort
                onActivated: function(index) { backend.setServerSort(index) }
            }
            TpChip {
                objectName: "ownedOnly"
                text: i18n.tr("Owned Cars & Tracks")
                selected: backend.ownedOnly
                multi: true
                tip: i18n.tr("Hide races and servers needing a car or a track you don't own")
                onClicked: backend.setOwnedOnly(!backend.ownedOnly)
            }
            Repeater {
                model: backend.classChoices
                TpChip {
                    required property var modelData
                    visible: page.classFilter
                    text: modelData.label
                    showDot: true
                    dotColor: modelData.color
                    selected: modelData.selected
                    dimmed: modelData.missing === true  // chosen before, in no race now: still filtering
                    multi: true
                    tip: modelData.missing === true ? Js.joined([modelData.name, i18n.tr("No race in this class now")])
                                                    : modelData.name
                    onClicked: backend.toggleClass(modelData.name)
                }
            }
            TpButton {
                visible: page.filtered
                flat: true
                size: "sm"
                text: i18n.tr("Clear Filters")
                onClicked: backend.clearFilters()
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: backend.tab

            // Daily races: timeline of the next hours, or one section per tier
            Item {
                ScrollPane {  // timeline view too while no race is shown: its empty, filtered or loading state
                    anchors.fill: parent
                    visible: backend.view !== 2 || empty
                    empty: page.count(0) === 0
                    openHidden: backend.openHidden[0] || 0
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
                    visible: backend.view === 2 && page.count(0) > 0
                    data_: backend.timeline
                    lanes: backend.timelineModel
                    fieldKey: page.timelineField
                    fieldTitle: page.timelineFieldTitle
                    practiceKey: page.timelinePractice
                    practiceTitle: page.timelinePracticeTitle
                    onMenuRequested: function(key, button, start) { page.openMenu(key, button, start) }
                }
            }

            // Weekly & special events
            ScrollPane {
                empty: page.count(1) === 0
                openHidden: backend.openHidden[1] || 0
                emptyTitle: i18n.tr("No weekly or special event to come")
                filtered: page.filtered
                GridLayout {
                    Layout.fillWidth: true
                    visible: backend.view !== 1
                    columns: page.columns
                    columnSpacing: theme.space4
                    rowSpacing: theme.space4
                    uniformCellWidths: true
                    Repeater {
                        model: backend.view !== 1 ? backend.eventsModel : null
                        EventCard {
                            showTier: true
                            onMenuRequested: function(key, card, at) { page.openMenu(key, card, 0, at) }
                        }
                    }
                    Filler { cards: backend.events.length; columns: page.columns }
                }
                Repeater {
                    model: backend.view === 1 ? backend.eventsModel : null
                    EventRow {
                        showTier: true
                        onMenuRequested: function(key, row, at) { page.openMenu(key, row, 0, at) }
                    }
                }
            }

            // Championships
            ScrollPane {
                empty: page.count(2) === 0
                openHidden: backend.openHidden[2] || 0
                emptyTitle: i18n.tr("No championship")
                filtered: page.filtered
                GridLayout {
                    Layout.fillWidth: true
                    columns: Math.min(page.columns, 2)
                    columnSpacing: theme.space4
                    rowSpacing: theme.space4
                    uniformCellWidths: true
                    Repeater {
                        model: backend.championshipsModel
                        ChampionshipCard { onMenuRequested: function(key, card, at) { page.openMenu(key, card, 0, at) } }
                    }
                    Filler { cards: backend.championships.length; columns: Math.min(page.columns, 2) }
                }
            }

            // Co-op events
            ScrollPane {
                empty: page.count(3) === 0
                openHidden: backend.openHidden[3] || 0
                emptyTitle: i18n.tr("No co-op event")
                filtered: page.filtered
                GridLayout {
                    Layout.fillWidth: true
                    columns: Math.min(page.columns, 2)
                    columnSpacing: theme.space4
                    rowSpacing: theme.space4
                    uniformCellWidths: true
                    Repeater {
                        model: backend.coopModel
                        CoopCard { onMenuRequested: function(key, card, at) { page.openMenu(key, card, 0, at) } }
                    }
                    Filler { cards: backend.coop.length; columns: Math.min(page.columns, 2) }
                }
            }

            // Servers hosted by players
            ScrollPane {
                empty: page.count(4) === 0
                openHidden: backend.openHidden[4] || 0
                emptyTitle: i18n.tr("No hosted server")
                filtered: page.filtered
                spacing: theme.space1
                Repeater {
                    model: backend.serversModel
                    ServerRow { onMenuRequested: function(key, row, at) { page.openMenu(key, row, 0, at) } }
                }
            }

        }
    }


    // Weekly leaderboard of a race or of a championship round: every page, all classes or one, your friends, a
    // driver found by name, where you stand; a row opens the driver's profile. Keys: Page Up / Down, Home / End
    TpPopup {
        id: boardPopup
        objectName: "boardPopup"
        readonly property var board: backend.board
        readonly property bool pages: board.friends !== true
        // Overlay of the page's window now (page made before the app shows it: the popup's own Overlay.overlay
        // stays on the former window, no parent, never opens; see TpDialogHost)
        parent: page.Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: Math.min(page.width - theme.space6 * 2, theme.em * 76)
        height: Math.min(page.height - theme.space6 * 2, theme.em * 50)
        onOpened: boardKeys.forceActiveFocus()
        onClosed: if (backend.board.open === true) backend.closeBoard()
        Connections {
            target: backend
            function onBoardChanged() {
                if (backend.board.open === true && !boardPopup.opened)
                    boardPopup.open()
                else if (backend.board.open !== true && boardPopup.opened)
                    boardPopup.close()
            }
        }
        ColumnLayout {
            id: boardKeys
            anchors.fill: parent
            spacing: theme.space3
            focus: true
            Keys.onPressed: function(event) {
                var board = boardPopup.board
                if (!boardPopup.pages || board.loading === true)
                    return
                if (event.key === Qt.Key_PageDown) backend.boardPage(board.page + 1)
                else if (event.key === Qt.Key_PageUp) backend.boardPage(board.page - 1)
                else if (event.key === Qt.Key_Home) backend.boardPage(1)
                else if (event.key === Qt.Key_End) backend.boardPage(board.pages)
                else return
                event.accepted = true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: theme.space3
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    TpText { Layout.fillWidth: true; role: "subtitle"; text: boardPopup.board.title || "" }
                    TpText { Layout.fillWidth: true; role: "caption"; text: boardPopup.board.subtitle || "" }
                }
                TpSpinner { visible: boardPopup.board.loading === true }
                TpButton {
                    objectName: "boardExport"
                    flat: true
                    size: "sm"
                    glyph: theme.glyphs.export
                    fallback: "CSV"
                    tip: i18n.tr("Export to CSV…")
                    enabled: (boardPopup.board.rows || []).length > 0
                    onClicked: backend.boardExport()
                }
                TpButton {
                    flat: true
                    size: "sm"
                    glyph: theme.glyphs.close
                    fallback: "✕"
                    tip: i18n.tr("Close")
                    onClicked: boardPopup.close()
                }
            }
            Flow {  // all classes or one, your friends, a driver by name
                Layout.fillWidth: true
                spacing: theme.space2
                TpChip {
                    text: i18n.tr("All Classes")
                    selected: (boardPopup.board.vehicleClass || "") === ""
                    enabled: boardPopup.board.loading !== true  // class changed once the page asked is read
                    onClicked: backend.boardClass("")
                }
                Repeater {
                    model: boardPopup.board.classes || []
                    TpChip {
                        required property var modelData
                        text: modelData.label
                        showDot: true
                        dotColor: modelData.color
                        tip: modelData.name
                        selected: boardPopup.board.vehicleClass === modelData.name
                        enabled: boardPopup.board.loading !== true
                        onClicked: backend.boardClass(modelData.name)
                    }
                }
                TpChip {
                    objectName: "boardFriends"
                    text: i18n.tr("Friends")
                    glyph: ""  // people
                    multi: true
                    selected: boardPopup.board.friends === true
                    tip: i18n.tr("You & your RaceControl friends ranked this week")
                    onClicked: backend.boardFriends(boardPopup.board.friends !== true)
                }
                TpSearchField {
                    objectName: "boardFind"
                    width: theme.em * 14
                    placeholderText: i18n.tr("Find a driver…")
                    searchDelay: 100000  // asked with Enter only (one ask a name): not on focus loss
                    onAccepted: if (text.trim() !== "") backend.boardFind(text)
                }
                TpText {
                    role: "caption"
                    visible: text !== ""
                    text: boardPopup.board.found || ""
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: theme.space3
                TpText {
                    role: "label"
                    text: Js.joined([boardPopup.pages ? i18n.tr("Fastest laps of the week") : i18n.tr("Friends"),
                                     boardPopup.pages ? boardPopup.board.count : ""])
                }
                Pill {
                    visible: (boardPopup.board.myPlace || "") !== ""
                    size: "sm"
                    text: boardPopup.board.myPlace || ""
                    tint: theme.accent
                    tip: i18n.tr("Your place")
                }
                TpText {
                    Layout.fillWidth: true
                    role: "caption"
                    text: boardPopup.board.standing || ""
                }
                TpButton {
                    objectName: "boardMine"
                    visible: boardPopup.pages && (boardPopup.board.myPage || 0) > 0
                    enabled: boardPopup.board.loading !== true
                    flat: true
                    size: "sm"
                    text: i18n.tr("Show My Place")
                    onClicked: backend.boardMine()
                }
            }
            BoardRowLayout {  // column titles (stay above the list)
                Layout.fillWidth: true
                Layout.rightMargin: theme.space3
                header: true
            }
            ListView {
                id: boardList
                objectName: "boardList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: boardPopup.board.rows || []
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: Item {
                    id: boardRow
                    required property var modelData
                    required property int index
                    width: boardList.width - theme.space3
                    implicitHeight: theme.rowTall
                    TpListRow {
                        anchors.fill: parent
                        striped: boardRow.index % 2 === 1
                        emphasized: boardRow.modelData.me
                        hovered: rowHover.containsMouse
                    }
                    MouseArea {
                        id: rowHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.showProfile(boardRow.modelData.name)
                    }
                    BoardRowLayout { anchors.fill: parent; row: boardRow.modelData }
                }
                TpStateView {
                    anchors.centerIn: parent
                    visible: boardList.count === 0
                    loading: boardPopup.board.loading === true
                    empty: boardList.count === 0
                    error: (boardPopup.board.error || "") !== ""
                    errorText: boardPopup.board.error || ""
                    glyph: ""  // flag
                    title: i18n.tr("Nobody ranked yet")
                    loadingText: i18n.tr("Reading the leaderboard…")
                }
            }
            RowLayout {  // pages
                Layout.alignment: Qt.AlignHCenter
                visible: boardPopup.pages
                spacing: theme.space2
                TpButton {
                    flat: true
                    size: "sm"
                    text: "1"
                    tip: i18n.tr("First Page")
                    shortcut: i18n.tr("Home")
                    enabled: (boardPopup.board.page || 1) > 1 && boardPopup.board.loading !== true
                    onClicked: backend.boardPage(1)
                }
                TpButton {
                    objectName: "boardPrevious"
                    flat: true
                    size: "sm"
                    glyph: ""  // chevron left
                    fallback: "‹"
                    tip: i18n.tr("Previous Page")
                    shortcut: i18n.tr("Page Up")
                    enabled: (boardPopup.board.page || 1) > 1 && boardPopup.board.loading !== true
                    onClicked: backend.boardPage(boardPopup.board.page - 1)
                }
                TpText {
                    role: "label"
                    tabular: true
                    text: i18n.tr("Page %1 of %2").replace("%1", boardPopup.board.page || 1).replace("%2", boardPopup.board.pages || 1)
                }
                TpButton {
                    objectName: "boardNext"
                    flat: true
                    size: "sm"
                    glyph: ""  // chevron right
                    fallback: "›"
                    tip: i18n.tr("Next Page")
                    shortcut: i18n.tr("Page Down")
                    enabled: (boardPopup.board.page || 1) < (boardPopup.board.pages || 1) && boardPopup.board.loading !== true
                    onClicked: backend.boardPage(boardPopup.board.page + 1)
                }
                TpButton {
                    flat: true
                    size: "sm"
                    text: String(boardPopup.board.pages || 1)
                    tip: i18n.tr("Last Page")
                    shortcut: i18n.tr("End")
                    enabled: (boardPopup.board.page || 1) < (boardPopup.board.pages || 1) && boardPopup.board.loading !== true
                    onClicked: backend.boardPage(boardPopup.board.pages)
                }
            }
        }
    }

    // Profile of a driver (leaderboard row): nationality, Driver & Safety Rank, badge
    TpPopup {
        id: profilePopup
        objectName: "profilePopup"
        readonly property var profile: backend.profile
        // Overlay of the page's window now (page made before the app shows it: the popup's own Overlay.overlay
        // stays on the former window, no parent, never opens; see TpDialogHost)
        parent: page.Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: theme.em * 22
        onClosed: if (backend.profile.open === true) backend.closeProfile()
        Connections {
            target: backend
            function onProfileChanged() {
                if (backend.profile.open === true && !profilePopup.opened)
                    profilePopup.open()
                else if (backend.profile.open !== true && profilePopup.opened)
                    profilePopup.close()
            }
        }
        ColumnLayout {
            width: parent.width
            spacing: theme.space2
            TpText { Layout.fillWidth: true; role: "subtitle"; text: profilePopup.profile.name || "" }
            TpSpinner { visible: profilePopup.profile.loading === true }
            RowLayout {  // nationality: country name after its flag
                Layout.fillWidth: true
                visible: (profilePopup.profile.nationality || "") !== ""
                spacing: theme.space2
                TpText { Layout.fillWidth: true; text: i18n.tr("Nationality"); textFormat: Text.PlainText; color: theme.dimText; elide: Text.ElideRight }
                TpFlag { flag: profilePopup.profile.flag || ({}) }
                TpText { text: profilePopup.profile.nationality || ""; textFormat: Text.PlainText; color: theme.text }
            }
            TpKeyValue { visible: (profilePopup.profile.dr || "") !== ""; label: i18n.tr("Driver Rank"); value: profilePopup.profile.dr || "" }
            TpKeyValue { visible: (profilePopup.profile.sr || "") !== ""; label: i18n.tr("Safety Rank"); value: profilePopup.profile.sr || "" }
            TpKeyValue { visible: (profilePopup.profile.badge || "") !== ""; label: i18n.tr("Badge"); value: profilePopup.profile.badge || "" }
            TpText {
                Layout.fillWidth: true
                role: "caption"
                visible: text !== ""
                text: profilePopup.profile.error || ""
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

    // Registration to a start: class, car & livery among the ones you own (event read when opened)
    TpDialog {
        id: registrationDialog
        objectName: "registrationDialog"
        // Overlay of the page's window now (page made before the app shows it: the popup's own Overlay.overlay
        // stays on the former window, no parent, never opens; see TpDialogHost)
        parent: page.Overlay.overlay
        readonly property var reg: backend.registration
        readonly property var cars: reg.cars || []
        property string chosenClass: ""
        property string chosenModel: ""
        property int chosenIndex: -1  // index of the car in reg.cars, -1 none
        readonly property var classes: unique(cars.map(function(car) { return car.vehicleClass }))
        readonly property var models: unique(cars.filter(function(car) { return car.vehicleClass === chosenClass })
                                                 .map(function(car) { return car.model }))
        readonly property var liveries: cars.filter(function(car) {
            return car.vehicleClass === chosenClass && car.model === chosenModel })
        readonly property var liveryNames: liveries.map(function(car) { return car.livery })

        function unique(list) {
            var found = []
            for (var i = 0; i < list.length; ++i) {
                if (found.indexOf(list[i]) < 0)
                    found.push(list[i])
            }
            return found
        }
        function pickClass(name) {
            chosenClass = name
            classCombo.currentIndex = classes.indexOf(name)
            pickModel(models.length > 0 ? models[0] : "")
        }
        function pickModel(name) {
            chosenModel = name
            modelCombo.currentIndex = models.indexOf(name)
            pickLivery(0)
        }
        function pickLivery(index) {
            chosenIndex = index >= 0 && index < liveries.length ? liveries[index].index : -1
            liveryCombo.currentIndex = chosenIndex >= 0 ? index : -1
        }

        title: i18n.tr("Register to %1").replace("%1", reg.title || "")
        acceptText: reg.busy === true ? i18n.tr("Registering…") : i18n.tr("Register")
        acceptEnabled: chosenIndex >= 0 && reg.busy !== true && reg.loading !== true
        closeOnAccept: false
        dismissOnOutside: false
        width: Math.min(parent ? parent.width - theme.em * 2 : theme.em * 32, theme.em * 32)
        onAccepted: backend.confirmRegistration(chosenIndex)
        onCancelled: backend.closeRegistration()
        // Lists made from the cars first (their bindings may follow this handler): first car chosen after them
        onCarsChanged: Qt.callLater(function() { pickClass(classes.length > 0 ? classes[0] : "") })
        Connections {
            target: backend
            function onRegistrationChanged() {
                if (backend.registration.open === true && !registrationDialog.opened)
                    registrationDialog.open()
                else if (backend.registration.open !== true && registrationDialog.opened)
                    registrationDialog.done()
            }
        }
        TpText {
            Layout.fillWidth: true
            role: "caption"
            wrap: true
            text: [registrationDialog.reg.when, registrationDialog.reg.track].filter(function(part) { return part })
                  .join(" · ")
        }
        TpNotice {
            Layout.fillWidth: true
            visible: (registrationDialog.reg.note || "") !== ""
            text: registrationDialog.reg.note || ""
            tone: theme.warning
            glyph: ""  // warning
            fallback: "!"
        }
        TpSpinner { visible: registrationDialog.reg.loading === true }
        GridLayout {
            Layout.fillWidth: true
            visible: registrationDialog.cars.length > 0
            columns: 2
            columnSpacing: theme.space3
            rowSpacing: theme.space2
            TpText { text: i18n.tr("Class") }
            TpCombo {
                id: classCombo
                objectName: "registrationClass"
                Layout.fillWidth: true
                tip: i18n.tr("Class")
                model: registrationDialog.classes
                enabled: registrationDialog.reg.busy !== true
                onActivated: function(index) { registrationDialog.pickClass(registrationDialog.classes[index]) }
            }
            TpText { text: i18n.tr("Car") }
            TpCombo {
                id: modelCombo
                objectName: "registrationModel"
                Layout.fillWidth: true
                tip: i18n.tr("Car")
                model: registrationDialog.models
                enabled: registrationDialog.reg.busy !== true
                onActivated: function(index) { registrationDialog.pickModel(registrationDialog.models[index]) }
            }
            TpText { text: i18n.tr("Livery") }
            TpCombo {
                id: liveryCombo
                objectName: "registrationLivery"
                Layout.fillWidth: true
                tip: i18n.tr("Livery")
                model: registrationDialog.liveryNames
                enabled: registrationDialog.reg.busy !== true
                onActivated: function(index) { registrationDialog.pickLivery(index) }
            }
        }
        TpText {
            Layout.fillWidth: true
            role: "caption"
            wrap: true
            visible: registrationDialog.cars.length > 0
            text: i18n.tr("Only cars you own are listed. Join the server from the game when it opens: a reminder is set before the start.")
        }
        TpText {
            objectName: "registrationError"
            Layout.fillWidth: true
            wrap: true
            visible: text !== ""
            color: theme.warning
            text: registrationDialog.reg.error || ""
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
                if (entry.id === "field" && page.menuStart > 0) {  // timeline: field shown under it
                    page.timelineField = entry.detail || ""
                    page.timelineFieldTitle = entry.detailTitle || ""
                }
                if (entry.id === "practice" && page.menuStart > 0) {  // timeline: practice servers under it too
                    page.timelinePractice = entry.detail || ""
                    page.timelinePracticeTitle = entry.detailTitle || ""
                }
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
        property int openHidden: 0  // rows Open to Me hides (others filters passed)
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
                  : pane.openHidden > 0 ? i18n.tr("Everything here is hidden by Open to Me.")
                  : (backend.status.note || "") !== "" ? "" : i18n.tr("Races are read from RaceControl while Le Mans Ultimate runs.")
            actionText: pane.filtered ? i18n.tr("Clear Filters") : pane.openHidden > 0 ? i18n.tr("Show All") : ""
            onAction: if (pane.filtered) backend.clearFilters(); else backend.setOpenOnly(false)
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

    // Safety Rank needed: lock & text when yours is lower (never color alone)
    component RequirementPill: Pill {
        property int open: 1
        property string requirement: ""
        visible: requirement !== ""
        size: "sm"
        text: requirement
        glyph: open === 0 ? theme.glyphs.lock : ""
        fallback: open === 0 ? "L" : ""
        tint: open === 0 ? theme.warning : theme.dimText
        tip: open === 0 ? i18n.tr("Your Safety Rank does not open this race yet")
                        : open === 1 ? i18n.tr("Safety Rank needed: yours opens it") : i18n.tr("Safety Rank needed")
    }

    component ClassBadges: Flow {
        property var classes: []
        visible: classes.length > 0
        spacing: theme.space2
        Repeater {
            model: parent.classes
            TpClassBadge {
                required property var modelData
                label: modelData.label
                fullName: modelData.full
                fill: modelData.color
            }
        }
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

    // Field of a start (read on demand from the menu): drivers, classes, Driver & Safety Rank shares
    component FieldBlock: ColumnLayout {
        id: fieldBlock
        property string detailKey: ""  // "field:<race key>" (next start) or "field:<race key>@<start>"
        property string title: ""
        readonly property var field: detailKey !== "" ? backend.details[detailKey] || null : null
        readonly property bool reading: detailKey !== "" && backend.loadingDetails.indexOf(detailKey) >= 0
        readonly property bool shown: field !== null || reading
        visible: shown
        spacing: theme.space1
        TpSectionLabel { text: Js.joined([i18n.tr("Field"), fieldBlock.title]) }
        TpSpinner { visible: fieldBlock.reading }
        TpText {
            Layout.fillWidth: true
            role: "caption"
            wrap: true
            visible: fieldBlock.field !== null
            text: fieldBlock.field === null ? "" : fieldBlock.field.error || Js.joined([fieldBlock.field.text, fieldBlock.field.classes])
        }
        RankShares { title: "DR"; shares: fieldBlock.field && fieldBlock.field.driverRanks ? fieldBlock.field.driverRanks : [] }
        RankShares { title: "SR"; shares: fieldBlock.field && fieldBlock.field.safetyRanks ? fieldBlock.field.safetyRanks : [] }
    }

    // Practice servers of a race read from its menu: players & time left of each, read time (not read again alone)
    component PracticeBlock: ColumnLayout {
        id: practiceBlock
        property string detailKey: ""  // "practice:<race key>"
        property string title: ""
        readonly property var practice: detailKey !== "" ? backend.details[detailKey] || null : null
        readonly property bool reading: detailKey !== "" && backend.loadingDetails.indexOf(detailKey) >= 0
        readonly property bool shown: practice !== null || reading
        objectName: "practiceBlock"
        visible: shown
        spacing: theme.space1
        TpSectionLabel {
            text: Js.joined([i18n.tr("Practice Servers"), practiceBlock.title,
                             practiceBlock.practice && practiceBlock.practice.read
                             ? i18n.tr("Read %1").replace("%1", practiceBlock.practice.read) : ""])
        }
        TpSpinner { visible: practiceBlock.reading }
        TpText {
            Layout.fillWidth: true
            role: "caption"
            wrap: true
            visible: text !== ""
            text: practiceBlock.practice === null ? "" : practiceBlock.practice.error || practiceBlock.practice.text || ""
        }
        Repeater {
            model: practiceBlock.practice && practiceBlock.practice.servers ? practiceBlock.practice.servers : []
            TpText { required property var modelData; Layout.fillWidth: true; role: "caption"; tabular: true; text: modelData }
        }
    }

    component RankShares: RowLayout {
        id: shareRow
        property string title: ""
        property var shares: []
        visible: shares.length > 0
        Layout.fillWidth: true
        spacing: theme.space2
        TpText { role: "caption"; text: shareRow.title; Layout.preferredWidth: theme.em * 1.6 }
        Repeater {
            model: shareRow.shares
            Pill {
                required property var modelData
                size: "sm"
                text: modelData.rank + " " + modelData.count
                tint: modelData.color
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
        // registration told when it says something of this race (yours, opening time): open is the rule
        readonly property bool registrationShown: card.race.registration !== "" && card.race.registrationOpen !== true
        signal menuRequested(string key, Item card, point at)
        objectName: "raceCard"
        fillContent: false
        Layout.fillWidth: true
        Layout.fillHeight: true
        eyebrow: card.showTier ? card.race.tierText : ""
        title: card.race.title
        tip: i18n.tr("Driver stats, recorded laps, race calculator, reminder, field & calendar")
        clickable: true
        onOpened: card.menuRequested(card.race.key, card, Qt.point(card.pad, card.bodyY - theme.space2))
        trailing: [GameLogo { source: card.race.trackLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 2.4 }]
        // race your Safety Rank does not open (Open to Me off): dimmed, open ones stand out
        opacity: card.race.open === 0 ? 0.62 : 1
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
        ClassBadges { Layout.fillWidth: true; classes: card.race.classes }
        PersonalBests { Layout.fillWidth: true; personal: card.race.personal || {} }
        Rectangle {  // facts of the race below
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: theme.space1
            color: theme.border
        }
        FactLine { glyph: "\uE916"; text: Js.joined([card.race.sessions, card.race.trackTime]) }  // stopwatch
        FactLine { glyph: card.race.wet === true ? "\uEB42" : "\uE706"; text: card.race.weather }  // water drop, sun
        FactLine {  // sliders
            glyph: "\uE9E9"
            text: Js.joined([card.race.settings, card.race.registered,
                             card.race.maxPlayers > 0 ? i18n.tr("%1 places").replace("%1", card.race.maxPlayers) : ""])
        }
        Flow {  // Safety Rank needed, your registration, server ready, what you don't own, your place this week
            Layout.fillWidth: true
            Layout.topMargin: theme.space1
            spacing: theme.space2
            visible: card.race.requirement !== "" || card.race.owned !== "" || card.registrationShown
                     || (card.race.place || "") !== "" || card.race.serverReady === true
            RequirementPill { open: card.race.open; requirement: card.race.requirement }
            Pill {
                visible: card.registrationShown
                size: "sm"
                text: card.race.registration
                glyph: card.race.registeredMe ? "\uE73E" : ""  // check
                fallback: card.race.registeredMe ? "\u2713" : ""
                tint: card.race.registeredMe ? theme.gain : theme.dimText
            }
            Pill {  // server of your split given by RaceControl (followed live, race_watch.py)
                objectName: "serverReady"
                visible: card.race.serverReady === true
                size: "sm"
                text: i18n.tr("Server ready: join it from the game")
                tint: theme.gain
            }
            Pill {
                visible: card.race.owned !== ""
                size: "sm"
                text: card.race.owned
                glyph: "\uE7BA"  // warning
                fallback: "!"
                tint: theme.warning
            }
            TpButton {  // your place in the weekly leaderboard: opens it
                objectName: "placeButton"
                visible: (card.race.place || "") !== ""
                flat: true
                size: "xs"
                glyph: "\ue7c1"  // flag
                fallback: "#"
                text: card.race.place || ""
                tip: i18n.tr("Your place in the weekly leaderboard")
                onClicked: backend.openBoard(card.race.key)
            }
        }
        FieldBlock { Layout.fillWidth: true; detailKey: "field:" + card.race.key }
        PracticeBlock { Layout.fillWidth: true; detailKey: "practice:" + card.race.key }
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


    // Columns of a leaderboard line (header: column titles)
    component BoardRowLayout: RowLayout {
        id: boardLine
        property var row: ({})
        property bool header: false
        spacing: theme.space3
        Layout.leftMargin: theme.space2
        Layout.rightMargin: theme.space2
        TpText {
            role: boardLine.header ? "overline" : "numeric"
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: theme.em * 3.6
            Layout.leftMargin: boardLine.header ? 0 : theme.space2
            text: boardLine.header ? "#" : boardLine.row.rank || ""
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            TpText {
                Layout.fillWidth: true
                role: boardLine.header ? "overline" : "body"
                font.weight: boardLine.row.me ? Font.DemiBold : Font.Normal
                text: boardLine.header ? i18n.tr("Driver") : boardLine.row.name || ""
            }
            TpText {
                Layout.fillWidth: true
                visible: !boardLine.header
                role: "caption"
                text: boardLine.row.carLine || ""
            }
        }
        Item {
            Layout.preferredWidth: theme.em * 4
            implicitHeight: badge.implicitHeight
            TpClassBadge {
                id: badge
                visible: !boardLine.header && (boardLine.row.classLabel || "") !== ""
                label: boardLine.row.classLabel || ""
                fullName: boardLine.row.className || ""
                fill: boardLine.row.classColor || theme.border
            }
            TpText { visible: boardLine.header; role: "overline"; text: i18n.tr("Class") }
        }
        TpText {
            role: boardLine.header ? "overline" : "caption"
            Layout.preferredWidth: theme.em * 11
            text: boardLine.header ? "DR · SR" : boardLine.row.ranks || ""
        }
        TpText {
            role: boardLine.header ? "overline" : "caption"
            tabular: true
            Layout.preferredWidth: theme.em * 9
            text: boardLine.header ? i18n.tr("Sectors") : boardLine.row.sectors || ""
        }
        TpText {
            role: boardLine.header ? "overline" : "numeric"
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: theme.em * 5
            text: boardLine.header ? i18n.tr("Lap") : boardLine.row.lap || ""
        }
        TpText {
            role: boardLine.header ? "overline" : "caption"
            tabular: true
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: theme.em * 4
            text: boardLine.header ? i18n.tr("Gap") : boardLine.row.gap || ""
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
        implicitHeight: lineHeight + (rowField.shown ? rowField.implicitHeight + theme.space2 : 0)
                        + (rowPractice.shown ? rowPractice.implicitHeight + theme.space2 : 0)
        TpListRow {
            anchors.fill: parent
            striped: raceRow.index % 2 === 1
            hovered: rowArea.containsMouse
            emphasized: raceRow.race.reminder > 0
        }
        ToolTip.visible: rowArea.containsMouse
        ToolTip.text: i18n.tr("Driver stats, recorded laps, race calculator, reminder, field & calendar")
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
            ClassBadges { classes: raceRow.race.classes; Layout.maximumWidth: theme.em * 12 }
            TpText {
                role: "numeric"
                visible: text !== ""
                text: Js.bestText(raceRow.race.personal)
            }
            TpButton {
                visible: (raceRow.race.place || "") !== ""
                flat: true
                size: "xs"
                text: raceRow.race.place || ""
                tip: i18n.tr("Your place in the weekly leaderboard")
                onClicked: backend.openBoard(raceRow.race.key)
            }
            RequirementPill { open: raceRow.race.open; requirement: raceRow.race.requirement }
        }
        FieldBlock {  // field of the next start (Show Field of the menu), under the line like the card
            id: rowField
            objectName: "raceRowField"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: rowContent.bottom
            anchors.leftMargin: theme.space3
            anchors.rightMargin: theme.space2
            detailKey: "field:" + raceRow.race.key
        }
        PracticeBlock {  // practice servers (Practice Servers of the menu), under the field
            id: rowPractice
            objectName: "raceRowPractice"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: rowField.shown ? rowField.bottom : rowContent.bottom
            anchors.topMargin: rowField.shown ? theme.space2 : 0
            anchors.leftMargin: theme.space3
            anchors.rightMargin: theme.space2
            detailKey: "practice:" + raceRow.race.key
        }
    }

    // Next hours of the daily races: one lane per race under its tier, a block per start (width: its length)
    component Timeline: ColumnLayout {
        id: line
        property var data_: ({})
        property var lanes: null  // model of the lanes (kept while time goes by: blocks placed from data_.now)
        readonly property real now: data_.now || 0
        readonly property real period: data_.period || 1
        property string fieldKey: ""  // field of a start asked from a block's menu
        property string fieldTitle: ""
        property string practiceKey: ""  // practice servers of a race asked from a block's menu
        property string practiceTitle: ""
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
                                // locked: warning tint; close or hovered: stronger tint (no accent hover border)
                                color: theme.tint(modelData.open === 0 ? theme.warning : theme.accent,
                                                  modelData.soon || blockArea.containsMouse ? "strong" : "selected")
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
            text: i18n.tr("Next %1 hours. Click a race for its menu; locked races in the warning color.").replace("%1", line.data_.hours || 6)
        }
        FieldBlock { Layout.fillWidth: true; detailKey: line.fieldKey; title: line.fieldTitle }
        PracticeBlock { Layout.fillWidth: true; detailKey: line.practiceKey; title: line.practiceTitle }
        Item { Layout.fillHeight: true }
    }

    component ChampionshipCard: TpSectionCard {
        id: champ
        required property var modelData
        readonly property var item: modelData
        readonly property var detail: backend.details["championship:" + champ.item.key] || null
        readonly property bool reading: backend.loadingDetails.indexOf("championship:" + champ.item.key) >= 0
        signal menuRequested(string key, Item card, point at)
        objectName: "championshipCard"
        fillContent: false
        Layout.fillWidth: true
        Layout.fillHeight: true
        eyebrow: Js.joined([champ.item.tierText, champ.item.kindText])
        title: champ.item.name
        tip: i18n.tr("Driver stats, recorded laps, race calculator, leaderboard & calendar")
        clickable: true  // menu below the title line, as a race card
        onOpened: champ.menuRequested(champ.item.key, champ, Qt.point(champ.pad, champ.bodyY - theme.space2))
        trailing: [GameLogo { source: champ.item.roundLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 2.4 }]
        opacity: champ.item.open === 0 ? 0.62 : 1  // your Safety Rank does not open it (Open to Me off)
        Flow {
            Layout.fillWidth: true
            spacing: theme.space2
            RequirementPill { open: champ.item.open; requirement: champ.item.requirement }
            Pill {
                visible: champ.item.registered === true
                size: "sm"
                text: i18n.tr("Registered")
                glyph: ""  // check
                fallback: "✓"
                tint: theme.gain
            }
            Pill {
                visible: champ.item.upcoming === true
                size: "sm"
                text: i18n.tr("Not started")
                tint: theme.accent
            }
            Pill {
                visible: champ.item.registrations !== ""
                size: "sm"
                text: champ.item.registrations
                glyph: ""  // people
                fallback: "#"
                tint: theme.dimText
            }
            Pill {
                visible: champ.item.owned !== ""
                size: "sm"
                text: champ.item.owned
                glyph: ""  // warning
                fallback: "!"
                tint: theme.warning
            }
        }
        TpText {  // current round (its chip below: number only)
            Layout.fillWidth: true
            role: "subtitle"
            visible: text !== ""
            text: Js.joined([champ.item.round, champ.item.roundTrack])
        }
        TpText {
            Layout.fillWidth: true
            role: "caption"
            wrap: true
            visible: text !== ""
            text: Js.joined([champ.item.roundEnds, champ.item.rules])
        }
        RowLayout {  // next session of the current round
            Layout.fillWidth: true
            visible: champ.item.next !== ""
            spacing: theme.space3
            TpText { role: "numeric"; font.weight: Font.DemiBold; text: champ.item.next }
            UntilPill { race: champ.item }
            TpText {
                Layout.fillWidth: true
                role: "caption"
                tabular: true
                text: champ.item.later.slice(0, Js.LATER).join("  ")
            }
        }
        TpButton {  // your place in the leaderboard of the round: opens it
            visible: (champ.item.place || "") !== ""
            flat: true
            size: "xs"
            glyph: "\ue7c1"  // flag
            fallback: "#"
            text: champ.item.place || ""
            tip: i18n.tr("Your place in the leaderboard of the round")
            onClicked: backend.openBoard(champ.item.key)
        }
        PersonalBests { Layout.fillWidth: true; personal: champ.item.personal || {} }
        ClassBadges { Layout.fillWidth: true; classes: champ.item.classes }
        Flow {  // rounds by number: current one selected, past ones dim, track & dates in the tooltip
            Layout.fillWidth: true
            visible: champ.item.rounds.length > 0
            spacing: theme.space1
            TpText {
                role: "caption"
                height: roundChips.count > 0 && roundChips.itemAt(0) ? roundChips.itemAt(0).height : implicitHeight
                verticalAlignment: Text.AlignVCenter
                rightPadding: theme.space1
                text: i18n.tr("Rounds")
            }
            Repeater {
                id: roundChips
                model: champ.item.rounds
                TpChip {
                    required property var modelData
                    interactive: false
                    size: "sm"
                    selected: modelData.current
                    dimmed: modelData.past
                    text: modelData.number + (modelData.points !== "" ? " " + modelData.points : "")
                    tip: Js.joined([modelData.number + " · " + modelData.track, modelData.dates, modelData.length,
                                    modelData.points])
                }
            }
        }
        ColumnLayout {  // sessions of the round with registrations, attempts, practice servers (on demand)
            Layout.fillWidth: true
            visible: champ.detail !== null || champ.reading
            spacing: theme.space1
            TpSpinner { visible: champ.reading }
            TpText {
                Layout.fillWidth: true
                role: "caption"
                wrap: true
                visible: text !== ""
                text: champ.detail === null ? "" : champ.detail.error || Js.joined([champ.detail.attempts].concat(champ.detail.practice || []))
            }
            Repeater {
                model: champ.detail && champ.detail.sessions ? champ.detail.sessions : []
                TpText {
                    required property var modelData
                    Layout.fillWidth: true
                    role: "caption"
                    tabular: true
                    text: Js.joined([modelData.time, modelData.until, modelData.registered])
                }
            }
        }
        ColumnLayout {  // your rounds (on demand)
            Layout.fillWidth: true
            readonly property var progress: backend.details["progress:" + champ.item.key] || null
            visible: progress !== null || backend.loadingDetails.indexOf("progress:" + champ.item.key) >= 0
            spacing: theme.space1
            TpSectionLabel { text: i18n.tr("Your Progress") }
            TpSpinner { visible: backend.loadingDetails.indexOf("progress:" + champ.item.key) >= 0 }
            TpText {
                Layout.fillWidth: true
                role: "caption"
                visible: text !== ""
                text: parent.progress === null ? "" : parent.progress.error || parent.progress.summary || ""
            }
            Repeater {
                model: parent.progress && parent.progress.rounds ? parent.progress.rounds : []
                TpText {
                    required property var modelData
                    Layout.fillWidth: true
                    role: "caption"
                    text: Js.joined([modelData.round, modelData.races, modelData.best])
                }
            }
        }
        footer: [
            TpButton {
                objectName: "championshipProgress"
                visible: backend.details["progress:" + champ.item.key] === undefined
                         && backend.loadingDetails.indexOf("progress:" + champ.item.key) < 0
                flat: true
                size: "sm"
                text: i18n.tr("Your Progress")
                tip: i18n.tr("Rounds you drove in this championship and your best place in each")
                onClicked: backend.readProgress(champ.item.key)
            },
            TpButton {
                objectName: "championshipDetails"
                visible: champ.item.id !== "" && champ.detail === null && !champ.reading
                flat: true
                size: "sm"
                text: i18n.tr("Sessions & Practice")
                tip: i18n.tr("Sessions of this round with drivers registered, attempts & practice servers")
                onClicked: backend.readChampionship(champ.item.key)
            }
        ]
    }

    component CoopCard: TpSectionCard {
        id: coopCard
        required property var modelData
        readonly property var event: modelData
        readonly property var board: backend.details["coop:" + coopCard.event.key] || null
        readonly property bool reading: backend.loadingDetails.indexOf("coop:" + coopCard.event.key) >= 0
        readonly property bool hasMine: coopCard.board !== null && coopCard.board.mine !== undefined
                                        && coopCard.board.mine.team !== undefined
        signal menuRequested(string key, Item card, point at)
        objectName: "coopCard"
        fillContent: false
        Layout.fillWidth: true
        Layout.fillHeight: true
        title: coopCard.event.name
        tip: i18n.tr("Driver stats, recorded laps, race calculator & calendar")
        clickable: true  // menu below the title line, as a race card
        onOpened: coopCard.menuRequested(coopCard.event.key, coopCard,
                                         Qt.point(coopCard.pad, coopCard.bodyY - theme.space2))
        trailing: [GameLogo { source: coopCard.event.trackLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 2.4 }]
        TpText { Layout.fillWidth: true; role: "subtitle"; text: coopCard.event.track }
        Flow {
            Layout.fillWidth: true
            spacing: theme.space2
            Pill {
                size: "sm"
                text: coopCard.event.open ? i18n.tr("Open now") : i18n.tr("Not open yet")
                dot: coopCard.event.open
                tint: coopCard.event.open ? theme.gain : theme.dimText
            }
            Pill { visible: coopCard.event.length !== ""; size: "sm"; text: coopCard.event.length; tint: theme.dimText }
            Pill {
                visible: coopCard.event.owned !== ""
                size: "sm"
                text: coopCard.event.owned
                glyph: ""  // warning
                fallback: "!"
                tint: theme.warning
            }
        }
        FactLine { glyph: "\uE787"; text: coopCard.event.dates }  // calendar
        PersonalBests { Layout.fillWidth: true; personal: coopCard.event.personal || {} }
        ColumnLayout {  // leaderboard (on demand): best teams & yours
            Layout.fillWidth: true
            visible: coopCard.board !== null || coopCard.reading
            spacing: theme.space1
            TpSpinner { visible: coopCard.reading }
            TpText {
                Layout.fillWidth: true
                role: "caption"
                visible: text !== ""
                text: coopCard.board === null ? "" : coopCard.board.error || coopCard.board.count
            }
            Repeater {
                model: coopCard.board && coopCard.board.top ? coopCard.board.top : []
                CoopLine {
                    required property var modelData
                    entry: modelData
                }
            }
            TpSectionLabel { visible: coopCard.hasMine; text: i18n.tr("Your Team") }
            CoopLine {
                visible: coopCard.hasMine
                entry: coopCard.hasMine ? coopCard.board.mine : ({})
                mine: true
            }
        }
        footer: TpButton {
            objectName: "coopBoard"
            visible: coopCard.board === null && !coopCard.reading
            flat: true
            size: "sm"
            text: i18n.tr("Leaderboard")
            onClicked: backend.readCoopBoard(coopCard.event.key)
        }
    }

    component CoopLine: RowLayout {
        id: coopLine
        property var entry: ({})
        property bool mine: false
        Layout.fillWidth: true
        spacing: theme.space2
        TpText {
            role: "numeric"
            font.weight: Font.DemiBold
            text: coopLine.entry.position || ""
            Layout.preferredWidth: theme.em * 3
        }
        TpText {
            Layout.fillWidth: true
            text: Js.joined([coopLine.entry.team, coopLine.entry.drivers])
            font.weight: coopLine.mine ? Font.DemiBold : Font.Normal
        }
        TpText { role: "caption"; text: coopLine.entry.vehicleClass || "" }
        TpText {
            role: "numeric"
            text: coopLine.entry.fastest || ""
            ToolTip.visible: fastArea.containsMouse
            ToolTip.text: i18n.tr("Fastest lap")
                          + (coopLine.entry.average ? " · " + i18n.tr("Average lap") + " " + coopLine.entry.average : "")
            MouseArea { id: fastArea; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }
    }

    // Hosted server: lock when it has a password, players, session, track, classes, region, not owned
    component ServerRow: Item {
        id: serverRow
        required property var modelData
        required property int index
        readonly property var server: modelData
        signal menuRequested(string key, Item row, point at)
        objectName: "serverRow"
        Layout.fillWidth: true
        implicitHeight: Math.max(theme.rowTall, rowLayout.implicitHeight + theme.space3 * 2)
        TpListRow { anchors.fill: parent; striped: serverRow.index % 2 === 1; hovered: serverArea.containsMouse }
        ToolTip.visible: serverArea.containsMouse && !playersArea.containsMouse
        ToolTip.text: i18n.tr("Driver stats, recorded laps & race calculator of this track")
        ToolTip.delay: theme.tipDelay
        MouseArea {  // under the row: menu below it, as a race row
            id: serverArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: serverRow.menuRequested(serverRow.server.key, serverRow,
                                               Qt.point(theme.space3, serverRow.height + theme.space1))
        }
        RowLayout {
            id: rowLayout
            anchors.fill: parent
            anchors.leftMargin: theme.space3
            anchors.rightMargin: theme.space3
            spacing: theme.space3
            Item {  // password: lock (same slot on every row: names aligned)
                Layout.preferredWidth: theme.em * 1.2
                implicitHeight: lockIcon.implicitHeight
                Icon {
                    id: lockIcon
                    anchors.centerIn: parent
                    glyph: serverRow.server.password ? theme.glyphs.lock : ""
                    fallback: serverRow.server.password ? "L" : ""
                    color: theme.dimText
                    Accessible.name: serverRow.server.password ? i18n.tr("Password") : ""
                }
            }
            Item {  // track logo (same slot on every row)
                Layout.preferredWidth: theme.em * 4
                implicitHeight: theme.em * 1.8
                GameLogo {
                    anchors.centerIn: parent
                    source: serverRow.server.trackLogo || ""
                    boxWidth: theme.em * 4
                    boxHeight: theme.em * 1.8
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                TpText { Layout.fillWidth: true; font.weight: Font.DemiBold; text: serverRow.server.name }
                TpText {
                    Layout.fillWidth: true
                    role: "caption"
                    text: Js.joined([serverRow.server.track, serverRow.server.region, serverRow.server.owned])
                }
                TpText {
                    Layout.fillWidth: true
                    role: "caption"
                    visible: text !== ""
                    text: Js.joined([serverRow.server.sessions, serverRow.server.weather])
                }
            }
            ClassBadges {  // classes column, right aligned
                classes: serverRow.server.classes
                layoutDirection: Qt.RightToLeft
                Layout.preferredWidth: theme.em * 11
                Layout.minimumWidth: theme.em * 11
                Layout.maximumWidth: theme.em * 11
            }
            Item {  // session column
                Layout.preferredWidth: theme.em * 6.5
                Layout.minimumWidth: theme.em * 6.5
                implicitHeight: sessionPill.implicitHeight
                Pill { id: sessionPill; anchors.right: parent.right; size: "sm"; text: serverRow.server.session; tint: theme.dimText }
            }
            ColumnLayout {  // players & how full
                Layout.preferredWidth: theme.em * 4.2
                Layout.minimumWidth: theme.em * 4.2
                Layout.maximumWidth: theme.em * 4.2
                spacing: theme.space1
                TpText {
                    Layout.fillWidth: true
                    role: "numeric"
                    horizontalAlignment: Text.AlignRight
                    color: serverRow.server.full ? theme.warning : serverRow.server.empty ? theme.dimText : theme.text
                    text: serverRow.server.players
                    ToolTip.visible: playersArea.containsMouse
                    ToolTip.text: serverRow.server.full ? i18n.tr("Full") : i18n.tr("Players")
                    MouseArea { id: playersArea; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                }
                TpMeter {
                    Layout.fillWidth: true
                    visible: serverRow.server.fill > 0
                    value: serverRow.server.fill
                    tint: serverRow.server.full ? theme.warning : theme.accent
                    animated: false
                    name: i18n.tr("Players")
                }
            }
        }
    }
}
