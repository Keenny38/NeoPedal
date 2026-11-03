#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Colors of the four themes, in one place (data only, no Qt)

Window themes (QPalette rows, status colors) are read by ui/__init__.py, overlay themes (classic color -> theme color
tables) by widget/_style.py, web pages by widget/_style.themed_page. tests/test_theme_contrast.py checks the contrast
of the window themes, tools/theme_contrast.py prints it.
"""

from types import MappingProxyType

THEME_NAMES = ("Modern Dark", "Modern Grey", "Modern White", "Legacy Grey")

# Window palettes: QPalette role -> (active, inactive, disabled) color
WINDOW_PALETTES = {
    "Modern Dark": {  # slate dark: the default
        "Window": ("#111318", "#111318", "#0F1115"),
        "WindowText": ("#E9ECF2", "#E9ECF2", "#7C828D"),
        "Base": ("#181B21", "#181B21", "#15171C"),
        "AlternateBase": ("#1C1F26", "#1C1F26", "#1A1C22"),
        "ToolTipBase": ("#23262E", "#23262E", "#23262E"),
        "ToolTipText": ("#E8EAED", "#E8EAED", "#E8EAED"),
        "PlaceholderText": ("#9CA0A8", "#9CA0A8", "#9CA0A8"),  # 4.5:1 on hover & selected rows
        "Text": ("#E8EAED", "#E8EAED", "#7A7D83"),
        "Button": ("#20232B", "#20232B", "#1A1C22"),
        "ButtonText": ("#E8EAED", "#E8EAED", "#7A7D83"),
        "BrightText": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "Light": ("#5A5D63", "#5A5D63", "#3A3C40"),
        "Midlight": ("#30353F", "#30353F", "#20232A"),  # hover visible on Button
        "Dark": ("#121315", "#121315", "#101113"),
        "Mid": ("#2E323C", "#2E323C", "#262931"),
        "Shadow": ("#0B0B0C", "#0B0B0C", "#0B0B0C"),
        "Highlight": ("#4C8DFF", "#3B78E7", "#2E323C"),
        "HighlightedText": ("#FFFFFF", "#FFFFFF", "#9AA0A6"),
        "Link": ("#5AAEFF", "#5AAEFF", "#7A7D83"),
        "LinkVisited": ("#C58AF9", "#C58AF9", "#7A7D83"),
    },
    "Modern Grey": {  # neutral gray, no blue tint, blue accent
        "Window": ("#1E1E1E", "#1E1E1E", "#1B1B1B"),
        "WindowText": ("#ECECEC", "#ECECEC", "#858585"),
        "Base": ("#282828", "#282828", "#232323"),
        "AlternateBase": ("#2C2C2C", "#2C2C2C", "#262626"),
        "ToolTipBase": ("#303030", "#303030", "#303030"),
        "ToolTipText": ("#ECECEC", "#ECECEC", "#ECECEC"),
        "PlaceholderText": ("#C0C0C0", "#C0C0C0", "#C0C0C0"),  # 4.5:1 on hover & selected rows
        "Text": ("#ECECEC", "#ECECEC", "#858585"),
        "Button": ("#303030", "#303030", "#292929"),
        "ButtonText": ("#ECECEC", "#ECECEC", "#858585"),
        "BrightText": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "Light": ("#6A6A6A", "#6A6A6A", "#444444"),
        "Midlight": ("#3C3C3C", "#3C3C3C", "#303030"),  # hover visible on Button
        "Dark": ("#151515", "#151515", "#121212"),
        "Mid": ("#5C5C5C", "#5C5C5C", "#3A3A3A"),  # input & control outlines 3:1 on cards,
        "Shadow": ("#101010", "#101010", "#101010"),
        "Highlight": ("#5B9BFF", "#4C8DF0", "#484848"),  # blue accent: 4.5:1 as text on window, cards & rows
        "HighlightedText": ("#FFFFFF", "#FFFFFF", "#9AA0A6"),
        "Link": ("#79B4FF", "#79B4FF", "#858585"),
        "LinkVisited": ("#C58AF9", "#C58AF9", "#858585"),
    },
    "Modern White": {  # light
        "Window": ("#F4F5F8", "#F4F5F8", "#ECEDF1"),
        "WindowText": ("#1F2328", "#1F2328", "#8C9096"),
        "Base": ("#FFFFFF", "#FFFFFF", "#F3F4F6"),
        "AlternateBase": ("#F6F7F9", "#F6F7F9", "#EEEFF2"),
        "ToolTipBase": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "ToolTipText": ("#1F2328", "#1F2328", "#1F2328"),
        "PlaceholderText": ("#5B6068", "#5B6068", "#5B6068"),  # 4.5:1 on window, hover & selected rows
        "Text": ("#1F2328", "#1F2328", "#8C9096"),
        "Button": ("#FFFFFF", "#FFFFFF", "#F3F4F6"),
        "ButtonText": ("#1F2328", "#1F2328", "#8C9096"),
        "BrightText": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "Light": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "Midlight": ("#E9EAED", "#E9EAED", "#F3F4F6"),
        "Dark": ("#A3A7AD", "#A3A7AD", "#A3A7AD"),
        "Mid": ("#D0D3D8", "#D0D3D8", "#D0D3D8"),
        "Shadow": ("#1F2328", "#1F2328", "#1F2328"),
        "Highlight": ("#2A63D4", "#2559BE", "#DADDE2"),  # 4.5:1 as text on window
        "HighlightedText": ("#FFFFFF", "#FFFFFF", "#5F6368"),
        "Link": ("#1A7FE0", "#1A7FE0", "#8C9096"),
        "LinkVisited": ("#8E44AD", "#8E44AD", "#8C9096"),
    },
    "Legacy Grey": {  # classic colors of TinyPedal 2.50
        "Window": ("#202124", "#202124", "#1C1D20"),
        "WindowText": ("#E8EAED", "#E8EAED", "#7A7D83"),
        "Base": ("#17181B", "#17181B", "#1C1D20"),
        "AlternateBase": ("#1D1E22", "#1D1E22", "#222327"),
        "ToolTipBase": ("#2B2D31", "#2B2D31", "#2B2D31"),
        "ToolTipText": ("#E8EAED", "#E8EAED", "#E8EAED"),
        "PlaceholderText": ("#A8ABB1", "#A8ABB1", "#A8ABB1"),  # 4.5:1 on hover & selected rows
        "Text": ("#E8EAED", "#E8EAED", "#7A7D83"),
        "Button": ("#2B2D31", "#2B2D31", "#25262A"),
        "ButtonText": ("#E8EAED", "#E8EAED", "#7A7D83"),
        "BrightText": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "Light": ("#5A5D63", "#5A5D63", "#3A3C40"),
        "Midlight": ("#3C3F44", "#3C3F44", "#303236"),  # hover: dim text stays 4.5:1
        "Dark": ("#121315", "#121315", "#101113"),
        "Mid": ("#3A3C41", "#3A3C41", "#2A2B2F"),
        "Shadow": ("#0B0B0C", "#0B0B0C", "#0B0B0C"),
        "Highlight": ("#58A7F8", "#1F6FC5", "#3A3C41"),  # 4.5:1 as text on every surface (Legacy Grey)
        "HighlightedText": ("#FFFFFF", "#FFFFFF", "#9AA0A6"),
        "Link": ("#5AAEFF", "#5AAEFF", "#7A7D83"),
        "LinkVisited": ("#C58AF9", "#C58AF9", "#7A7D83"),
    },
}

# Status colors (no QPalette role for them), per window color theme.
# Text colors keep at least 4.5:1 contrast on window & base background of their theme,
# badge colors are backgrounds under badge_text.
STATUS_COLORS = {
    "Dark": {
        "success": "#3DDC84",
        "success_border": "#2E7D52",
        "inactive": "#808080",
        "danger": "#FF7B72",
        "warning": "#E3B341",
        "info": "#58A6FF",
        "badge_success": "#238636",
        "badge_danger": "#C93C37",
        "badge_warning": "#8A5D00",
        "badge_neutral": "#5E6670",
        "badge_text": "#FFFFFF",
    },
    "Light": {
        "success": "#16702F",
        "success_border": "#16702F",
        "inactive": "#6E7781",
        "danger": "#B42318",
        "warning": "#8A5A00",
        "info": "#0B5CBF",
        "badge_success": "#1A7F37",
        "badge_danger": "#CF222E",
        "badge_warning": "#8A5A00",
        "badge_neutral": "#5E6670",
        "badge_text": "#FFFFFF",
    },
}

# Overlay themes: 
# Classic default color (RGB) -> modern color (RGB), alpha channel is kept
MODERN_PALETTE = MappingProxyType({
    # Neutral (slate)
    "000000": "0E1116",
    "111111": "13161C",
    "222222": "1B1F27",
    "2A2A2A": "212631",
    "333333": "2A303C",
    "444444": "373E4C",
    "555555": "4A5262",
    "666666": "576071",
    "777777": "646D7E",
    "888888": "747D8E",
    "AAAAAA": "9AA3B2",
    "BBBBBB": "AEB4C0",
    "CCCCCC": "C3C8D1",
    "DDDDDD": "D6DAE1",
    "EEEEEE": "E9ECF1",
    "FFFFFF": "F4F6F9",
    # Red & orange
    "FF2200": "F87171",  # loss: status colors of app pages & stream graphics (setting_status_colors)
    "FF4400": "FF5A36",
    "DD5500": "F06A2B",
    "EE6600": "F2743A",
    "FF6600": "FB923C",  # warning (pit)
    # Yellow
    "FFAA00": "FFB020",
    "FFCC00": "FFD43B",
    "FFFF00": "FACC15",  # gold (yellow flag, slower sector)
    "CCCC22": "D4D44A",
    # Green
    "009900": "22A052",
    "22AA00": "2FB344",
    "22CC22": "4ADE80",  # gain
    "448800": "3A9D5D",
    "44FF00": "4ADE80",
    "66EE00": "52D273",
    "66FF00": "5BE37D",
    "88FF00": "8BE36B",
    # Blue & cyan
    "00CCEE": "22B8E0",
    "00CCFF": "38BDF8",
    "66CCFF": "5CC8FF",
    "66CCCC": "5EC4C4",
    # Purple & pink
    "AA00AA": "A63DC7",
    "CC22CC": "C026D3",
    "FF44FF": "E879F9",
    "FF66FF": "F472D0",
    # Other default colors
    "00AAFF": "38A9F5", "FF0000": "F23B3B", "999999": "8A93A3", "FF00FF": "E056E0",
    "FF4422": "FF5A40", "0088FF": "2F86F0", "FF44CC": "F062C8", "00FF00": "3EDC6B",
    "AA22AA": "A33FB0", "008800": "2A8F4F", "44CC00": "4CC45A", "00FFFF": "4FE3EE",
    "00CC00": "36B85A", "77FF00": "86E35C", "00C2F2": "2BB8E6", "EE00EE": "D94BD9",
    "2266CC": "3570C8", "CC7700": "D08526", "0000FF": "3B5BF0", "22FFFF": "5CE8F0",
    "FFFF22": "F8E45A", "22EE22": "45D86A", "EE7700": "F08A2E", "4444FF": "5B5BF5",
    "44AA00": "4FA84A", "FF8800": "FF9530", "22FF00": "4EE36B", "00BBDD": "22B0D6",
    "EE0000": "E53E3E", "9900FF": "C084FC", "0099FF": "2E98F2", "0055FF": "3565F2",
    "0066CC": "2A6EC2", "BBAA00": "C2B236", "887700": "8A7E2E", "880088": "8A3A8F",
    "008888": "2A8A8A", "DD2200": "E0452F", "CC00CC": "C23BC9", "FF2222": "F44848",
    "CC44CC": "C257C7", "44DDFF": "5AD2F7", "88FF88": "8FE8A0", "FFFF88": "F9EE95",
    "EE77FF": "E08AF2",
})

# Modern Grey: neutral gray scale (no blue tint) in place of the slate one of Modern Dark, panels a little lighter
MODERN_GREY_NEUTRALS = MappingProxyType({
    "000000": "161616",
    "111111": "1C1C1C",
    "222222": "252525",
    "2A2A2A": "2C2C2C",
    "333333": "343434",
    "444444": "414141",
    "555555": "515151",
    "666666": "5F5F5F",
    "777777": "6C6C6C",
    "888888": "7B7B7B",
    "999999": "8A8A8A",
    "AAAAAA": "A0A0A0",
    "BBBBBB": "B3B3B3",
    "CCCCCC": "C7C7C7",
    "DDDDDD": "D9D9D9",
    "EEEEEE": "EAEAEA",
    "FFFFFF": "F5F5F5",
})

# Modern White (light theme): classic grays (panels & text) inverted, colors on panels darkened to stay readable.
# Grays: slate scale of Modern Dark, reversed
MODERN_LIGHT_NEUTRALS = MappingProxyType({
    "000000": "FFFFFF",
    "111111": "FAFBFC",
    "222222": "F4F6F9",
    "2A2A2A": "EDF0F4",
    "333333": "E5E9EF",
    "444444": "D8DDE5",
    "555555": "C5CBD5",
    "666666": "98A1B0",
    "777777": "848D9C",
    "888888": "6B7383",
    "999999": "5E6676",
    "AAAAAA": "4E5666",
    "BBBBBB": "3F4655",
    "CCCCCC": "313845",
    "DDDDDD": "252B36",
    "EEEEEE": "171B22",
    "FFFFFF": "0E1116",
})
