"""Tool pages outside the rail kept built a while once left (opened again at once), loading text never hidden by
the page fade, rail tool modules imported ahead (2026-11-04, page open times)"""

import sys

from PySide6.QtWidgets import QApplication

from tests.test_dialog_pages import settle, window  # noqa: F401  (fixture)

STREAM = "stream_overlay_view.StreamOverlaysView"
EDITORS = "data_editors.DataEditors"


def shown(main):
    main.show()
    settle()
    return main.centralWidget()


def names(view):
    return [type(page.dialog).__name__ for page in view.dialog_pages()]


def test_left_tool_page_parked_and_shown_again(window):  # noqa: F811
    from neopedal.ui.tools_view import open_tool

    view = shown(window)
    dialog = open_tool(STREAM, window)
    assert names(view) == ["StreamOverlaysView"]
    view.set_current_index(0)
    settle()
    assert names(view) == [] and [page.dialog for page in view._parked] == [dialog]  # closed for the user
    assert not view._button_pages.isVisibleTo(view)  # no open page listed behind
    assert view.open_page_paths() == []  # never reopened at next start
    assert open_tool(STREAM, window) is dialog  # same page back, not built again
    assert names(view) == ["StreamOverlaysView"] and not view._parked
    assert view._pages.currentWidget().dialog is dialog
    view.close_parked_pages(True)


def test_parked_pages_closed_when_old_hidden_or_quit(window, monkeypatch):  # noqa: F811
    from neopedal.ui import app_tab_view
    from neopedal.ui.tools_view import open_tool

    view = shown(window)
    closed = []
    dialog = open_tool(STREAM, window)
    dialog.destroyed.connect(lambda *_: closed.append("stream"))
    view.set_current_index(0)
    settle()
    assert len(view._parked) == 1
    view.close_parked_pages()  # timer: not old yet
    assert len(view._parked) == 1
    clock = app_tab_view.time.monotonic() + app_tab_view.PARKED_MS / 1000 + 1
    monkeypatch.setattr(app_tab_view.time, "monotonic", lambda: clock)
    view.close_parked_pages()
    assert not view._parked
    open_tool(EDITORS, window)
    view.set_current_index(0)
    settle()
    assert len(view._parked) == 1
    assert view.close_all_pages(build_behind=False)  # quit
    assert not view._parked


def test_parked_pages_limit_and_new_copy(window, monkeypatch):  # noqa: F811
    from neopedal.ui import app_tab_view
    from neopedal.ui.tools_view import open_tool

    monkeypatch.setattr(app_tab_view, "PARKED_PAGES", 1)
    view = shown(window)
    open_tool(STREAM, window)
    view.set_current_index(0)
    settle()
    open_tool(EDITORS, window)
    view.set_current_index(0)
    settle()
    assert [type(page.dialog).__name__ for page in view._parked] == ["DataEditors"]  # oldest closed
    view.close_parked_pages("DataEditors")
    assert not view._parked


def test_hidden_window_never_parks(window):  # noqa: F811
    from neopedal.ui.tools_view import open_tool

    view = shown(window)
    open_tool(STREAM, window)
    window.hide()
    view.set_current_index(0)
    settle()
    assert not view._parked and names(view) == []


def test_loading_text_not_hidden_by_fade(window, monkeypatch):  # noqa: F811
    from neopedal.ui import lazy_page
    from neopedal.ui.lazy_page import LazyPage

    view = shown(window)
    monkeypatch.setattr(lazy_page, "animations_enabled", lambda: True)
    view._page_fade._enabled = None
    index = next(index for index in range(view._pages.count())
                 if isinstance(view._pages.widget(index), LazyPage) and view._pages.widget(index).page is None
                 and index != view._pages.currentIndex())
    page = view._pages.widget(index)
    seen = []
    original = page.ensure_page

    def ensure_page():
        seen.append(view._page_fade.isVisible())  # while the loading text is painted
        original()

    monkeypatch.setattr(page, "ensure_page", ensure_page)
    view.set_current_index(index)
    assert seen and seen[0] is False
    assert view._page_fade.isVisible()  # built page fades in
    QApplication.processEvents()


def test_rail_tool_modules_imported_ahead(window, monkeypatch):  # noqa: F811
    from neopedal import realtime_state
    from neopedal.ui import app_tab_view

    view = shown(window)
    imported = []
    monkeypatch.setattr(app_tab_view, "import_module", lambda name: imported.append(name))
    modules = view.preimport_modules()
    assert modules and all(name.startswith("neopedal.ui.") for name in modules)  # tools of the default rail
    assert all(name not in sys.modules for name in modules)
    monkeypatch.setattr(realtime_state, "active", True)
    view.preimport_next()
    assert not imported  # driving: waits
    monkeypatch.setattr(realtime_state, "active", False)
    view.preimport_next()
    assert imported == modules[:1] and view._preimport_timer.isActive()
    view._preimport_timer.stop()
