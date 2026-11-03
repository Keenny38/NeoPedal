import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Modal box over the page: title, content, Cancel & accept buttons (always in that order). Fades & scales in.
// Esc cancels (cancelled signal), a click outside too unless dismissOnOutside is false (dialogs with fields:
// typed text is not lost by a click beside), Enter in a field of the content accepts (call accept()).
// Opened without a field taking focus, the accept button has it (Cancel for danger): Enter answers at once.
// showCancel false: one button (acceptText, "Close") for dialogs that only show something.
TpPopup {
    id: dialog
    property string title: ""
    property string acceptText: "OK"
    property string cancelText: i18n.tr("Cancel")
    property bool acceptEnabled: true
    property bool showCancel: true
    property bool danger: false  // accept button in red (action cannot be undone)
    property bool closeOnAccept: true  // false: page closes it with done() once the action succeeded
    default property alias content: body.data
    signal accepted()
    signal cancelled()

    function accept() {
        if (!acceptEnabled)
            return
        if (closeOnAccept)
            done()
        accepted()
    }
    function done() {
        acceptedNow = true
        close()
    }
    // Focus in the content (field focused by the page when opened), else on the default button
    function focusDefault() {
        if (!opened)
            return
        var item = contentItem.Window.activeFocusItem
        for (; item; item = item.parent) {
            if (item === body)
                return
        }
        var cancelFirst = showCancel && (danger || !acceptButton.enabled)
        if (cancelFirst || acceptButton.enabled)
            (cancelFirst ? cancelButton : acceptButton).forceActiveFocus(Qt.TabFocusReason)
    }

    anchors.centerIn: overlayItem  // in the middle of the window, parent: the item it is declared in (TpPopup)
    width: Math.min(overlayItem ? overlayItem.width - theme.em * 2 : theme.em * 28, theme.em * 28)
    modal: true
    focus: true
    property bool acceptedNow: false
    onAboutToShow: acceptedNow = false
    onOpened: Qt.callLater(focusDefault)  // after the page focused a field of the content
    onClosed: if (!acceptedNow) cancelled()

    contentItem: ColumnLayout {
        spacing: theme.space5
        TpText {  // title role: heading size & display face, told to screen readers as a heading
            role: "title"
            wrap: true
            Layout.fillWidth: true
            text: dialog.title
            visible: text !== ""
        }
        ColumnLayout {
            id: body
            Layout.fillWidth: true
            spacing: theme.space3
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: theme.space1
            spacing: theme.space3
            Item { Layout.fillWidth: true }
            TpButton {
                id: cancelButton
                visible: dialog.showCancel
                text: dialog.cancelText
                onClicked: dialog.close()
                Keys.onReturnPressed: click()
                Keys.onEnterPressed: click()
            }
            TpButton {
                id: acceptButton
                accent: true
                danger: dialog.danger
                text: dialog.acceptText
                enabled: dialog.acceptEnabled
                onClicked: dialog.accept()
                Keys.onReturnPressed: click()
                Keys.onEnterPressed: click()
            }
        }
    }
}
