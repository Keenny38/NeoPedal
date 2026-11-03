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
Page registry: every main window page & tool page declared once

Main window pages (navigation rail) and tool pages (Tools page cards, menu, command palette,
navigation rail, home quick access) are read from PAGES. Tables of ui.tools_view, ui.nav_rail,
ui.app & the default rail of setting_global are derived from it. Plain data only (no Qt import):
dialog classes are named by path, imported when first opened.
"""

from __future__ import annotations

from dataclasses import dataclass

PAGE_MAIN = "Pages"  # category of main window pages
# Tool categories: Tools page sections & menu, in order
TOOL_CATEGORIES = ("Utilities", "Editors", "Management", "Advanced")


@dataclass(frozen=True)
class PageSpec:
    """Main window page or tool page

    Args:
        name: Page key (rail & quick access setting), tool dialog module name for tool pages.
        label: Full name (English, translated by tr), rail tooltip.
        glyph: Icon glyph in Segoe Fluent Icons / MDL2 Assets.
        category: PAGE_MAIN, or tool section (see TOOL_CATEGORIES).
        dialog: Tool dialog "module.DialogClass" path relative to ui package ("" for main pages).
        short_label: Rail label (rail buttons are narrow), label if empty.
        letter: Icon drawn without icon font, first letter of short label if empty.
        rail: Position in default navigation rail, -1 if not in it.
        keywords: Extra words finding the tool in command palette (former names, what it covers), both languages.
        status: "module:function" giving status of tool page with an on / off switch ("on", "off", "" closed).
        description: What the page is for, one short sentence (Tools page, command palette).
        listed: Shown on Tools page & Tools menu (Settings: own menu, rail gear & Ctrl+, only).
        wiki: User guide page (and #anchor) explaining the page, opened by the help button.
    """

    name: str
    label: str
    glyph: str
    category: str
    dialog: str = ""
    short_label: str = ""
    letter: str = ""
    rail: int = -1
    keywords: str = ""
    status: str = ""
    description: str = ""
    listed: bool = True
    wiki: str = ""

    @property
    def rail_label(self) -> str:
        return self.short_label or self.label

    @property
    def rail_letter(self) -> str:
        return self.letter or self.rail_label[:1]


# Tabs of the Data Editors page, former editor pages: (key: former tool name, tab label, "module.DialogClass")
DATA_EDITOR_TABS = (
    ("vehicle_class_editor", "Classes", "vehicle_class_editor.VehicleClassEditor"),
    ("vehicle_brand_editor", "Brands", "vehicle_brand_editor.VehicleBrandEditor"),
    ("tyre_compound_editor", "Compounds", "tyre_compound_editor.TyreCompoundEditor"),
    ("brake_editor", "Brakes", "brake_editor.BrakeEditor"),
    ("heatmap_editor", "Heatmaps", "heatmap_editor.HeatmapEditor"),
    ("track_info_editor", "Tracks", "track_info_editor.TrackInfoEditor"),
    ("track_notes_editor", "Notes", "track_notes_editor.TrackNotesEditor"),
)
MAP_VIEWER_PATH = "track_map_viewer.TrackMapViewer"  # former tool page: map of the Tracks tab
PERFORMANCE_PATH = "perf_view.PerformanceView"  # Performance button of the Modules category of Settings


# Every page: main window pages first (in tab order), then tools by category (in card order)
PAGES: tuple[PageSpec, ...] = (
    PageSpec("home", "Home", "", PAGE_MAIN, letter="A", rail=0,
             description="Game, preset, overlays & last session at a glance", wiki="Getting-Started#home-page"),  # home
    PageSpec("widget", "Overlays", "", PAGE_MAIN, letter="W", rail=2,
             description="Turn overlays on or off and open their options", wiki="Overlays"),  # all apps grid
    PageSpec("preset", "Preset", "", PAGE_MAIN, short_label="Presets", letter="P", rail=6,
             description="Load, create, share and restore presets", wiki="Presets-and-Settings#presets"),  # library
    # Utilities
    PageSpec(
        "race_calculator", "Race Calculator", "", "Utilities",  # calculator
        "race_calculator.RaceCalculator", short_label="Calculator",
        keywords=(
            "fuel calculator tyre tire strategy planner energy pit stop stint "
            "carburant calculateur pneus strategie energie arret relais"
        ),
        status="neopedal.ui.quick.race_backend:race_status",
        description="Fuel, energy, tyres and pit stops of a race, live or planned",
        wiki="Race-Calculator",
    ),
    PageSpec(
        "driver_stats_viewer", "Driver Stats", "", "Utilities",  # contact
        "driver_stats_viewer.DriverStatsViewer", short_label="Stats", rail=3,
        description="Your laps, personal bests and progress on every track",
        wiki="Driver-Stats",
    ),
    PageSpec(
        "lap_viewer", "Lap Telemetry Viewer", "", "Utilities",  # area chart
        "lap_viewer.LapViewer", short_label="Telemetry", rail=5,
        description="Compare recorded laps on charts and on the track map",
        wiki="Telemetry-Viewer",
    ),
    PageSpec(
        "broadcast_director", "Broadcast Director", "", "Utilities",  # sliders (mixing desk)
        "broadcast_director.BroadcastDirector", short_label="Broadcast",
        keywords=(
            "lmu broadcast director cast casting camera cameras spectator stream commentator commentary battle "
            "auto director tv production regie realisateur spectateur commentateur commentaires bagarre diffusion "
            "spectate spectate mode follow driver suivre pilote mode spectateur"
        ),
        status="neopedal.ui.quick.director_backend:director_status",
        description="Cameras, live timing and graphics while spectating",
        wiki="Broadcast-Director",
    ),
    PageSpec(
        "race_results_viewer", "Results & Replays", "", "Utilities",  # flag
        "race_results_viewer.RaceResultsViewer", short_label="Results", rail=4,
        keywords=(
            "results classification standings finish position grid laps sectors incidents penalties session "
            "resultats classement arrivee grille tours secteurs incidents penalites "
            "game replays lmu replay incident contact crash watch rediffusion contacts accrochage revoir"
        ),
        description="Results of past sessions and game replays",
        wiki="Race-Results",
    ),
    PageSpec(
        "race_schedule_viewer", "Upcoming Races", "", "Utilities",  # calendar
        "race_schedule_viewer.RaceScheduleViewer", short_label="Races", rail=1,
        keywords=(
            "lmu racecontrol online daily race weekly special event championship coop co-op hosted server "
            "schedule calendar upcoming next safety rank sr "
            "course quotidienne hebdomadaire evenement special championnat serveur heberge planning calendrier "
            "prochaines courses a venir en ligne"
        ),
        description="Online races to come: daily, weekly, special, championships, co-op & hosted servers",
        wiki="Upcoming-Races",
    ),
    PageSpec(
        "stream_overlay_view", "Stream Overlays", "", "Utilities",  # streaming
        "stream_overlay_view.StreamOverlaysView", short_label="Stream",
        keywords=(
            "obs streamlabs xsplit vmix twitch youtube stream streaming browser source broadcast layout "
            "diffusion direct source navigateur streamer"
        ),
        description="Overlays as browser sources for OBS and other streaming apps",
        wiki="Connections#stream-overlays-obs-streamlabs-xsplit-vmix",
    ),
    # Editors
    PageSpec(
        "data_editors", "Data Editors", "\ue70f", "Editors",  # edit
        "data_editors.DataEditors", short_label="Editors",
        keywords=(
            "heatmap brake tyre tire compound vehicle car brand maker class track info pit lane speed trap "
            "track notes pace notes pacenotes playback sound editor editors "
            "carte thermique frein pneu gomme voiture marque constructeur classe circuit piste stand "
            "notes de piste notes de pilotage lecture son editeur editeurs"
        ),
        description="Classes, brands, compounds, brakes, heatmaps, tracks and track & pace notes",
        wiki="Presets-and-Settings#style-presets",
    ),
    # Management
    PageSpec(
        "app_settings", "Settings", "", "Management",  # settings
        "app_settings.AppSettings",
        keywords=(
            "settings configuration options preferences application config.json overlay style theme notification "
            "compatibility remote control web dashboard vr user path folder language startup update backup "
            "parametres reglages preferences style theme notifications compatibilite controle a distance "
            "tableau de bord dossiers langue demarrage mise a jour sauvegardes"
        ),
        description="Every application option",
        wiki="Presets-and-Settings#global-config",
        listed=False,
    ),
    PageSpec(
        "plugin_manager", "Plugin Manager", "", "Management",  # puzzle
        "plugin_manager.PluginManager", short_label="Plugins",
        description="Install, trust and enable overlay plugins",
        wiki="Overlays#widget-plugins",
        listed=False,  # Overlays page (Plugins button), command palette
    ),
    PageSpec(
        "perf_view", "Overlay Performance", "\uec4a", "Management",  # speed
        "perf_view.PerformanceView", short_label="Performance",
        description="CPU time of each overlay and module, game data state",
        wiki="Troubleshooting#performance",
        listed=False,  # Performance button of the Modules category of Settings, command palette
    ),
    # Advanced
    PageSpec(
        "replay_view", "Session Recorder", "", "Advanced",  # replay
        "replay_view.ReplayView", short_label="Recorder",
        keywords=(
            "telemetry replay tpreplay record playback without game overlay test "
            "rejeu telemetrie enregistrer lecture sans jeu"
        ),
        description="Record a session and play it back without the game",
        wiki="Connections#session-recorder",
    ),
)


# User guide page of dialog pages absent from PAGES (help button), by dialog class name
DIALOG_WIKI = {
    "OverlayOptions": "Getting-Started#the-overlay-options-page",
    "OptionFinder": "Getting-Started#find-any-option",
    "ReleaseNotesDialog": "Updates-and-Security#whats-new-page",
    "About": "Home#license-and-credits",
    "LogInfo": "Troubleshooting#logs",
    "BugReport": "Troubleshooting#report-a-bug",
    "QuickAccessEditor": "Getting-Started#home-page",
}


def check_pages(pages: tuple[PageSpec, ...]):
    """Raise if page names, dialogs or rail positions repeat, or a tool has no known category"""
    names = [page.name for page in pages]
    if len(set(names)) != len(names):
        raise RuntimeError(f"page declared twice: {sorted({name for name in names if names.count(name) > 1})}")
    for page in pages:
        if page.category == PAGE_MAIN:
            if page.dialog:
                raise RuntimeError(f"main page with a dialog: {page.name}")
        elif page.category not in TOOL_CATEGORIES or page.dialog.split(".", 1)[0] != page.name:
            raise RuntimeError(f"tool page without known category or dialog module: {page.name}")
    rails = [page.rail for page in pages if page.rail >= 0]
    if sorted(rails) != list(range(len(rails))):
        raise RuntimeError(f"default rail positions not 0 to {len(rails) - 1}: {sorted(rails)}")


def main_pages(pages: tuple[PageSpec, ...] = PAGES) -> tuple[PageSpec, ...]:
    """Main window pages in tab order"""
    return tuple(page for page in pages if page.category == PAGE_MAIN)


def tool_pages(pages: tuple[PageSpec, ...] = PAGES) -> tuple[PageSpec, ...]:
    """Tool pages in card order (category by category)"""
    return tuple(page for category in TOOL_CATEGORIES for page in pages if page.category == category)


def tool_sections(
    pages: tuple[PageSpec, ...] = PAGES, listed_only: bool = False,
) -> tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]:
    """Tool sections: (title, ((label, glyph, "module.DialogClass"), ...)), empty sections left out

    Args:
        listed_only: only tools of Tools page & Tools menu (see PageSpec.listed), else every tool page
            (navigation rail entries, pages reopened at startup).
    """
    sections = []
    for category in TOOL_CATEGORIES:
        tools = tuple((page.label, page.glyph, page.dialog) for page in pages
                      if page.category == category and (page.listed or not listed_only))
        if tools:
            sections.append((category, tools))
    return tuple(sections)


def page_spec(key: str, pages: tuple[PageSpec, ...] = PAGES) -> PageSpec | None:
    """Page by name (page key, tool module name) or by tool dialog path or class name, None if unknown"""
    for page in pages:
        if key in (page.name, page.dialog) or (page.dialog and page.dialog.rsplit(".", 1)[-1] == key):
            return page
    return None


def page_wiki(class_name: str) -> str:
    """User guide page (and #anchor) of a dialog page by class name: its PageSpec, else DIALOG_WIKI, "" if none"""
    spec = page_spec(class_name)
    return spec.wiki if spec is not None and spec.wiki else DIALOG_WIKI.get(class_name, "")


def default_rail(pages: tuple[PageSpec, ...] = PAGES) -> str:
    """Default navigation rail setting text: page keys in rail order"""
    return ",".join(page.name for page in sorted((page for page in pages if page.rail >= 0), key=lambda page: page.rail))


check_pages(PAGES)
