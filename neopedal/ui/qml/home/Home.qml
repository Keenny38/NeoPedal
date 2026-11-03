import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Home page: status banner on top (verdict of game & checks as title, its action, the other checks, version,
// release notes & update told once), then cards: game (in a session only, whole row: place, lap & time left in
// big type, live calculator, director & overlay lock at hand; off track the banner tells the game), overlays (lock,
// overlays & modules on), preset, this week, driver (ranks over time), last session with its debrief (each corner
// opens the telemetry viewer on it), next online races your Safety Rank opens (whole row), quick access. Cards
// open their page: click, or Tab then Enter / Space. Cards read in background keep their place (loading) until
// read: the grid never jumps. Cards follow page width in 1 to 3 columns, spans fill each row whichever cards are
// shown (no hole), the page scrolls when taller than the window.
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
    property bool debriefOpen: false  // corners to work on & goal shown
    // Cards shown (from data, never from .visible): spans fill each row of the grid
    readonly property bool weekShown: (loading.week === true && week.summary === undefined) || week.summary !== undefined
    readonly property bool driverShown: driver.name !== undefined || loading.driver === true
    readonly property bool lastShown: (last.track || "") !== ""

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

            // Status banner: verdict (session on track, ready, or the most important check) & its action, the
            // other checks, then app version, release notes & update (told once, here)
            Card {
                id: banner
                objectName: "statusBanner"
                readonly property string level: page.status.level || "info"
                readonly property color tone: page.levelColor(level)
                Layout.fillWidth: true
                implicitHeight: bannerColumn.implicitHeight + theme.padCard * 2
                color: Qt.tint(theme.surfaceCard, theme.tint(tone, "subtle"))
                border.color: theme.tint(tone, "strong")
                Accessible.role: Accessible.Grouping
                Accessible.name: page.status.title || ""

                ColumnLayout {
                    id: bannerColumn
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: theme.padCard }
                    spacing: theme.space3

                    GridLayout {  // verdict & its action (under it on a narrow page)
                        Layout.fillWidth: true
                        columns: page.compact ? 1 : 2
                        columnSpacing: theme.space5
                        rowSpacing: theme.space3
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: theme.space4
                            Item {  // level: live dot, else icon (with the title: never color alone)
                                Layout.preferredWidth: Math.round(theme.em * 1.6)
                                Layout.preferredHeight: Layout.preferredWidth
                                Layout.alignment: Qt.AlignTop
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
                                    size: theme.iconLg
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: theme.space1
                                Text {
                                    objectName: "statusTitle"
                                    Layout.fillWidth: true
                                    text: page.status.title || ""
                                    textFormat: Text.PlainText
                                    color: theme.text
                                    font.pointSize: theme.fontTitle
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                    Accessible.role: Accessible.Heading
                                    Accessible.name: text
                                }
                                Text {
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: page.status.text || ""
                                    textFormat: Text.PlainText
                                    color: theme.dimText
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                        TpButton {  // action following the verdict
                            objectName: "statusAction"
                            visible: (page.status.actionText || "") !== ""
                            Layout.alignment: page.compact ? Qt.AlignLeft : Qt.AlignRight | Qt.AlignVCenter
                            text: page.status.actionText || ""
                            accent: true
                            onClicked: backend.runCheck(page.status.action)
                        }
                    }

                    Repeater {  // other checks, most important first
                        model: page.status.rows || []
                        CheckRow {}
                    }

                    Rectangle {  // divider
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: theme.tint(banner.tone, "selected")
                    }
                    Flow {  // app & version (small), release notes, update
                        Layout.fillWidth: true
                        spacing: theme.space3
                        Image {
                            source: page.themed(page.header.icon, page.header.iconLight) || ""
                            visible: status === Image.Ready
                            width: Math.round(theme.em * 1.3)
                            height: width
                            sourceSize.height: Math.ceil(theme.em * 1.3 * Screen.devicePixelRatio)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            smooth: true
                        }
                        Text {
                            objectName: "versionText"
                            height: theme.controlHeightSm
                            verticalAlignment: Text.AlignVCenter
                            text: page.joined([(page.header.app || "") + " " + i18n.tr("Version") + " " + (page.header.version || ""),
                                               page.header.game || ""])
                            color: theme.dimText
                            font.pointSize: theme.fontSmall
                            textFormat: Text.PlainText
                        }
                        TpButton {
                            size: "sm"
                            flat: true
                            text: i18n.tr("What's New")
                            tip: i18n.tr("What's new in this version")
                            onClicked: backend.showReleaseNotes()
                        }
                        TpButton {  // update: told here only (no check row, no second pill)
                            objectName: "updateButton"
                            readonly property string updateState: page.header.update || ""
                            size: "sm"
                            flat: updateState !== "available"
                            accent: updateState === "available"
                            glyph: ""  // sync
                            text: updateState === "checking" ? i18n.tr("Checking…")
                                : updateState === "available" ? i18n.tr("Update Available") + " · v" + (page.header.latest || "")
                                : i18n.tr("Check for Updates")
                            tip: updateState === "available" ? i18n.tr("See Update") : page.header.tip || ""
                            enabled: updateState !== "checking"
                            onClicked: backend.updateAction()
                        }
                    }
                }
            }

            // Cards
            GridLayout {
                Layout.fillWidth: true
                columns: page.columns
                columnSpacing: theme.space4
                rowSpacing: theme.space4
                uniformCellWidths: true

                TpSectionCard {  // game & session, on track only: whole row (place, lap, time left, actions at hand)
                    fillContent: false  // content under the header, footer buttons at the bottom
                    objectName: "gameCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.columnSpan: page.columns
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
                        Text {
                            Layout.fillWidth: true
                            text: page.joined([page.game.track, page.game.session])
                            color: theme.text
                            font.pointSize: theme.fontSubtitle
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
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
                        TpButton {
                            size: "sm"
                            accent: true
                            glyph: page.overlay.locked ? theme.glyphs.lock : theme.glyphs.unlock  // state shown (as the Overlays card)
                            fallback: page.overlay.locked ? "L" : "U"
                            text: page.overlay.locked ? i18n.tr("Unlock Overlay") : i18n.tr("Lock Overlay")
                            onClicked: backend.toggleLock()
                        }
                    }
                }

                TpSectionCard {  // overlays: lock & display options, overlays & modules on
                    fillContent: false  // content under the header, footer buttons at the bottom
                    objectName: "overlaysCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    glyph: page.overlay.locked ? theme.glyphs.lock : theme.glyphs.unlock
                    fallback: page.overlay.locked ? "L" : "U"
                    title: i18n.tr("Overlays")
                    clickable: true
                    tip: i18n.tr("Open overlays")
                    onOpened: backend.openPage("widget")
                    Text {
                        Layout.fillWidth: true
                        text: page.overlay.locked ? i18n.tr("Locked") : i18n.tr("Unlocked")
                        textFormat: Text.PlainText
                        color: theme.text
                        font.pointSize: theme.fontSubtitle
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: page.overlay.locked === false
                        text: i18n.tr("Drag overlays to move them")
                        color: theme.dimText
                        wrapMode: Text.WordWrap
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
                    footer: [
                        TpButton {  // Module page (not in the navigation bar by default)
                            objectName: "openModules"
                            flat: true
                            size: "sm"
                            text: i18n.tr("Open modules")
                            onClicked: backend.openPage("module")
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

                TpSectionCard {  // preset loaded, switch to another one
                    fillContent: false  // content under the header, footer buttons at the bottom
                    objectName: "presetCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.columnSpan: page.columns === 3 && !page.weekShown ? 2 : 1
                    glyph: ""  // library
                    fallback: "P"
                    title: i18n.tr("Preset")
                    clickable: true
                    tip: i18n.tr("Open presets")
                    onOpened: backend.openPage("preset")
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: theme.space3
                        Text {
                            Layout.fillWidth: true
                            text: page.preset.name || ""
                            color: theme.text
                            font.pointSize: theme.fontSubtitle
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                        Pill {
                            visible: page.preset.locked === true
                            text: i18n.tr("Locked")
                            glyph: theme.glyphs.lock
                            tint: theme.dimText
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: page.preset.autoLoad ? i18n.tr("Primary preset loads automatically")
                                                   : i18n.tr("Primary preset auto load off")
                        textFormat: Text.PlainText
                        color: theme.dimText
                        wrapMode: Text.WordWrap
                    }
                    footer: TpButton {
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
                    }
                }

                TpSectionCard {  // last 7 days (as on Driver Stats): place kept while read, none when nothing driven
                    id: weekCard
                    objectName: "weekCard"
                    fillContent: false  // content under the header, footer buttons at the bottom
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    readonly property bool waiting: page.loading.week === true && page.week.summary === undefined
                    visible: page.weekShown
                    Layout.columnSpan: page.columns === 2 && !page.driverShown ? 2 : 1
                    glyph: ""  // calendar
                    fallback: "W"
                    title: i18n.tr("This Week")
                    clickable: true
                    tip: i18n.tr("Open driver stats")
                    onOpened: backend.openDriverStats()
                    TpStateView {
                        objectName: "weekLoading"
                        Layout.alignment: Qt.AlignHCenter
                        loading: weekCard.waiting
                        compact: true
                    }
                    TpText {  // sessions, driving time, laps
                        Layout.fillWidth: true
                        visible: text !== ""
                        role: "numeric"
                        text: page.week.summary || ""
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
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

                TpSectionCard {  // driver: ranks, badge, race record (read in background: place kept meanwhile)
                    fillContent: false  // content under the header, footer buttons at the bottom
                    id: driverCard
                    objectName: "driverCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.columnSpan: page.columns === 3 && !page.lastShown ? 3
                                     : page.columns === 2 && !page.weekShown ? 2 : 1
                    readonly property bool waiting: page.loading.driver === true && page.driver.name === undefined
                    property int rankHovered: 0  // rank rows under the mouse: their tooltip, not the card one
                    visible: page.driverShown
                    glyph: ""  // contact
                    fallback: "D"
                    title: i18n.tr("Driver")
                    clickable: true
                    tip: rankHovered > 0 ? "" : i18n.tr("Open driver stats")
                    onOpened: backend.openDriverStats()
                    TpStateView {
                        objectName: "driverLoading"
                        Layout.alignment: Qt.AlignHCenter
                        loading: driverCard.waiting
                        compact: true
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: page.driver.name || ""
                        color: theme.text
                        font.pointSize: theme.fontSubtitle
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: page.driver.identity || ""
                        color: theme.dimText
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                    Repeater {
                        model: page.driver.ranks || []
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: theme.space1
                            RowLayout {
                                id: rankRow
                                Layout.fillWidth: true
                                spacing: theme.space3
                                HoverHandler {  // what the percents mean
                                    id: rankHover
                                    onHoveredChanged: driverCard.rankHovered += hovered ? 1 : -1
                                }
                                TpToolTip {
                                    visible: rankHover.hovered && (modelData.tip || "") !== ""
                                    text: modelData.tip || ""
                                    delay: theme.tipDelay
                                    // A popup (not an item of the layout): placed in rankRow, below it
                                    y: rankRow.height + theme.space1  // qmllint disable Quick.layout-positioning
                                }
                                Text {
                                    text: modelData.label
                                    textFormat: Text.PlainText
                                    color: theme.dimText
                                    font.pointSize: theme.fontLabel
                                    elide: Text.ElideRight
                                    Layout.preferredWidth: theme.em * 6.5
                                }
                                Text {
                                    text: modelData.value
                                    textFormat: Text.PlainText
                                    color: page.rankColor(modelData)
                                    font.weight: Font.DemiBold
                                }
                                TpMeter {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: theme.em * 2
                                    Layout.alignment: Qt.AlignVCenter
                                    value: modelData.progress
                                    tint: page.rankColor(modelData)
                                    name: modelData.label
                                }
                                Text {
                                    text: modelData.progressText
                                    textFormat: Text.PlainText
                                    color: theme.text
                                    font.pointSize: theme.fontSmall
                                    font.features: { "tnum": 1 }
                                }
                                Text {  // change since previous rank: arrow & sign, not color alone
                                    visible: modelData.change !== ""
                                    text: (modelData.changeTone > 0 ? "▲ " : "▼ ") + modelData.change
                                    textFormat: Text.PlainText
                                    color: modelData.changeTone > 0 ? theme.gain : theme.loss
                                    font.pointSize: theme.fontSmall
                                    font.features: { "tnum": 1 }
                                }
                            }
                            TpRankLine {
                                Layout.fillWidth: true
                                visible: (modelData.chart || []).length > 1
                                points: modelData.chart || []
                                tint: page.rankColor(modelData)
                                label: modelData.label
                            }
                        }
                    }
                    RowLayout {  // game badge in its color
                        readonly property var badge: page.driver.badge || {}
                        visible: (badge.name || "") !== ""
                        Layout.fillWidth: true
                        spacing: theme.space3
                        Image {
                            source: parent.badge.icon || ""
                            visible: status === Image.Ready
                            Layout.preferredWidth: Math.round(theme.em * 1.3)
                            Layout.preferredHeight: Layout.preferredWidth
                            sourceSize.height: Math.ceil(theme.em * 1.3 * Screen.devicePixelRatio)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }
                        Text {
                            Layout.fillWidth: true
                            text: parent.badge.name || ""
                            color: page.themed(parent.badge.color, parent.badge.lightColor) || theme.text
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
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
                    RowLayout {  // ranks remembered: clock & warning color once old (not current values)
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
                            Layout.alignment: Qt.AlignTop
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.driver.note || ""
                            color: parent.stale ? theme.warning : theme.dimText
                            font.pointSize: theme.fontSmall
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                        }
                    }
                    Repeater {  // other game accounts of this computer
                        model: page.driver.others || []
                        Text {
                            required property var modelData
                            Layout.fillWidth: true
                            text: modelData.name + i18n.colon() + page.joined(modelData.ranks.map(function(rank) {
                                return rank.label + " " + rank.value
                            }).concat([modelData.badge.name || ""])) + " (" + modelData.when + ")"
                            color: theme.dimText
                            font.pointSize: theme.fontSmall
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                TpSectionCard {  // last driven session & its debrief (read in background: place kept meanwhile)
                    fillContent: false  // content under the header, footer buttons at the bottom
                    objectName: "lastSessionCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.columnSpan: page.columns === 1 ? 1 : page.columns === 2 || page.driverShown ? 2 : 3
                    visible: page.lastShown
                    glyph: ""  // history
                    fallback: "H"
                    title: i18n.tr("Last Session")
                    clickable: true
                    tip: i18n.tr("Driver stats of this track & car")
                    onOpened: backend.openLastSession()
                    trailing: [
                        GameLogo { source: page.last.trackLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 1.8 },
                        GameLogo { source: page.last.brandLogo || ""; boxWidth: theme.em * 5; boxHeight: theme.em * 1.8 }
                    ]
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: theme.space3
                        Text {
                            Layout.fillWidth: true
                            text: page.last.track || ""
                            color: theme.text
                            font.pointSize: theme.fontSubtitle
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                        Pill {
                            visible: (page.last.result || "") !== ""
                            text: page.last.result || ""
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: page.joined([page.last.vehicle, page.last.session,
                                           page.last.best ? i18n.tr("Best") + " " + page.last.best : "", page.last.date])
                        color: theme.dimText
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                    }
                    TpStateView {  // debrief being read: its place kept
                        objectName: "debriefLoading"
                        Layout.alignment: Qt.AlignHCenter
                        loading: page.loading.debrief === true && page.debrief.figures === undefined
                        compact: true
                    }
                    ColumnLayout {  // debrief: best & personal best, figures; corners & goal when opened
                        objectName: "debriefBlock"
                        Layout.fillWidth: true
                        visible: page.debrief.figures !== undefined
                        spacing: theme.space2
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: theme.space2
                            spacing: theme.space3
                            Icon { glyph: ""; fallback: "R"; color: theme.accent }  // area chart
                            TpSectionLabel {
                                Layout.fillWidth: true
                                text: i18n.tr("Session Debrief")
                            }
                            TpButton {
                                objectName: "debriefToggle"
                                visible: (page.debrief.tips || []).length > 0 || (page.debrief.goal || {}).goal !== undefined
                                flat: true
                                size: "xs"
                                text: page.debriefOpen ? i18n.tr("Hide Details") : i18n.tr("Show Details")
                                onClicked: page.debriefOpen = !page.debriefOpen
                                Accessible.role: Accessible.Button
                                Accessible.description: page.debriefOpen ? i18n.tr("Expanded") : i18n.tr("Collapsed")
                            }
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: theme.space3
                            Text {
                                text: (page.debrief.best || "") !== "" ? i18n.tr("Best") + " " + page.debrief.best : (page.debrief.track || "")
                                color: theme.text
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                                font.features: { "tnum": 1 }
                                height: Math.round(theme.em * 1.45)
                                verticalAlignment: Text.AlignVCenter
                            }
                            Pill {
                                visible: page.debrief.personal === "new"
                                text: page.debrief.personalText || ""
                                glyph: ""  // star
                                tint: theme.gain
                            }
                            Text {
                                visible: page.debrief.personal === "slower"
                                text: page.debrief.personalText || ""
                                color: theme.dimText
                                textFormat: Text.PlainText
                                height: Math.round(theme.em * 1.45)
                                verticalAlignment: Text.AlignVCenter
                                font.features: { "tnum": 1 }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: (page.debrief.figures || []).join(" · ")
                            color: theme.dimText
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            font.features: { "tnum": 1 }
                        }
                        TpSectionLabel {
                            Layout.fillWidth: true
                            Layout.topMargin: theme.space2
                            visible: page.debriefOpen && (page.debrief.tips || []).length > 0
                            text: i18n.tr("Work on") + " · " + (page.debrief.against || "")
                        }
                        Repeater {
                            model: page.debriefOpen ? page.debrief.tips || [] : []
                            CornerTipRow {}
                        }
                        ColumnLayout {  // lap time goal of driver stats page
                            id: goalBlock
                            Layout.fillWidth: true
                            Layout.topMargin: theme.space2
                            visible: page.debriefOpen && (page.debrief.goal || {}).goal !== undefined
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
                                Text {
                                    text: i18n.tr("Goal") + " " + (goalBlock.goal.goal || "")
                                    textFormat: Text.PlainText
                                    color: theme.text
                                    font.weight: Font.DemiBold
                                    font.features: { "tnum": 1 }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: goalBlock.goal.state === "reached" ? "✓ " + i18n.tr("reached") : (goalBlock.goal.gap || "")
                                    textFormat: Text.PlainText
                                    color: goalBlock.goal.state === "reached" ? theme.gain : theme.dimText
                                    font.weight: goalBlock.goal.state === "reached" ? Font.DemiBold : Font.Normal
                                    font.features: { "tnum": 1 }
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: goalBlock.goal.percent || ""
                                    textFormat: Text.PlainText
                                    visible: text !== ""
                                    color: theme.dimText
                                    font.features: { "tnum": 1 }
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

                TpSectionCard {  // next online races your Safety Rank opens (RaceControl): whole row
                    objectName: "racesCard"
                    fillContent: false
                    Layout.fillWidth: true
                    Layout.columnSpan: page.columns
                    visible: (page.races.rows || []).length > 0
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
                            // One race: start & time to it, reminder; title; track logo & name; classes, tier &
                            // length; your place this week, registered
                            Rectangle {
                                id: raceItem
                                objectName: "nextRace"
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                implicitHeight: raceColumn.implicitHeight + theme.space3 * 2
                                radius: theme.radiusMd
                                color: theme.surfaceSunken
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
                                                    visible: raceItem.modelData.until !== ""
                                                    size: "sm"
                                                    text: raceItem.modelData.until
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
                                    Flow {  // your place in the weekly leaderboard, registered
                                        Layout.fillWidth: true
                                        Layout.topMargin: theme.space1
                                        visible: (raceItem.modelData.place || "") !== "" || raceItem.modelData.registeredMe === true
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
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Quick access: tools, pages & actions chosen by the user (Customize, or right-click)
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
                Layout.fillWidth: true
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
                        glyph: modelData.glyph
                        fallback: modelData.letter
                        text: modelData.label
                        tip: modelData.shortcut !== "" ? modelData.label + "  " + modelData.shortcut : ""
                        onClicked: backend.runQuick(modelData.key)
                    }
                }
                Text {
                    visible: backend.quick.length === 0
                    Layout.fillWidth: true
                    text: i18n.tr("No quick access button: use Customize… to add tools, pages or actions.")
                    color: theme.dimText
                    wrapMode: Text.WordWrap
                }
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: theme.space2
                text: i18n.tr("Tip: press Ctrl+K to find any overlay, option, tool or preset. Drop a preset or plugin file on this window to import it.")
                color: theme.dimText
                font.pointSize: theme.fontSmall
                wrapMode: Text.WordWrap
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
