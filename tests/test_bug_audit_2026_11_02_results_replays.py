"""Bug audit of the Results & Replays page (2026-11-02): regression tests of the fixes (B-xxx: report numbers)"""

import os
import re
from types import SimpleNamespace

from tests.test_dialog_pages import window  # noqa: F401 (window: fixture)
from tests.test_game_info import GAME_ANSWERS, answered, replays_page, wait_commands, wait_requests  # noqa: F401 (fixtures)

CTRL = 0x04000000  # Qt.KeyboardModifier.ControlModifier
QML = os.path.join(os.path.dirname(__file__), "..", "neopedal", "ui", "qml", "analysis")


def page_of_replays(replays_page, folder, names: str):  # noqa: F811
    """Replays page listing a replay file of folder for each name (newest last)"""
    folder.mkdir()
    for name in names:
        (folder / f"{name}.Vcr").write_bytes(b"replay")
    listed = [{"id": index, "replayName": name, "size": 1000, "timestamp": 1791165314 + index, "metadata": {}}
              for index, name in enumerate(names)]
    return answered(replays_page, {**GAME_ANSWERS, "/rest/watch/replays": listed,
                                   "/rest/watch/replay/getReplayFolder": {"custom": "", "default": str(folder)}})


# B-001: replay deselected with Ctrl stayed the replay given to the actions of the selection (Delete key, Delete of
# the selection bar, Export & Protect of the menu): it was moved to the recycle bin instead of the selected ones
def test_b001_ctrl_deselected_replay_not_deleted(replays_page, monkeypatch, tmp_path):  # noqa: F811
    from neopedal.ui.quick import dialogs, replay_files

    backend = page_of_replays(replays_page, tmp_path / "Replays", "ABC")
    backend.clickReplay("C", 0)
    backend.clickReplay("B", CTRL)
    backend.clickReplay("A", CTRL)
    backend.clickReplay("A", CTRL)  # A deselected: B & C left, A stays the current row (Shift range anchor)
    assert backend.checked == {"B", "C"} and backend.selectedReplay == "A"
    assert backend.selectionKey() in {"B", "C"}
    trashed: list[str] = []

    def move_to_trash(path: str) -> bool:
        trashed.append(path)
        return True

    monkeypatch.setattr(dialogs, "confirm", lambda *args, **kwargs: args[4](True))
    monkeypatch.setattr(replay_files, "QFile", SimpleNamespace(moveToTrash=move_to_trash))
    backend.deleteReplays(backend.selectionKey())
    wait_requests(backend.request_trash)
    assert sorted(os.path.basename(path) for path in trashed) == ["B.Vcr", "C.Vcr"]


def test_b001_selection_key_is_current_replay_otherwise(replays_page, tmp_path):  # noqa: F811
    backend = page_of_replays(replays_page, tmp_path / "Replays", "ABC")
    backend.clickReplay("C", 0)
    assert backend.selectionKey() == "C"
    backend.clickReplay("A", CTRL)
    assert backend.selectionKey() == "A"  # current replay selected
    backend.clickReplay("A", CTRL)
    backend.clickReplay("C", CTRL)  # nothing selected: current replay alone
    assert backend.checked == set() and backend.selectionKey() == backend.selectedReplay == "C"


def test_b001_selection_actions_of_page_use_selection_key():
    with open(os.path.join(QML, "ReplayList.qml"), encoding="utf-8") as file:
        source = file.read()
    for action in ("deleteReplays", "exportReplays", "toggleProtected"):
        assert not re.search(rf"{action}\(replays\.selectedReplay\)", source), action
    assert len(re.findall(r"(?:deleteReplays|exportReplays|toggleProtected)\(replays\.selectionKey\(\)\)", source)) == 5


SHOW_HUD = [("POST", "/rest/hud/toggleAllComponents/true"), ("POST", "/rest/sessions/setHudOnWatchScreen", "true"),
            ("POST", "/rest/watch/replay/setReplayUIVisible", "true")]


# B-002: HUD hidden from the page stayed hidden once the replay was left (in the next race too)
def test_b002_hud_hidden_in_replay_shown_again_once_replay_left(replays_page):  # noqa: F811
    backend = answered(replays_page, GAME_ANSWERS)
    assert backend.gameState == "replay"
    backend.setHudShown(False)
    wait_commands(backend)
    assert ("POST", "/rest/hud/toggleAllComponents/false") in replays_page.sent
    replays_page.sent.clear()
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": False})  # back to the live session
    wait_commands(backend)
    assert backend.gameState == "session" and replays_page.sent == SHOW_HUD
    replays_page.sent.clear()
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": None})  # shown once only
    wait_commands(backend)
    assert replays_page.sent == []


def test_b002_hud_part_hidden_shown_again_and_live_session_asks_first(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import dialogs

    backend = answered(replays_page, GAME_ANSWERS)
    backend.toggleHudComponent("chat")  # shown in GAME_ANSWERS: hidden by the page
    wait_commands(backend)
    replays_page.sent.clear()
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": False,
                            "/rest/hud": {"chat": False, "mfd": True, "speedo": False}})
    wait_commands(backend)
    assert replays_page.sent == [("POST", "/rest/hud/toggle/chat")]  # speedo hidden in game: left as it is
    # Live session: hidden only once confirmed
    asked: list[str] = []
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action, on_result, **kwargs: asked.append(text))
    replays_page.sent.clear()
    backend.setHudShown(False)
    wait_commands(backend)
    assert asked and "session" in asked[0] and replays_page.sent == []


def test_b002_hud_hidden_shown_again_when_page_closed(replays_page):  # noqa: F811
    import time

    backend = answered(replays_page, GAME_ANSWERS)
    backend.setHudShown(False)
    wait_commands(backend)
    replays_page.sent.clear()
    backend.release_resources()  # page closed while the replay is open
    end = time.monotonic() + 5
    while replays_page.sent != SHOW_HUD and time.monotonic() < end:
        time.sleep(0.01)
    assert replays_page.sent == SHOW_HUD
