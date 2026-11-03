import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Lap time goal of selected vehicle: set by the driver, else automatic (limit of next level of community lap
// times); progress since first lap time, told once beaten (automatic: once the level is reached)
TpSectionCard {
    id: card
    readonly property var goal: backend.goal
    // Backend tone name in its status color (gain, loss), else fallback
    function tone(name, fallback) { return name === "loss" || name === "gain" ? theme.tone(name) : fallback }
    objectName: "goalCard"
    visible: card.goal.visible === true
    title: i18n.tr("Lap Time Goal")
    glyph: ""  // target
    tip: i18n.tr("Lap time to beat with this car: automatic (next level of community lap times) unless you set one. A message tells you once it is beaten.")
    actions: [
        TpButton {  // goal set by the driver: back to the automatic one
            visible: card.goal.set === true && card.goal.auto !== true
            flat: true
            size: "sm"
            text: i18n.tr("Automatic")
            tip: i18n.tr("Remove your goal: automatic goal again (next level of community lap times)")
            onClicked: backend.clearGoal()
        },
        TpButton {
            size: "sm"
            text: card.goal.set === true && card.goal.auto !== true ? i18n.tr("Change…") : i18n.tr("Set…")
            tip: i18n.tr("Your own lap time to beat, instead of the automatic goal")
            onClicked: backend.editGoal()
        }
    ]
    RowLayout {
        visible: card.goal.set === true
        Layout.fillWidth: true
        spacing: theme.space4
        Text {
            text: card.goal.time || ""
            textFormat: Text.PlainText
            color: card.goal.reached ? theme.gain : theme.accent
            font.pointSize: theme.fontLarge
            font.weight: Font.DemiBold
            font.features: { "tnum": 1 }
        }
        Text {
            text: card.goal.gap || ""
            textFormat: Text.PlainText
            color: card.tone(card.goal.gapColor, theme.dimText)
            font.weight: Font.DemiBold
            font.features: { "tnum": 1 }
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
    }
    TpMeter {  // progress from the first lap time of the history to the goal
        visible: card.goal.set === true && (card.goal.ratio || -1) >= 0
        Layout.fillWidth: true
        value: Math.max(card.goal.ratio || 0, 0)
        tint: card.goal.reached ? theme.gain : theme.accent
        name: i18n.tr("Lap Time Goal")
    }
    Text {
        Layout.fillWidth: true
        // Personal best, what an automatic goal is (next level...)
        text: card.goal.set === true
              ? i18n.tr("Personal best") + " " + (card.goal.best || "—") + (card.goal.auto === true ? " · " + card.goal.source : "")
              : i18n.tr("No goal yet: set a lap time to beat.")
        textFormat: Text.PlainText
        color: theme.dimText
        font.pointSize: theme.fontLabel
        wrapMode: Text.WordWrap
    }
}
