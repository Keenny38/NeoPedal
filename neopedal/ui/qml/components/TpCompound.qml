import QtQuick

// Tyre compound badge, as in overlays (Standings): compound letter on a rounded square of compound color
TpLetterBadge {
    property string name: ""  // compound name or letter ("Soft", "Medium #2", "Hyper - Soft", "S")

    visible: name !== ""
    shape: "square"
    size: theme.em * 1.1
    letter: theme.compoundLetter(name)
    fill: theme.compound(name)
}
