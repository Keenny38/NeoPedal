import QtQuick

// Message at bottom of page for a few seconds (click: hidden), slides in. show() after each new message.
// Shown long enough to read it (longer for errors), kept while the mouse is over it or its button has keyboard
// focus (Undo reached with Tab never vanishes under the key); optional action
// button (actionText, action signal): "Undo" after an action done without confirmation.
// level: "success" (check, default), "info", "warning", "error" (error: true is the same as level "error"),
// told by icon & border color. Screen readers announce it (alert). Same durations as the widget toasts
// (ui/toast.py toast_duration, theme.toast* tokens), counted on the text without markup. textFormat: Text.StyledText
// only for escaped text (Python safe_markup).
Rectangle {
    id: toast
    property string text: ""
    property bool error: false  // warning icon & red border, else check
    property string level: error ? "error" : "success"
    property int textFormat: Text.PlainText
    property int duration: 0  // ms shown, 0: from text length
    property string actionText: ""
    property bool shown: false
    readonly property bool failed: level === "error"
    readonly property color tone: level === "error" ? theme.loss : level === "warning" ? theme.warning
                                : level === "info" ? theme.info : theme.gain
    // Characters read: markup tags left out, an entity (&lt;) one character
    readonly property int readLength: textFormat === Text.StyledText
        ? text.replace(/<[^>]*>/g, "").replace(/&(#?[A-Za-z0-9]+);/g, "x").length : text.length
    readonly property int shownTime: duration > 0 ? duration
        : Math.round(Math.max(theme.toastMinimumTime, readLength * theme.toastTimePerCharacter + theme.toastReadStartTime)
                     * (failed ? theme.toastErrorFactor : 1) + (actionText !== "" ? theme.toastActionExtraTime : 0))
    // Mouse over the toast, or its action button focused: kept shown
    readonly property bool held: hover.hovered || actionButton.activeFocus
    signal action()

    function show() {
        shown = true
        if (held)
            hideTimer.stop()
        else
            hideTimer.restart()
    }
    onHeldChanged: {
        if (held)
            hideTimer.stop()
        else if (shown)
            hideTimer.restart()
    }

    Accessible.role: Accessible.AlertMessage
    Accessible.name: text

    anchors.horizontalCenter: parent.horizontalCenter
    y: shown ? parent.height - height - theme.space6 : parent.height + theme.em
    width: Math.min(toastRow.implicitWidth + theme.space6 * 2, parent.width - theme.em * 4)
    height: toastRow.implicitHeight + theme.em * 1.1
    radius: theme.radiusLg
    color: theme.surfaceFlyout
    border.width: 1
    border.color: level === "success" ? theme.strokeSubtle : tone
    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on y { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
    Behavior on opacity { NumberAnimation { duration: theme.motionSlow } }
    Timer { id: hideTimer; interval: toast.shownTime; onTriggered: toast.shown = false }
    TpShadow {}
    HoverHandler { id: hover }
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: toast.shown = false }
    Row {
        id: toastRow
        anchors.centerIn: parent
        spacing: theme.space4
        Icon {
            anchors.verticalCenter: parent.verticalCenter
            // warning (errors too), info, check
            glyph: toast.level === "warning" || toast.level === "error" ? ""
                 : toast.level === "info" ? "" : ""
            fallback: toast.level === "warning" || toast.level === "error" ? "!" : toast.level === "info" ? "i" : "✓"
            color: toast.tone
        }
        TpText {
            elide: Text.ElideNone
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, (toast.parent ? toast.parent.width : 0) - theme.em * 7
                            - (toast.actionText !== "" ? actionButton.implicitWidth + toastRow.spacing : 0))
            text: toast.text
            textFormat: toast.textFormat === Text.StyledText ? Text.StyledText : Text.PlainText
            color: theme.text
            wrapMode: Text.WordWrap
        }
        TpButton {
            id: actionButton
            anchors.verticalCenter: parent.verticalCenter
            visible: toast.actionText !== ""
            size: "sm"
            text: toast.actionText
            onClicked: { toast.shown = false; toast.action() }
        }
    }
}
