import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Home page: status on top (a slim line when all is well, none on track then: the game card tells; else a banner:
// verdict & its action, the other checks; update told there once out), then cards: game (in a session only, whole
// row: place, lap & time left in big type, live calculator, director & overlay lock at hand), driver (ranks in big
// type & over time, badge, race record, ranks read again when old), overlays (preset loaded & its switch, lock,
// overlays & modules on), last session (best lap in big type, lap times as bars, corners to work on & goal), this
// week (driving time of each day), next online races your Safety Rank opens (live countdown, register), quick
// access (tools & actions not in the navigation bar). Cards open their page: click, or Tab then Enter / Space. Cards
// read in background keep their place (loading) until read, then fade in: the grid never jumps. Cards follow page
// width in 1 to 3 columns, placed row by row (placeCards: spans fill each row whichever cards are shown, no hole),
// the page scrolls when taller than the window.
TpPage {
    id: page

    readonly property int columns: width >= theme.bpWide ? 3 : width >= theme.bpCompact ? 2 : 1
    readonly property bool compact: width < theme.bpCompact
    readonly property var header: backend.header
    readonly property var status: backend.status
    readonly property var game: backend.game
    readonly property var overlay: backend.overlay
    readonly property var preset: backend.preset
    readonly property var counts: backend.counts
    readonly property var last: backend.lastSession
    readonly property var debrief: backend.debrief
    readonly property var driver: backend.driver
    readonly property var loading: backend.loading
    readonly property var week: backend.week
    readonly property var races: backend.races
    readonly property bool inSession: (game.track || "") !== ""
    // Cards shown (from data, never from .visible): placeCards fills each row of the grid
    readonly property bool weekShown: (loading.week === true && week.summary === undefined) || week.summary !== undefined
    readonly property bool driverShown: driver.name !== undefined || loading.driver === true
    readonly property bool lastShown: (last.track || "") !== ""
    readonly property bool racesShown: (races.rows || []).length > 0
    // Status: slim line when nothing is to fix, none on track with nothing to fix (the game card tells the session)
    readonly property bool bannerSlim: (status.level === "success" || status.level === "live")
                                       && (status.rows || []).length === 0
    readonly property bool bannerShown: (status.title || "") !== "" && !(status.level === "live" && bannerSlim)
    readonly property bool updateOut: header.update === "available"
    readonly property var places: placeCards(columns, inSession, driverShown, lastShown, weekShown, racesShown)
    property real now: Date.now() / 1000  // seconds: countdown of races starting soon
    property int rankHovered: 0  // rank tiles under the mouse: their tooltip, not the driver card one
    property int lastHovered: 0  // date & lap bars under the mouse: their tooltip, not the last session card one
    property int weekHovered: 0  // day bars under the mouse: their tooltip, not the week card one

    function levelColor(level) {
        return level === "error" ? theme.loss : level === "warning" ? theme.warning
             : level === "success" || level === "live" ? theme.gain : theme.accent
    }
    function levelGlyph(level) {
        return level === "success" ? "" : level === "info" ? "" : ""  // check, info, warning
    }
    function levelFallback(level) {
        return level === "success" ? "✓" : level === "info" ? "i" : "!"
    }
    function joined(parts) {
        return parts.filter(function(part) { return part !== undefined && part !== "" }).join(" · ")
    }
    // Value of the theme kind (backend gives one for dark pages, one for light ones)
    function themed(dark, light) {
        return theme.dark ? dark : light
    }
    function rankColor(row) {
        return page.themed(row.color, row.lightColor) || theme.text
    }
    // Grid places of the cards (row, column, span): cards in reading order, each row filled (the last card of a row
    // widened over a hole); 2 columns: overlays & this week side by side
    function placeCards(columns, game, driver, last, week, races) {
        var wanted = columns === 2
            ? [["game", 2, game], ["driver", 2, driver], ["overlays", 1, true], ["week", 1, week], ["last", 2, last],
               ["races", 2, races]]
            : [["game", 3, game], ["driver", 2, driver], ["overlays", 1, true], ["last", 2, last], ["week", 1, week],
               ["races", 3, races]]
        var places = {}
        var row = 0
        var column = 0
        var previous = ""
        for (var index = 0; index < wanted.length; ++index) {
            if (!wanted[index][2])
                continue
            var span = Math.min(wanted[index][1], columns)
            if (column + span > columns) {  // no room left: row closed, its last card widened
                places[previous].span += columns - column
                row += 1
                column = 0
            }
            previous = wanted[index][0]
            places[previous] = {"row": row, "column": column, "span": span}
            column += span
            if (column >= columns) {
                row += 1
                column = 0
            }
        }
        if (column > 0)
            places[previous].span += columns - column
        return places
    }
    function place(name) {
        return page.places[name] || {"row": 0, "column": 0, "span": 1}
    }
    // Width of a card over span columns: set, not left to the grid (a column only spanned, never filled by a card
    // of its own, would collapse)
    function cardWidth(name) {
        var span = page.place(name).span
        var cell = (column.width - theme.space4 * (page.columns - 1)) / page.columns
        return cell * span + theme.space4 * (span - 1)
    }
    // Time to a race start: minutes & seconds within 10 minutes (live), else as the backend tells it
    function countdown(row) {
        var left = Math.floor(row.startTime - page.now)
        if (row.running === true || left <= 0 || left > 600)
            return row.until
        return i18n.tr("in %1").replace("%1", Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0"))
    }

    Timer {  // countdown of races starting soon, while the page shows them
        interval: 1000
        repeat: true
        running: backend.shown && page.racesShown
        triggeredOnStart: true
        onTriggered: page.now = Date.now() / 1000
    }

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight + theme.padPage * 2
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: column
            x: theme.padPage
            y: theme.padPage
            width: flick.width - theme.padPage * 2
            spacing: theme.space4

            // Status: verdict (ready, or the most important check) & its action, the other checks, update once out.
            // Slim line on the card surface when all is well; tinted banner when something is to fix or to know.
            Card {
                id: banner
                objectName: "statusBanner"
                readonly property string level: page.status.level || "info"
                readonly property color tone: page.levelColor(level)
                readonly property bool tinted: !page.bannerSlim && level !== "success" && level !== "live"
                readonly property real inset: page.bannerSlim ? theme.space3 : theme.padCard
                visible: page.bannerShown
                Layout.fillWidth: true
                implicitHeight: bannerColumn.implicitHeight + inset * 2
                color: tinted ? Qt.tint(theme.surfaceCard, theme.tint(tone, "subtle")) : theme.surfaceCard
                border.color: tinted ? theme.tint(tone, "strong") : theme.strokeSubtle
                Accessible.role: Accessible.Grouping
                Accessible.name: page.status.title || ""

                ColumnLayout {
                    id: bannerColumn
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: banner.inset }
                    spacing: theme.space3

                    GridLayout {  // verdict, its action & update (under it on a narrow page)
                        Layout.fillWidth: true
                        columns: page.compact ? 1 : 2
                        columnSpacing: theme.space5
                        rowSpacing: theme.space3
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: page.bannerSlim ? theme.space3 : theme.space4
                            Item {  // level: live dot, else icon (with the title: never color alone)
                                Layout.preferredWidth: Math.round(theme.em * (page.bannerSlim ? 1 : 1.6))
                                Layout.preferredHeight: Layout.preferredWidth
                                Layout.alignment: page.bannerSlim ? Qt.AlignVCenter : Qt.AlignTop
                                TpPulseDot {
                                    anchors.centerIn: parent
                                    width: Math.round(theme.em * 0.8)
                                    visible: banner.level === "live"
                                    color: banner.tone
                                    pulsing: visible
                                }
                                Icon {
                                    anchors.centerIn: parent
                                    visible: banner.level !== "live"
                                    glyph: page.levelGlyph(banner.level)
                                    fallback: page.levelFallback(banner.level)
                                    color: banner.tone
                                    size: page.bannerSlim ? theme.iconSm : theme.iconLg
                                }
                            }
                            GridLayout {  // title & text: one line when slim
                                Layout.fillWidth: true
                                columns: page.bannerSlim && !page.compact ? 2 : 1
                                columnSpacing: theme.space3
                                rowSpacing: theme.space1
                                TpText {
                                    objectName: "statusTitle"
                                    Layout.fillWidth: !page.bannerSlim
                                    role: page.bannerSlim ? "body" : "title"
                                    font.weight: Font.DemiBold
                                    wrap: true
                                    text: page.status.title || ""
                                    Accessible.role: Accessible.Heading
                                    Accessible.name: text
                                }
                                TpText {
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    color: theme.dimText
                                    wrap: true
                                    text: page.status.text || ""
                                }
                            }
                        }
                        Row {  // action following the verdict, update once out (told here only)
                            Layout.alignment: page.compact ? Qt.AlignLeft : Qt.AlignRight | Qt.AlignVCenter
                            spacing: theme.space3
                            TpButton {
                                objectName: "statusAction"
                                visible: (page.status.actionText || "") !== ""
                                text: page.status.actionText || ""
                                size: page.bannerSlim ? "sm" : "md"
                                accent: true
                                onClicked: backend.runCheck(page.status.action)
                            }
                            TpButton {
                                objectName: "updateButton"
                                visible: page.updateOut
                                size: "sm"
                                accent: true
                                glyph: ""  // sync
                                text: i18n.tr("Update Available") + " · v" + (page.header.latest || "")
                                tip: i18n.tr("See Update")
                                onClicked: backend.updateAction()
                            }
                        }
                    }

                    Repeater {  // other checks, most important first
                        model: page.status.rows || []
                        CheckRow {}
                    }
                }
            }

            // Cards, placed by placeCards
            GridLayout {
                Layout.fillWidth: true
                columns: page.columns
                columnSpacing: theme.space4
                rowSpacing: theme.space4

                TpSectionCard {  // game & session, on track only: whole row (place, lap, time left, actions at hand)
                    fillContent: false  // content under the header, footer buttons at the bottom
                    objectName: "gameCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.row: page.place("game").row
                    Layout.column: page.place("game").column
                    Layout.columnSpan: page.place("game").span
                    Layout.preferredWidth: page.cardWidth("game")
                    Layout.maximumWidth: page.cardWidth("game")
                    visible: page.inSession
                    glyph: ""  // game controller
                    fallback: "G"
                    title: i18n.tr("Game")
                    clickable: true
                    tip: i18n.tr("API settings of the game")
                    onOpened: backend.openGameSettings()
                    trailing: [
                        GameLogo { source: page.game.trackLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 1.8 },
                        GameLogo { source: page.game.brandLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 1.8 }
                    ]
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: theme.space3
                        TpPulseDot {
                            Layout.preferredWidth: Math.round(theme.em * 0.6)
                            Layout.preferredHeight: Layout.preferredWidth
                            color: page.game.running ? theme.gain : theme.dimText
                            pulsing: page.game.running === true
                            Layout.alignment: Qt.AlignVCenter
                        }
                        TpText {
                            Layout.fillWidth: true
                            role: "subtitle"
                            text: page.joined([page.game.track, page.game.session])
                        }
                    }
                    Flow {  // key figures in big type
                        objectName: "sessionFigures"
                        Layout.fillWidth: true
                        spacing: theme.space6
                        Figure {
                            visible: (page.game.position || "") !== ""
                            value: page.game.position || ""
                            suffix: page.game.total || ""
                            label: i18n.tr("Position")
                        }
                        Figure {
                            value: page.game.lap || ""
                            label: page.game.vehicle || ""
                        }
                        Figure {
                            visible: (page.game.timeLeft || "") !== ""
                            value: page.game.timeLeft || ""
                            label: i18n.tr("Time left")
                        }
                    }
                    Flow {  // actions at hand (wrap on a narrow page)
                        objectName: "sessionActions"
                        Layout.fillWidth: true
                        Layout.topMargin: theme.space2
                        spacing: theme.space3
                        TpButton {
                            size: "sm"
                            glyph: ""  // calculator
                            fallback: "="
                            text: i18n.tr("Live Calculator")
                            tip: i18n.tr("Race Calculator on its Live tab")
                            onClicked: backend.openLiveCalculator()
                        }
                        TpButton {
                            visible: page.game.lmu === true
                            size: "sm"
                            glyph: ""  // sliders
                            fallback: "B"
                            text: i18n.tr("Broadcast Director")
                            onClicked: backend.openDirector()
                        }
                        TpButton {  // the overlay lock of the session (the overlays card leaves it out on track)
                            size: "sm"
                            accent: true
                            glyph: page.overlay.locked ? theme.glyphs.lock : theme.glyphs.unlock  // state shown
                            fallback: page.overlay.locked ? "L" : "U"
                            text: page.overlay.locked ? i18n.tr("Unlock Overlay") : i18n.tr("Lock Overlay")
                            onClicked: backend.toggleLock()
                        }
                    }
                }

                TpSectionCard {  // driver: ranks in big type & over time, badge, race record (read in background)
                    id: driverCard
                    objectName: "driverCard"
                    fillContent: false  // content under the header
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.row: page.place("driver").row
                    Layout.column: page.place("driver").column
                    Layout.columnSpan: page.place("driver").span
                    Layout.preferredWidth: page.cardWidth("driver")
                    Layout.maximumWidth: page.cardWidth("driver")
                    readonly property bool waiting: page.loading.driver === true && page.driver.name === undefined
                    visible: page.driverShown
                    glyph: ""  // contact
                    fallback: "D"
                    title: i18n.tr("Driver")
                    clickable: true
                    tip: page.rankHovered > 0 ? "" : i18n.tr("Open driver stats")
                    onOpened: backend.openDriverStats()
                    TpStateView {
                        objectName: "driverLoading"
                        Layout.alignment: Qt.AlignHCenter
                        loading: driverCard.waiting
                        compact: true
                    }
                    ColumnLayout {  // once read: faded in
                        objectName: "driverBody"
                        Layout.fillWidth: true
                        visible: !driverCard.waiting
                        opacity: visible ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: theme.motionBase; easing.type: Easing.OutCubic } }
                        spacing: theme.space4
                        RowLayout {  // name, nationality, team & number; game badge on the right
                            Layout.fillWidth: true
                            spacing: theme.space4
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: theme.space1
                                TpText {
                                    objectName: "driverName"
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    role: "title"
                                    text: page.driver.name || ""
                                }
                                RowLayout {  // flag of game profile nationality, then country, team & number
                                    Layout.fillWidth: true
                                    visible: identityText.text !== ""
                                    spacing: theme.space2
                                    TpFlag { flag: page.driver.flag || ({}) }
                                    TpText {
                                        id: identityText
                                        Layout.fillWidth: true
                                        color: theme.dimText
                                        text: page.driver.identity || ""
                                    }
                                }
                            }
                            RowLayout {  // game badge in its color
                                readonly property var badge: page.driver.badge || {}
                                visible: (badge.name || "") !== ""
                                Layout.alignment: Qt.AlignTop | Qt.AlignRight
                                spacing: theme.space2
                                Image {
                                    source: parent.badge.icon || ""
                                    visible: status === Image.Ready
                                    Layout.preferredWidth: Math.round(theme.em * 1.6)
                                    Layout.preferredHeight: Layout.preferredWidth
                                    sourceSize.height: Math.ceil(theme.em * 1.6 * Screen.devicePixelRatio)
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                }
                                TpText {
                                    role: "subtitle"
                                    text: parent.badge.name || ""
                                    color: page.themed(parent.badge.color, parent.badge.lightColor) || theme.text
                                }
                            }
                        }
                        GridLayout {  // Driver Rank & Safety Rank side by side (one under the other on a narrow page)
                            objectName: "rankTiles"
                            Layout.fillWidth: true
                            visible: (page.driver.ranks || []).length > 0
                            columns: page.compact || (page.driver.ranks || []).length < 2 ? 1 : 2
                            columnSpacing: theme.space6
                            rowSpacing: theme.space4
                            uniformCellWidths: true
                            Repeater {
                                model: page.driver.ranks || []
                                RankTile {}
                            }
                        }
                        Flow {  // race record of results files
                            Layout.fillWidth: true
                            visible: (page.driver.figures || []).length > 0
                            spacing: theme.space5
                            Repeater {
                                model: page.driver.figures || []
                                Figure {
                                    required property var modelData
                                    small: true
                                    value: modelData.value
                                    label: modelData.label
                                }
                            }
                        }
                        RowLayout {  // ranks remembered: how long ago (clock & warning color once old), read again
                            objectName: "driverNote"
                            readonly property bool stale: page.driver.noteStale === true
                            visible: (page.driver.note || "") !== ""
                            Layout.fillWidth: true
                            spacing: theme.space2
                            Icon {
                                visible: parent.stale
                                glyph: ""  // clock
                                fallback: "⏱"
                                color: theme.warning
                                size: theme.iconSm
                            }
                            TpText {
                                Layout.fillWidth: true
                                role: "caption"
                                color: parent.stale ? theme.warning : theme.dimText
                                text: page.driver.note || ""
                                HoverHandler {
                                    id: noteHover
                                    onHoveredChanged: page.rankHovered += hovered ? 1 : -1
                                }
                                TpToolTip {
                                    visible: noteHover.hovered && (page.driver.noteTip || "") !== ""
                                    text: page.driver.noteTip || ""
                                    delay: theme.tipDelay
                                }
                            }
                            TpButton {
                                objectName: "refreshRanks"
                                visible: page.driver.refresh === true
                                flat: true
                                size: "xs"
                                glyph: ""  // sync
                                text: i18n.tr("Refresh")
                                tip: i18n.tr("Read your ranks again from RaceControl")
                                onClicked: backend.refreshRanks()
                            }
                        }
                        Repeater {  // other game accounts of this computer
                            model: page.driver.others || []
                            TpText {
                                required property var modelData
                                Layout.fillWidth: true
                                role: "caption"
                                wrap: true
                                text: modelData.name + i18n.colon() + page.joined(modelData.ranks.map(function(rank) {
                                    return rank.label + " " + rank.value
                                }).concat([modelData.badge.name || ""])) + " (" + modelData.when + ")"
                            }
                        }
                    }
                }

                TpSectionCard {  // overlays: preset loaded & its switch, lock, overlays & modules on
                    id: overlaysCard
                    objectName: "overlaysCard"
                    fillContent: false  // content under the header, footer buttons at the bottom
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.row: page.place("overlays").row
                    Layout.column: page.place("overlays").column
                    Layout.columnSpan: page.place("overlays").span
                    Layout.preferredWidth: page.cardWidth("overlays")
                    Layout.maximumWidth: page.cardWidth("overlays")
                    glyph: page.overlay.locked ? theme.glyphs.lock : theme.glyphs.unlock
                    fallback: page.overlay.locked ? "L" : "U"
                    title: i18n.tr("Overlays")
                    clickable: true
                    tip: i18n.tr("Open overlays")
                    onOpened: backend.openPage("widget")
                    ColumnLayout {  // preset loaded
                        objectName: "presetBlock"
                        Layout.fillWidth: true
                        spacing: theme.space1
                        TpText { role: "overline"; text: i18n.tr("Preset") }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: theme.space3
                            TpText {
                                objectName: "presetName"
                                Layout.fillWidth: true
                                role: "subtitle"
                                text: page.preset.name || ""
                            }
                            Pill {
                                visible: page.preset.locked === true
                                text: i18n.tr("Locked")
                                glyph: theme.glyphs.lock
                                tint: theme.dimText
                            }
                        }
                        TpText {
                            Layout.fillWidth: true
                            role: "caption"
                            wrap: true
                            text: page.preset.autoLoad ? i18n.tr("Primary preset loads automatically")
                                                       : i18n.tr("Primary preset auto load off")
                        }
                    }
                    ColumnLayout {  // lock & what is on
                        Layout.fillWidth: true
                        Layout.topMargin: theme.space2
                        spacing: theme.space2
                        TpText {
                            Layout.fillWidth: true
                            font.weight: Font.DemiBold
                            wrap: true
                            text: page.overlay.locked ? i18n.tr("Locked")
                                                      : i18n.tr("Unlocked") + " · " + i18n.tr("Drag overlays to move them")
                        }
                        Flow {  // how many are on (no share bar: nothing to fill up)
                            Layout.fillWidth: true
                            spacing: theme.space6
                            Figure { small: true; value: String(page.counts.overlays || 0); label: i18n.tr("Active overlays") }
                            Figure { small: true; value: String(page.counts.modules || 0); label: i18n.tr("Active modules") }
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: theme.space2
                            visible: page.overlay.autoHide === true || page.overlay.vr === true
                            Pill { visible: page.overlay.autoHide === true; text: i18n.tr("Auto Hide") }
                            Pill { visible: page.overlay.vr === true; text: i18n.tr("VR Compatibility") }
                        }
                    }
                    footer: [
                        TpButton {
                            id: switchButton
                            text: i18n.tr("Switch Preset")
                            glyph: ""  // chevron down
                            size: "sm"
                            tip: i18n.tr("Load another preset")
                            onClicked: {
                                if (!presetMenu.visible)
                                    presetMenu.rows = backend.presetList()  // newest presets when opened
                                presetMenu.toggleBelow(switchButton)
                            }
                        },
                        TpButton {  // Modules category of Settings
                            objectName: "openModules"
                            flat: true
                            size: "sm"
                            text: i18n.tr("Modules")
                            tip: i18n.tr("Open modules")
                            onClicked: backend.runCheck("modules")
                        },
                        TpButton {  // on track: in the game card
                            visible: !page.inSession
                            text: page.overlay.locked ? i18n.tr("Unlock Overlay") : i18n.tr("Lock Overlay")
                            accent: true
                            size: "sm"
                            onClicked: backend.toggleLock()
                        }
                    ]
                }

                TpSectionCard {  // last driven session & its debrief (read in background: place kept meanwhile)
                    id: lastCard
                    objectName: "lastSessionCard"
                    fillContent: false  // content under the header, footer buttons at the bottom
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.row: page.place("last").row
                    Layout.column: page.place("last").column
                    Layout.columnSpan: page.place("last").span
                    Layout.preferredWidth: page.cardWidth("last")
                    Layout.maximumWidth: page.cardWidth("last")
                    readonly property bool debriefShown: page.debrief.figures !== undefined
                    visible: page.lastShown
                    glyph: ""  // history
                    fallback: "H"
                    title: i18n.tr("Last Session")
                    clickable: true
                    tip: page.lastHovered > 0 ? "" : i18n.tr("Driver stats of this track & car")
                    onOpened: backend.openLastSession()
                    trailing: [
                        GameLogo { source: page.last.trackLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 1.8 },
                        GameLogo { source: page.last.brandLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 1.8 }
                    ]
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: theme.space3
                        TpText {
                            Layout.fillWidth: true
                            role: "subtitle"
                            text: page.last.track || ""
                        }
                        Pill {
                            visible: (page.last.result || "") !== ""
                            text: page.last.result || ""
                        }
                    }
                    TpText {  // vehicle, session, best lap (when no debrief tells it), how long ago (date in tooltip)
                        objectName: "lastSessionDetail"
                        Layout.fillWidth: true
                        color: theme.dimText
                        wrap: true
                        text: page.joined([page.last.vehicle, page.last.session,
                                           !lastCard.debriefShown && page.last.best ? i18n.tr("Best") + " " + page.last.best : "",
                                           page.last.date])
                        HoverHandler {
                            id: dateHover
                            onHoveredChanged: page.lastHovered += hovered ? 1 : -1
                        }
                        TpToolTip {
                            visible: dateHover.hovered && (page.last.dateTip || "") !== ""
                            text: page.last.dateTip || ""
                            delay: theme.tipDelay
                        }
                    }
                    TpStateView {  // debrief being read: its place kept
                        objectName: "debriefLoading"
                        Layout.alignment: Qt.AlignHCenter
                        loading: page.loading.debrief === true && !lastCard.debriefShown
                        compact: true
                    }
                    ColumnLayout {  // debrief: best lap & personal best, lap times, corners to work on, goal
                        objectName: "debriefBlock"
                        Layout.fillWidth: true
                        visible: lastCard.debriefShown
                        opacity: visible ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: theme.motionBase; easing.type: Easing.OutCubic } }
                        spacing: theme.space3
                        GridLayout {  // best lap in big type; lap times of the stint as bars beside it (under it if narrow)
                            Layout.fillWidth: true
                            Layout.topMargin: theme.space2
                            columns: page.compact || (page.debrief.laps || []).length < 2 ? 1 : 2
                            columnSpacing: theme.space6
                            rowSpacing: theme.space3
                            uniformCellWidths: true
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignTop
                                spacing: theme.space1
                                TpText { role: "overline"; text: i18n.tr("Best Lap") }
                                TpText {
                                    objectName: "debriefBest"
                                    role: "display"
                                    tabular: true
                                    text: (page.debrief.best || "") !== "" ? page.debrief.best : (page.debrief.track || "")
                                }
                                Pill {
                                    visible: page.debrief.personal === "new"
                                    text: page.debrief.personalText || ""
                                    glyph: ""  // star
                                    tint: theme.gain
                                }
                                TpText {
                                    visible: page.debrief.personal === "slower"
                                    color: theme.dimText
                                    tabular: true
                                    text: page.debrief.personalText || ""
                                }
                                TpText {
                                    Layout.fillWidth: true
                                    Layout.topMargin: theme.space1
                                    role: "caption"
                                    tabular: true
                                    wrap: true
                                    text: (page.debrief.figures || []).join(" · ")
                                }
                            }
                            LapBars {
                                objectName: "lapBars"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.minimumHeight: theme.em * 4
                                visible: bars.length > 1
                                bars: page.debrief.laps || []
                            }
                        }
                        TpSectionLabel {
                            Layout.fillWidth: true
                            Layout.topMargin: theme.space2
                            visible: (page.debrief.tips || []).length > 0
                            text: i18n.tr("Work on") + " · " + (page.debrief.against || "")
                        }
                        Repeater {
                            model: page.debrief.tips || []
                            CornerTipRow {}
                        }
                        ColumnLayout {  // lap time goal of driver stats page
                            id: goalBlock
                            objectName: "goalBlock"
                            Layout.fillWidth: true
                            Layout.topMargin: theme.space2
                            visible: (page.debrief.goal || {}).goal !== undefined
                            spacing: theme.space2
                            readonly property var goal: page.debrief.goal || {}
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: theme.space3
                                Icon {
                                    glyph: ""  // target
                                    fallback: "◎"
                                    color: goalBlock.goal.state === "reached" ? theme.gain : theme.accent
                                }
                                TpText {
                                    font.weight: Font.DemiBold
                                    tabular: true
                                    text: i18n.tr("Goal") + " " + (goalBlock.goal.goal || "")
                                }
                                TpText {
                                    Layout.fillWidth: true
                                    tabular: true
                                    text: goalBlock.goal.state === "reached" ? "✓ " + i18n.tr("reached") : (goalBlock.goal.gap || "")
                                    color: goalBlock.goal.state === "reached" ? theme.gain : theme.dimText
                                    font.weight: goalBlock.goal.state === "reached" ? Font.DemiBold : Font.Normal
                                }
                                TpText {
                                    visible: text !== ""
                                    color: theme.dimText
                                    tabular: true
                                    text: goalBlock.goal.percent || ""
                                }
                            }
                            TpMeter {
                                Layout.fillWidth: true
                                visible: (goalBlock.goal.ratio === undefined ? -1 : goalBlock.goal.ratio) >= 0
                                value: Math.max(goalBlock.goal.ratio || 0, 0)
                                tint: goalBlock.goal.state === "reached" ? theme.gain : theme.accent
                                name: i18n.tr("Goal")
                            }
                        }
                    }
                    footer: TpButton {
                        visible: page.debrief.canOpen === true
                        text: i18n.tr("Open Telemetry")
                        glyph: ""  // area chart
                        size: "sm"
                        onClicked: backend.openDebrief()
                    }
                }

                TpSectionCard {  // last 7 days (as on Driver Stats): place kept while read, none when nothing driven
                    id: weekCard
                    objectName: "weekCard"
                    fillContent: false  // content under the header
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.row: page.place("week").row
                    Layout.column: page.place("week").column
                    Layout.columnSpan: page.place("week").span
                    Layout.preferredWidth: page.cardWidth("week")
                    Layout.maximumWidth: page.cardWidth("week")
                    readonly property bool waiting: page.loading.week === true && page.week.summary === undefined
                    visible: page.weekShown
                    glyph: ""  // calendar
                    fallback: "W"
                    title: i18n.tr("This Week")
                    clickable: true
                    tip: page.weekHovered > 0 ? "" : i18n.tr("Open driver stats")
                    onOpened: backend.openDriverStats()
                    TpStateView {
                        objectName: "weekLoading"
                        Layout.alignment: Qt.AlignHCenter
                        loading: weekCard.waiting
                        compact: true
                    }
                    ColumnLayout {  // once read: faded in
                        Layout.fillWidth: true
                        visible: !weekCard.waiting && page.week.summary !== undefined
                        opacity: visible ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: theme.motionBase; easing.type: Easing.OutCubic } }
                        spacing: theme.space3
                        TpText {  // sessions, driving time, laps
                            Layout.fillWidth: true
                            role: "numeric"
                            font.weight: Font.DemiBold
                            wrap: true
                            text: page.week.summary || ""
                        }
                        DayBars {
                            objectName: "dayBars"
                            Layout.fillWidth: true
                            Layout.preferredHeight: theme.em * 4.5
                            visible: days.length > 0
                            days: page.week.days || []
                        }
                        Flow {  // goals reached, new personal bests, goals within reach: icon & words, not color alone
                            Layout.fillWidth: true
                            spacing: theme.space2
                            Repeater {
                                model: page.week.highlights || []
                                Pill {
                                    required property var modelData
                                    glyph: modelData.glyph
                                    fallback: modelData.kind === "goal_near" ? "◎" : modelData.kind === "record" ? "★" : "✓"
                                    text: modelData.text
                                    tint: modelData.tone === "gain" ? theme.gain : theme.accent
                                }
                            }
                        }
                    }
                }

                TpSectionCard {  // next online races your Safety Rank opens (RaceControl): whole row
                    objectName: "racesCard"
                    fillContent: false
                    Layout.fillWidth: true
                    Layout.row: page.place("races").row
                    Layout.column: page.place("races").column
                    Layout.columnSpan: page.place("races").span
                    Layout.preferredWidth: page.cardWidth("races")
                    Layout.maximumWidth: page.cardWidth("races")
                    visible: page.racesShown
                    glyph: ""  // calendar
                    fallback: "R"
                    title: i18n.tr("Next Races")
                    clickable: true
                    tip: i18n.tr("Open upcoming races")
                    onOpened: backend.openRaces()
                    GridLayout {
                        Layout.fillWidth: true
                        columns: page.columns
                        columnSpacing: theme.space5
                        rowSpacing: theme.space3
                        uniformCellWidths: true
                        Repeater {
                            model: page.races.rows || []
                            // One race: start & time to it (live within 10 min), reminder; title; track logo & name;
                            // classes, tier & length; your place this week, registered or register
                            Rectangle {
                                id: raceItem
                                objectName: "nextRace"
                                required property var modelData
                                readonly property bool soon: modelData.soon === true || modelData.running === true
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                implicitHeight: raceColumn.implicitHeight + theme.space3 * 2
                                radius: theme.radiusMd
                                color: theme.surfaceSunken
                                border.width: soon ? 1 : 0  // starting soon: told by the time pill too
                                border.color: theme.tint(theme.accent, "strong")
                                ColumnLayout {
                                    id: raceColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: theme.space3
                                    spacing: theme.space1
                                    RowLayout {  // start, title & track; track logo on the right
                                        Layout.fillWidth: true
                                        spacing: theme.space3
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: theme.space1
                                            RowLayout {  // start, time to it, reminder set
                                                Layout.fillWidth: true
                                                spacing: theme.space2
                                                TpText {
                                                    role: "title"
                                                    tabular: true
                                                    text: raceItem.modelData.start
                                                }
                                                Pill {
                                                    objectName: "raceCountdown"
                                                    visible: text !== ""
                                                    size: "sm"
                                                    text: page.countdown(raceItem.modelData)
                                                    dot: raceItem.modelData.running === true || raceItem.modelData.imminent === true
                                                    pulsing: dot
                                                    tint: raceItem.modelData.running === true ? theme.gain
                                                          : raceItem.modelData.soon === true ? theme.accent : theme.dimText
                                                }
                                                Pill {
                                                    visible: (raceItem.modelData.reminder || 0) > 0
                                                    size: "sm"
                                                    glyph: ""  // bell
                                                    fallback: "!"
                                                    text: i18n.tr("%1 min").replace("%1", raceItem.modelData.reminder || 0)
                                                    tint: theme.accent
                                                    tip: i18n.tr("Reminder set")
                                                }
                                                Item { Layout.fillWidth: true }
                                            }
                                            TpText {
                                                Layout.fillWidth: true
                                                role: "subtitle"
                                                text: raceItem.modelData.title
                                            }
                                            TpText {
                                                Layout.fillWidth: true
                                                text: raceItem.modelData.track
                                            }
                                        }
                                        GameLogo {
                                            Layout.alignment: Qt.AlignTop | Qt.AlignRight
                                            source: raceItem.modelData.trackLogo || ""
                                            boxWidth: theme.em * 5
                                            boxHeight: theme.em * 2.6
                                        }
                                    }
                                    Flow {  // classes, tier & race length
                                        Layout.fillWidth: true
                                        spacing: theme.space2
                                        Repeater {
                                            id: classBadges
                                            model: raceItem.modelData.classes || []
                                            TpClassBadge {
                                                required property var modelData
                                                label: modelData.label
                                                fullName: modelData.full
                                                fill: modelData.color
                                            }
                                        }
                                        TpText {  // centered on the badges
                                            role: "caption"
                                            height: Math.max(implicitHeight, classBadges.count > 0 && classBadges.itemAt(0)
                                                                             ? classBadges.itemAt(0).height : 0)
                                            verticalAlignment: Text.AlignVCenter
                                            text: page.joined([raceItem.modelData.tierText, raceItem.modelData.length])
                                        }
                                    }
                                    Flow {  // your place in the weekly leaderboard, registered, else register
                                        Layout.fillWidth: true
                                        Layout.topMargin: theme.space1
                                        visible: (raceItem.modelData.place || "") !== "" || raceItem.modelData.registeredMe === true
                                                 || raceItem.modelData.canRegister === true
                                        spacing: theme.space2
                                        Pill {
                                            visible: (raceItem.modelData.place || "") !== ""
                                            size: "sm"
                                            glyph: ""  // flag
                                            fallback: "#"
                                            text: raceItem.modelData.place || ""
                                            tint: theme.accent
                                            tip: i18n.tr("Your place in the weekly leaderboard")
                                        }
                                        Pill {
                                            visible: raceItem.modelData.registeredMe === true
                                            size: "sm"
                                            glyph: ""  // check
                                            fallback: "✓"
                                            text: i18n.tr("Registered")
                                            tint: theme.gain
                                        }
                                        TpButton {  // registration dialog of the Upcoming Races page (car chosen there)
                                            objectName: "registerRace"
                                            visible: raceItem.modelData.canRegister === true
                                            size: "xs"
                                            accent: raceItem.soon
                                            text: i18n.tr("Register…")
                                            tip: i18n.tr("Choose your car and register to this race")
                                            onClicked: backend.registerRace(raceItem.modelData.key)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Quick access: tools & actions chosen by the user (Customize, or right-click), those of the navigation
            // bar left out (one place each)
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: theme.space2
                spacing: theme.space3
                TpSectionLabel { text: i18n.tr("Quick Access") }
                TpButton {
                    flat: true
                    size: "xs"
                    text: i18n.tr("Customize…")
                    tip: i18n.tr("Add, remove or reorder quick access buttons")
                    onClicked: backend.customizeQuick()
                }
                Item { Layout.fillWidth: true }
            }
            GridLayout {
                id: quickGrid
                objectName: "quickGrid"
                Layout.fillWidth: true
                visible: backend.quick.length > 0
                columns: page.columns === 1 ? 1 : page.columns === 2 ? 3 : 5
                columnSpacing: theme.space3
                rowSpacing: theme.space3
                uniformCellWidths: true
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: function(point) { quickMenu.popup() }
                }
                Repeater {
                    model: backend.quick
                    TpButton {
                        required property var modelData
                        Layout.fillWidth: true
                        // a cell wide however few buttons there are (never stretched over the row)
                        Layout.maximumWidth: (column.width - quickGrid.columnSpacing * (quickGrid.columns - 1))
                                             / quickGrid.columns
                        glyph: modelData.glyph
                        fallback: modelData.letter
                        text: modelData.label
                        tip: modelData.shortcut !== "" ? modelData.label + "  " + modelData.shortcut : ""
                        onClicked: backend.runQuick(modelData.key)
                    }
                }
            }
        }
    }

    // Rank of the driver card: name, rank in big type in its color & change since the previous one, progress to
    // the next tier, rank over time; its tooltip tells what the percents mean
    component RankTile: ColumnLayout {
        id: tile
        required property var modelData
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: theme.space1
        HoverHandler {
            id: tileHover
            onHoveredChanged: page.rankHovered += hovered ? 1 : -1
        }
        TpToolTip {
            visible: tileHover.hovered && (tile.modelData.tip || "") !== ""
            text: tile.modelData.tip || ""
            delay: theme.tipDelay
            // A popup (not an item of the layout): placed in the tile, below it
            y: tile.height + theme.space1  // qmllint disable Quick.layout-positioning
        }
        TpText { role: "overline"; text: tile.modelData.label }
        RowLayout {
            Layout.fillWidth: true
            spacing: theme.space3
            TpText {
                objectName: "rankValue"
                role: "display"
                text: tile.modelData.value
                color: page.rankColor(tile.modelData)
            }
            Item { Layout.fillWidth: true }
            TpText {  // change since previous rank: arrow & sign, not color alone
                visible: tile.modelData.change !== ""
                Layout.alignment: Qt.AlignVCenter
                tabular: true
                font.weight: Font.DemiBold
                text: (tile.modelData.changeTone > 0 ? "▲ " : "▼ ") + tile.modelData.change
                color: tile.modelData.changeTone > 0 ? theme.gain : theme.loss
            }
        }
        RowLayout {  // progress to the next tier
            Layout.fillWidth: true
            spacing: theme.space3
            TpMeter {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                value: tile.modelData.progress
                tint: page.rankColor(tile.modelData)
                name: tile.modelData.label
            }
            TpText {
                role: "caption"
                tabular: true
                text: tile.modelData.progressText
            }
        }
        TpRankLine {
            Layout.fillWidth: true
            visible: (tile.modelData.chart || []).length > 1
            points: tile.modelData.chart || []
            tint: page.rankColor(tile.modelData)
            label: tile.modelData.label
        }
    }

    // Lap times of the last session as bars (bottom aligned, right aligned when few): best lap full height in the
    // gain color, slower laps shorter, invalid laps faint; tooltip: lap number & time
    component LapBars: Item {
        id: lapBars
        property var bars: []
        readonly property real gap: Math.max(1, Math.round(theme.em * 0.15))
        readonly property real barWidth: Math.max(2, Math.min(theme.em * 1.2,
            (width - gap * (bars.length - 1)) / Math.max(bars.length, 1)))
        Accessible.role: Accessible.Chart
        Accessible.name: i18n.tr("Lap times")
        Row {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            spacing: lapBars.gap
            Repeater {
                model: lapBars.bars
                Item {
                    id: barCell
                    required property var modelData
                    width: lapBars.barWidth
                    height: lapBars.height
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: Math.max(2, parent.height * barCell.modelData.ratio)
                        radius: Math.min(width / 2, theme.radiusXs)
                        color: barCell.modelData.best ? theme.gain : theme.accent
                        opacity: barCell.modelData.valid ? (barHover.hovered ? 1 : 0.85) : 0.35
                    }
                    HoverHandler {
                        id: barHover
                        onHoveredChanged: page.lastHovered += hovered ? 1 : -1
                    }
                    TpToolTip {
                        visible: barHover.hovered
                        text: barCell.modelData.tip
                        delay: theme.tipDelay
                    }
                }
            }
        }
    }

    // Driving time of each of the last 7 days as bars (longest day full height), today in the accent color, day
    // letter under each; tooltip: day & driving time
    component DayBars: Item {
        id: dayBars
        property var days: []
        Accessible.role: Accessible.Chart
        Accessible.name: i18n.tr("Driving time of each day")
        Row {
            anchors.fill: parent
            spacing: theme.space2
            Repeater {
                model: dayBars.days
                Column {
                    id: dayCell
                    required property var modelData
                    width: (dayBars.width - theme.space2 * (dayBars.days.length - 1)) / Math.max(dayBars.days.length, 1)
                    height: dayBars.height
                    spacing: theme.space1
                    Item {
                        width: parent.width
                        height: parent.height - dayLetter.height - parent.spacing
                        Rectangle {  // driving time (a thin line for a day not driven)
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: dayCell.modelData.ratio > 0 ? Math.max(3, parent.height * dayCell.modelData.ratio) : 2
                            radius: theme.radiusXs
                            color: dayCell.modelData.ratio <= 0 ? theme.strokeSubtle
                                 : dayCell.modelData.today ? theme.accent : theme.tint(theme.accent, "strong")
                        }
                        HoverHandler {
                            id: dayHover
                            onHoveredChanged: page.weekHovered += hovered ? 1 : -1
                        }
                        TpToolTip {
                            visible: dayHover.hovered
                            text: dayCell.modelData.tip
                            delay: theme.tipDelay
                        }
                    }
                    TpText {
                        id: dayLetter
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        role: "caption"
                        font.weight: dayCell.modelData.today ? Font.DemiBold : Font.Normal
                        color: dayCell.modelData.today ? theme.text : theme.dimText
                        text: dayCell.modelData.label
                    }
                }
            }
        }
    }

    // Key figure: value (big, or subtitle size when small), suffix after it ("/24"), label under it
    component Figure: Column {
        id: figure
        property string value: ""
        property string suffix: ""
        property string label: ""
        property bool small: false
        spacing: 0
        Accessible.role: Accessible.StaticText
        Accessible.name: label + " " + value + suffix
        Row {
            spacing: theme.space1
            Text {
                id: figureValue
                text: figure.value
                textFormat: Text.PlainText
                color: theme.text
                font.pointSize: figure.small ? theme.fontSubtitle : theme.fontDisplay
                font.weight: Font.DemiBold
                font.features: { "tnum": 1 }
            }
            Text {
                visible: figure.suffix !== ""
                anchors.baseline: figureValue.baseline
                text: figure.suffix
                textFormat: Text.PlainText
                color: theme.dimText
                font.pointSize: theme.fontSubtitle
                font.features: { "tnum": 1 }
            }
        }
        Text {
            visible: figure.label !== ""
            text: figure.label
            textFormat: Text.PlainText
            color: theme.dimText
            font.pointSize: theme.fontSmall
        }
    }

    // Check of the banner below its verdict: level strip, icon, title & text, action
    component CheckRow: RowLayout {
        id: checkRow
        required property var modelData
        Layout.fillWidth: true
        spacing: theme.space3
        Rectangle {  // level strip: told by icon & text too, never by color alone
            Layout.fillHeight: true
            Layout.preferredWidth: Math.max(2, Math.round(theme.em * 0.2))
            radius: width / 2
            color: page.levelColor(checkRow.modelData.level)
        }
        Icon {
            glyph: page.levelGlyph(checkRow.modelData.level)
            fallback: page.levelFallback(checkRow.modelData.level)
            color: page.levelColor(checkRow.modelData.level)
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: theme.space1
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Text {
                Layout.fillWidth: true
                text: checkRow.modelData.title
                color: theme.text
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                visible: text !== ""
                text: checkRow.modelData.text
                color: theme.dimText
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
        }
        TpButton {
            visible: checkRow.modelData.actionText !== ""
            text: checkRow.modelData.actionText
            size: "sm"
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.runCheck(checkRow.modelData.action)
        }
    }

    // Corner to work on: label, time lost, likely cause; click or Enter opens the telemetry viewer on it
    component CornerTipRow: Rectangle {
        id: tipRow
        required property var modelData
        Layout.fillWidth: true
        implicitHeight: tipLine.implicitHeight + theme.space2 * 2
        radius: theme.radiusMd
        color: tipArea.containsMouse ? theme.hover : "transparent"
        activeFocusOnTab: true
        Keys.onReturnPressed: backend.openCorner(modelData.index)
        Keys.onEnterPressed: backend.openCorner(modelData.index)
        Keys.onSpacePressed: backend.openCorner(modelData.index)
        Accessible.role: Accessible.Button
        Accessible.name: modelData.label + " " + modelData.loss + " " + modelData.cause
        Accessible.onPressAction: backend.openCorner(modelData.index)
        RowLayout {
            id: tipLine
            anchors.fill: parent
            anchors.leftMargin: theme.space2
            anchors.rightMargin: theme.space2
            spacing: theme.space3
            Text {
                text: tipRow.modelData.label
                color: theme.text
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
            Text {
                text: tipRow.modelData.loss
                textFormat: Text.PlainText
                color: theme.tone("loss")
                font.features: { "tnum": 1 }
            }
            Text {
                Layout.fillWidth: true
                text: tipRow.modelData.cause
                color: theme.dimText
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
            Icon {
                glyph: ""  // chevron right
                fallback: "›"
                color: theme.dimText
                size: theme.iconSm
            }
        }
        MouseArea {
            id: tipArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: backend.openCorner(tipRow.modelData.index)
            ToolTip.visible: containsMouse
            ToolTip.text: i18n.tr("Open this corner in telemetry")
            ToolTip.delay: theme.tipDelay
        }
        FocusRing { visible: tipRow.activeFocus }
    }

    // Presets of the preset card, newest first: click loads one
    TpMenu {
        id: presetMenu
        property var rows: []
        Instantiator {
            model: presetMenu.rows
            delegate: TpMenuItem {
                required property var modelData
                text: modelData.name
                checkable: true
                checked: modelData.loaded
                enabled: !modelData.loaded
                onTriggered: backend.loadPreset(modelData.file)
            }
            onObjectAdded: function(index, object) { presetMenu.insertItem(index, object) }
            onObjectRemoved: function(index, object) { presetMenu.removeItem(object) }
        }
        MenuSeparator {}
        TpMenuItem {
            text: i18n.tr("All Presets…")
            onTriggered: backend.openPage("preset")
        }
    }

    TpMenu {
        id: quickMenu
        TpMenuItem {
            text: i18n.tr("Customize Quick Access…")
            onTriggered: backend.customizeQuick()
        }
    }

    // Dialogs & toasts asked by the backend (quick/dialogs.py): over the page, last child
    TpDialogHost {}
}
