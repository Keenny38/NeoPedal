import QtQuick
import QtQuick.Controls.Basic

// Popup surface in app look: flyout surface with a soft shadow (TpShadow), fades & scales in, page dimmed (scrim)
// when modal.
// Base of TpDialog and of the pages' own popups (settings, pickers, help). dismissOnOutside false: only Esc
// (or the popup's own buttons) closes it, for popups holding typed input.
//   TpPopup { anchors.centerIn: overlayItem; modal: true; width: ...; Column { ... } }
// Never parent: Overlay.overlay (the popup's own): a page made before the app shows it moves to the app window
// (QQuickWidget), the item a popup is declared in follows it, the popup's own Overlay.overlay stays on the
// former window: no parent once that window is gone, the popup never opens. Popups keep the item they are
// declared in as parent and center & size on overlayItem, the overlay of that item's window now.
Popup {
    id: popup
    property bool dismissOnOutside: true
    readonly property Item overlayItem: parent ? parent.Overlay.overlay : null  // window overlay, see above

    padding: theme.padPopup
    closePolicy: dismissOnOutside ? Popup.CloseOnEscape | Popup.CloseOnPressOutside : Popup.CloseOnEscape

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionFast }
        NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: theme.motionBase; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: theme.motionFast }
    }
    Overlay.modal: Rectangle {
        color: theme.scrim
        Behavior on opacity { NumberAnimation { duration: theme.motionFast } }
    }
    background: Rectangle {
        radius: theme.radiusLg
        color: theme.surfaceFlyout
        border.width: 1
        border.color: theme.strokeSubtle
        TpShadow {}
    }
}
