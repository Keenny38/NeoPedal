"""Window menus tidied (2026-11-02): Restart & Quit together (end of the title bar menu, else Window menu, tray keeps
Quit), Tools menu without the tools of the navigation bar, Settings sections in a submenu, clearer names, Command
Palette shortcut shown in Help"""

from PySide6.QtWidgets import QMainWindow, QMenu

from tests.test_ui_audit_2026_10_29_shell import flush, window  # noqa: F401


def texts(menu: QMenu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def visible_texts(menu: QMenu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator() and action.isVisible()]


def test_quit_in_window_menu_and_tray_only(window):  # noqa: F811
    from neopedal.ui.menu import OverlayMenu, WindowMenu

    overlay = window.findChild(OverlayMenu)
    assert "Quit" not in texts(overlay) and "Reload Overlays" in texts(overlay)
    assert texts(window.findChild(WindowMenu))[-2:] == ["Restart NeoPedal", "Quit"]  # Windows title bar (tests)
    tray = OverlayMenu("Overlay", window, True)
    assert texts(tray)[-1] == "Quit"
    tray.deleteLater()
    menu = WindowMenu("Window", window, app_actions=False)  # modern title bar: end of its menu instead
    assert "Quit" not in texts(menu) and "Restart NeoPedal" not in texts(menu)
    assert not menu.actions()[-1].isSeparator()
    menu.deleteLater()


def test_title_bar_menu_ends_with_restart_and_quit(ui_env):
    from PySide6.QtWidgets import QApplication

    from neopedal.ui.title_bar import TitleBar

    qapp = QApplication.instance()

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.calls = []

        def restart_app(self):
            self.calls.append("restart")
            return True

        def quit_app(self):
            self.calls.append("quit")
            return True

    main = Window()
    bar = TitleBar(main)
    main.setMenuWidget(bar)
    bar.menu_bar.addMenu("Help")
    bar.customize_rail = lambda: None
    main.show()
    try:
        bar.show_menu()
        qapp.processEvents()
        menu = next(widget for widget in qapp.topLevelWidgets() if isinstance(widget, QMenu) and widget.isVisible())
        actions = menu.actions()
        assert [action.text() for action in actions if not action.isSeparator()] == [
            "Help", "Customize Navigation Bar…", "Restart NeoPedal", "Quit"]
        assert actions[-3].isSeparator()  # own group, after the rail editor
        actions[-2].trigger()
        actions[-1].trigger()
        assert main.calls == ["restart", "quit"]
        menu.close()
    finally:
        main.close()
        main.deleteLater()
        qapp.processEvents()


def test_tools_menu_leaves_out_tools_of_navigation_bar(window, monkeypatch):  # noqa: F811
    from neopedal.ui import nav_rail
    from neopedal.ui.menu import ToolsMenu
    from neopedal.ui.tools_view import LISTED_TOOL_SECTIONS

    tools = window.findChild(ToolsMenu)
    rail = nav_rail.current_rail_items()
    assert "race_calculator" in rail and "lap_viewer" in rail  # default rail
    tools.aboutToShow.emit()
    shown = visible_texts(tools)
    assert "Race Calculator" not in shown and "Lap Telemetry Viewer" not in shown and "Results && Replays" not in shown
    assert "Track Map Viewer" in shown and "Brake Editor" in shown and "Session Recorder" in shown
    assert len(shown) < 15  # was 20
    # Removed from the navigation bar: listed again
    monkeypatch.setattr(nav_rail, "current_rail_items", lambda: [key for key in rail if key != "race_calculator"])
    tools.aboutToShow.emit()
    assert "Race Calculator" in visible_texts(tools)
    # Every tool in the navigation bar: separators of empty sections hidden too (no stacked separators)
    names = [path.split(".", 1)[0] for _, entries in LISTED_TOOL_SECTIONS for _, _, path in entries]
    monkeypatch.setattr(nav_rail, "current_rail_items", lambda: names)
    tools.aboutToShow.emit()
    assert visible_texts(tools) == ["Pages"]
    assert not [action for action in tools.actions() if action.isSeparator() and action.isVisible()]


def test_settings_sections_in_submenu(window):  # noqa: F811
    from neopedal.ui.menu import ConfigMenu

    menu = window.findChild(ConfigMenu)
    assert texts(menu) == ["Open Settings", "Find Option…", "Sections", "Web Dashboard Address…", "Open Folder",
                           "Import Settings…"]
    assert texts(menu.menu_sections) == [
        "Application", "Compatibility", "Notification", "Units", "Global Font Override", "Overlay Style",
        "Remote Control", "Web Dashboard", "VR Overlay (Experimental)", "User Path"]
    opened = []
    import neopedal.ui.app_settings as app_settings

    original = app_settings.open_app_settings
    app_settings.open_app_settings = lambda parent, section: opened.append(section)
    try:
        for action in menu.menu_sections.actions():
            if not action.isSeparator():
                action.trigger()
    finally:
        app_settings.open_app_settings = original
    assert opened == ["application", "compatibility", "notification", "units", "font", "overlay_style",
                      "remote_control", "web_dashboard", "vr_overlay", "user_path"]


def test_help_and_api_names(window, monkeypatch):  # noqa: F811
    from neopedal.ui import command_palette
    from neopedal.ui.menu import APIMenu, HelpMenu

    assert "API Options" in texts(window.findChild(APIMenu))
    help_menu = window.findChild(HelpMenu)
    titles = texts(help_menu)
    assert "About NeoPedal" in titles and "Setup Wizard…" in titles and "Command Palette\tCtrl+K" in titles
    assert "Support NeoPedal" not in titles  # own menu, right after Help
    menus = [action.text() for action in window.menuBar().actions()]
    assert menus[-2:] == ["Help", "Support NeoPedal"]
    support = window.menuBar().actions()[-1].menu()
    assert type(support).__name__ == "SupportMenu" and texts(support) == ["Patreon", "Ko-fi"]
    opened = []
    monkeypatch.setattr(window, "open_command_palette", lambda: opened.append(True))
    menu = HelpMenu("Help", window)
    next(action for action in menu.actions() if action.text().startswith("Command Palette")).trigger()
    assert opened == [True]
    menu.deleteLater()
    # Palette: no entry opening the palette, support links found by their menu path
    commands = command_palette.build_commands(window)
    assert not [command for command in commands if command.title.startswith("Command Palette")]
    patreon = next(command for command in commands if command.title == "Patreon")
    assert "support neopedal" in patreon.text


def test_palette_keeps_restart_and_quit_under_title_bar(window, monkeypatch):  # noqa: F811
    from neopedal.ui import command_palette
    from neopedal.ui.menu import WindowMenu

    window_menu = window.findChild(WindowMenu)
    for action in window_menu.actions()[-3:]:  # as under the title bar drawn by the app (not in the menu)
        action.setVisible(False)
    quits = []
    monkeypatch.setattr(window, "quit_app", lambda: quits.append(True) or True)
    commands = command_palette.build_commands(window)
    titles = [command.title for command in commands]
    assert titles.count("Restart NeoPedal") == 1 and titles.count("Quit") == 1
    next(command for command in commands if command.title == "Quit").run()
    assert quits == [True]


def test_menus_in_french(window):  # noqa: F811
    from neopedal import i18n
    from neopedal.ui.menu import ConfigMenu, HelpMenu, OverlayMenu

    i18n.set_language("Français")
    try:
        overlay = OverlayMenu("Overlay", window)
        config = ConfigMenu("Settings", window)
        help_menu = HelpMenu("Help", window)
        assert "Recharger les overlays" in texts(overlay)
        assert "Sections" in texts(config)
        titles = texts(help_menu)
        assert "À propos de NeoPedal" in titles and "Assistant de configuration…" in titles
        assert "Palette de commandes\tCtrl+K" in titles
        assert i18n.tr("Support NeoPedal") == "Soutenir NeoPedal"
        for menu in (overlay, config, help_menu):
            menu.deleteLater()
    finally:
        i18n.set_language("English")
    flush()
