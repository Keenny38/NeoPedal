import QtQuick
import QtQuick.Controls.Basic

// Popup menu: flyout surface with a soft shadow, fades in, items highlighted on hover, check marks, separators
// (MenuSeparator {}). Menu of a button: toggleBelow(button) opens it below the button (theme gap), a second click
// on the same button closes it (instead of closing & opening again), keyboard focus back on the button after Esc.
//   TpButton { id: more; onClicked: moreMenu.toggleBelow(more); TpMenu { id: moreMenu; ... } }
//   moreMenu.toggleBelow(hudButton, true)  // right edges aligned (button at the page's right edge)
Menu {
    id: menu
    padding: theme.space2  // same inset as TpCombo's list
    // As wide as its widest item (long French labels), 13 em at least, never wider than the window. Measured
    // again when an item changes width, once after items are added or removed (Instantiator models insert them
    // one by one: measured at each insert, the cost grew with the square of the count) and when it opens
    property int measureSerial: 0
    readonly property real widestItem: {
        var widest = 0
        measureSerial  // items added or removed (not count: changes at each insert)
        for (var i = 0; ; ++i) {
            var entry = itemAt(i)
            if (!entry)
                break
            widest = Math.max(widest, entry.implicitWidth)
        }
        return widest
    }
    function measureItems() { measureSerial += 1 }
    onCountChanged: Qt.callLater(menu.measureItems)  // once per batch of inserts
    onAboutToShow: {
        closing = false
        measureItems()  // items added just before opening: width right where it opens
    }
    implicitWidth: Math.min(Math.max(theme.em * 13, widestItem + leftPadding + rightPadding),
                            parent && parent.Window.window ? parent.Window.width - theme.em : theme.em * 40)

    // Button the menu was opened from by toggleBelow (null: opened otherwise). A press on it does not close the
    // menu (close policy: outside of its parent, the button or the area of toggleAt), its click then closes it: one
    // click, one toggle.
    property Item toggleSource: null
    property bool refocusSource: false  // button had keyboard focus: given back when the menu closes
    // Fading out (exit transition): still visible, but a click meant to open it again (press on another button
    // closed it, action just picked, Esc) opens it once closed (popup() while fading out was undone by the fade)
    property bool closing: false
    property var pendingOpen: null  // {source, x, y} opened at closed
    // Toggled open, just before it shows: entries made here are measured before it shows (made at aboutToShow, the
    // menu showed empty, then grew & widened: it blinked)
    signal opening()
    onAboutToHide: closing = true
    function toggleBelow(source, alignRight) {
        if (alignRight === true)
            measureItems()  // width of the items just set
        toggleAt(source, alignRight === true ? source.width - Math.max(width, implicitWidth) : 0,
                 source.height + theme.space1)
    }
    // Same toggle at a point of the source (clickable card or row: below its title line, not below all of it).
    // area: item holding the source & its siblings (cards of a list): the menu is placed in it, so a press on
    // another card does not close it, and a click there moves it to that card at once, filled again (closed then
    // opened, it faded out & in: it blinked). Presses elsewhere in the area are the page's to close it.
    function toggleAt(source, x, y, area) {
        var within = area || null
        if (visible && closing) {
            pendingOpen = { source: source, x: x, y: y, area: within }
            return
        }
        if (visible) {
            // Read before close(): without an exit transition (Windows animation effects off), closed (onClosed:
            // toggleSource reset) runs inside close() and the second click opened the menu again
            var openedFrom = toggleSource
            if (openedFrom !== source && within !== null && parent === within) {
                showAt(source, x, y, within)  // moved, never closed
                return
            }
            close()
            if (openedFrom === source)
                return
            if (visible) {  // fading out: opened from the new source once closed
                pendingOpen = { source: source, x: x, y: y, area: within }
                return
            }
        }
        showAt(source, x, y, within)
    }
    function showAt(source, x, y, within) {
        toggleSource = source
        refocusSource = source.activeFocus === true
        opening()
        measureItems()
        if (within === null) {
            popup(source, x, y)
            return
        }
        var at = source.mapToItem(within, x, y)
        if (visible) {
            menu.x = at.x
            menu.y = at.y
        } else {
            popup(within, at.x, at.y)
        }
    }
    closePolicy: toggleSource !== null ? Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
                                       : Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onClosed: {
        closing = false
        var source = toggleSource
        toggleSource = null
        var pending = pendingOpen
        pendingOpen = null
        if (pending !== null && pending.source) {
            toggleAt(pending.source, pending.x, pending.y, pending.area)
            return
        }
        if (source !== null && refocusSource)
            source.forceActiveFocus()
    }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionFast }
        NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: theme.motionFast; easing.type: Easing.OutCubic }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: theme.motionFast } }

    background: Rectangle {
        implicitWidth: theme.em * 13
        radius: theme.radiusLg
        color: theme.surfaceFlyout
        border.width: 1
        border.color: theme.strokeSubtle
        TpShadow {}
    }

    delegate: TpMenuItem {}
}
