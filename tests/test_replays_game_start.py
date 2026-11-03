"""Le Mans Ultimate started from the Results & Replays page (Steam), replay asked meanwhile opened once it answers"""

import time

from PySide6.QtCore import QCoreApplication

from tests.test_game_info import GAME_ANSWERS, answered, replays_page, wait_commands, wait_requests  # noqa: F401

MENU_ANSWERS = {**GAME_ANSWERS, "/rest/replay/isActive": None}  # game running, in its menus


def offline(page, monkeypatch, steam=True):
    """Page shown with the game not running, Steam start and confirmations recorded (confirmed)"""
    from neopedal.ui.quick import dialogs, replays_list

    started, confirms = [], []
    monkeypatch.setattr(replays_list, "start_game", lambda: started.append(1) or steam)
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action, on_result, **kwargs: (
        confirms.append(text), on_result(True)))
    backend = answered(page, {})
    assert backend.gameState == "offline" and not backend.gameStarting
    return backend, started, confirms


def pump(seconds: float):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()


def answer_state(backend, answers, page):
    """Next state answer of the timer (not F5), then replays list asked meanwhile"""
    page.game.answers = answers
    backend.refresh_state()
    wait_requests(backend.request_state)
    wait_requests(backend.request_replays)


def test_replay_asked_offline_opens_once_started_game_answers(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick.replays_common import ReplayAction

    backend, started, confirms = offline(replays_page, monkeypatch)
    replays_page.sent.clear()
    backend.watch_named("Bahrain R1", ReplayAction("Bahrain R1", 300.0, ("Kevin Ramirez",)))
    wait_requests(backend.request_replays, backend.request_state)
    assert started == [1] and len(confirms) == 1 and "Start it, then open replay <b>Bahrain R1</b>" in confirms[0]
    assert backend.gameStarting and backend.statusText == "Starting Le Mans Ultimate…"
    assert backend.pending_watch == "Bahrain R1" and backend.pending_action is not None
    answer_state(backend, {}, replays_page)  # still starting: kept, nothing told
    assert backend.gameStarting and backend.pending_watch == "Bahrain R1" and not backend.noticeError
    answer_state(backend, MENU_ANSWERS, replays_page)  # game answers its state first: replays listed, replay opened
    wait_commands(backend)
    assert not backend.gameStarting and backend.pending_watch == "" and len(confirms) == 1  # never asked again
    assert ("GET", "/rest/watch/play/1") in replays_page.sent and backend.openingReplay == "Bahrain R1"
    assert backend.action is not None and backend.action.time == 300.0  # done once the replay is open
    assert started == [1]


def test_start_given_up_when_game_never_answers(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick.replays_common import ReplayAction

    backend, _started, _confirms = offline(replays_page, monkeypatch)
    backend.watch_named("Bahrain R1", ReplayAction("Bahrain R1"))
    wait_requests(backend.request_replays, backend.request_state)
    assert backend.gameStarting
    backend.launching_until = time.monotonic() - 1.0  # 5 minutes passed
    answer_state(backend, {}, replays_page)
    assert not backend.gameStarting and backend.pending_watch == "" and backend.noticeError
    assert "did not answer after it was started" in backend.noticeText
    assert backend.statusText.startswith("Game not answering")
    answer_state(backend, MENU_ANSWERS, replays_page)  # started later by hand: replay never opened on its own
    wait_commands(backend)
    assert not any(command[1].startswith("/rest/watch/play/") for command in replays_page.sent)


def test_start_button_and_stop_waiting(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick.replays_common import ReplayAction

    backend, started, confirms = offline(replays_page, monkeypatch)
    backend.startGame()
    backend.startGame()  # already starting: Steam not asked twice
    assert started == [1] and not confirms and backend.gameStarting
    backend.watch_named("Bahrain R1", ReplayAction("Bahrain R1"))  # asked while starting: no other start
    wait_requests(backend.request_replays, backend.request_state)
    assert started == [1] and not confirms and backend.pending_watch == "Bahrain R1"
    backend.cancelStart()
    assert not backend.gameStarting and backend.pending_watch == ""
    answer_state(backend, MENU_ANSWERS, replays_page)
    wait_commands(backend)
    assert backend.replayCount > 0 and backend.openingReplay == ""  # game followed, replay not opened
    backend.startGame()  # game running: never started again
    assert started == [1]


def test_steam_not_opened_told(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick.replays_common import ReplayAction

    backend, started, confirms = offline(replays_page, monkeypatch, steam=False)
    backend.watch_named("Bahrain R1", ReplayAction("Bahrain R1"))
    wait_requests(backend.request_replays, backend.request_state)
    assert started == [1] and confirms and not backend.gameStarting and backend.pending_watch == ""
    assert backend.noticeError and "Steam could not be opened" in backend.noticeText


def test_replays_listed_when_game_answers_state_first(replays_page):  # noqa: F811
    """Game started by hand while the page shows: its replays listed without F5 (state answered before the list)"""
    backend = answered(replays_page, {})
    assert backend.replayCount == 0
    answer_state(backend, MENU_ANSWERS, replays_page)
    assert backend.gameState == "menu" and backend.replayCount > 0


def test_start_button_shown_offline(replays_page, monkeypatch):  # noqa: F811
    from tests.test_lap_viewer_fix_list import everything

    backend, _started, _confirms = offline(replays_page, monkeypatch)
    replays_page.resize(1400, 860)
    replays_page.show()
    deadline = time.monotonic() + 3.0
    root = replays_page.view.rootObject()

    def button(name):
        return next((item for item in everything(root) if item.objectName() == name), None)

    while button("startGameButton") is None and time.monotonic() < deadline:
        QCoreApplication.processEvents()
    start = button("startGameButton")
    assert start is not None and start.property("visible")
    state = next(item for item in everything(root) if item.objectName() == "replayListState")
    assert state.property("actionText") == "Start LMU"
    backend.startGame()
    QCoreApplication.processEvents()
    assert not button("startGameButton").property("visible") and button("cancelStartButton").property("visible")
    assert state.property("loading") and state.property("loadingText") == "Starting Le Mans Ultimate…"
    assert not replays_page.view.errors()


def test_page_dialog_follows_window_change(ui_env):
    """Results page made before the app shows it: QQuickWidget gives it another window once in the app, its
    confirmations (start the game, open a replay) shown in that window, not in the former one (never opened)"""
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtQuick import QQuickWindow

    from neopedal.ui import race_results_viewer
    from neopedal.ui.quick import dialogs

    page = race_results_viewer.RaceResultsViewer(None)
    other = QQuickWindow()
    try:
        page.resize(1400, 860)
        page.show()
        pump(0.3)
        root = page.view.rootObject()
        dialog = root.findChild(QObject, "bridgeDialog")
        other.resize(1400, 860)
        root.setParentItem(other.contentItem())  # window made again, as QQuickWidget does once in the app
        other.show()
        pump(0.3)
        dialogs.confirm(page, "Start Le Mans Ultimate", "Start it?", "Start and Watch", lambda chosen: None)
        pump(0.3)
        assert dialog.property("opened") and dialog.property("parent").window() is other
    finally:
        root.setParentItem(None)
        other.close()
        page.close()
        page.deleteLater()
        other.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
