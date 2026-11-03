import QtQuick

// Entry of a popup window's content (command palette, shortcuts sheet, notification center): fades & scales in as
// TpPopup does (from 0.96, motionBase), at once when Windows animations are off (motion tokens 0). Starts when made.
//   ColumnLayout { id: content; ... }  TpEnter { target: content }
ParallelAnimation {
    id: enter
    property Item target: null
    running: target !== null
    NumberAnimation { target: enter.target; property: "opacity"; from: 0; to: 1; duration: theme.motionBase }
    NumberAnimation {
        target: enter.target; property: "scale"; from: 0.96; to: 1; duration: theme.motionBase
        easing.type: Easing.OutCubic
    }
}
