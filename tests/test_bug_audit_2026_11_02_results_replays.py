"""Bug audit of the Results & Replays page (2026-11-02): regression tests of the fixes (B-xxx: report numbers)"""

import os
import re
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

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


# B-004: end of a copy wrote over a replay that took its name during the copy (renamed in the page, saved by game)
def test_b004_copy_never_writes_over_a_replay_named_meanwhile(tmp_path):
    from neopedal.ui.quick import replay_files

    game, downloads = tmp_path / "Replays", tmp_path / "Downloads"
    game.mkdir()
    downloads.mkdir()
    (game / "Spa R1 1.Vcr").write_bytes(b"game replay")
    (game / "My best race.Vcr").write_bytes(b"precious")
    source = downloads / "Spa R1 1.Vcr"
    source.write_bytes(b"z" * (replay_files.CHUNK_SIZE * 2))
    renamed: list[str] = []

    def progress(_value: float):
        if not renamed:  # during the copy: renamed in the page to the name the copy will take, game saves one too
            renamed.append(replay_files.rename_replay(str(game), "My best race", "Spa R1 1 (2)"))
            (game / "Spa R1 1 (2).Vcr").write_bytes(b"saved by game")

    result = replay_files.copy_replays([str(source)], str(game), progress)
    assert renamed == ["name already used"]  # name of the replay being copied refused
    assert (game / "My best race.Vcr").read_bytes() == b"precious"
    assert (game / "Spa R1 1 (2).Vcr").read_bytes() == b"saved by game"  # never written over
    assert result.added == ["Spa R1 1 (3)"] and (game / "Spa R1 1 (3).Vcr").stat().st_size == source.stat().st_size
    assert not list(game.glob("*.part"))


# B-005: on a drive without recycle bin (USB stick, network drive), "moved to the recycle bin" deleted replays for good
def test_b005_no_recycle_bin_asks_to_delete_for_good(replays_page, monkeypatch, tmp_path):  # noqa: F811
    from neopedal.ui.quick import dialogs, replay_files

    backend = page_of_replays(replays_page, tmp_path / "Replays", "AB")
    asked: list[tuple[str, str]] = []

    def confirm(parent, title, text, action, on_result, **kwargs):
        asked.append((text, action))
        on_result(True)

    monkeypatch.setattr(dialogs, "confirm", confirm)
    monkeypatch.setattr(replay_files, "QFile", SimpleNamespace(moveToTrash=lambda path: True))
    monkeypatch.setattr(replay_files, "recycle_bin", lambda folder: False)
    backend.deleteReplays("A")
    wait_requests(backend.request_trash)
    assert "for good" in asked[0][0] and "no recycle bin" in asked[0][0] and asked[0][1] == "Delete Permanently"
    assert backend.noticeText == "1 replay(s) deleted for good"
    monkeypatch.setattr(replay_files, "recycle_bin", lambda folder: True)  # usual drive: recycle bin as before
    backend.deleteReplays("B")
    wait_requests(backend.request_trash)
    assert "recycle bin?" in asked[1][0] and backend.noticeText == "1 replay(s) moved to the recycle bin"


@pytest.mark.skipif(sys.platform != "win32", reason="drive types of Windows")
def test_b005_recycle_bin_of_drives(tmp_path):
    from neopedal.ui.quick import replay_files

    assert replay_files.recycle_bin(str(tmp_path))  # fixed drive
    assert not replay_files.recycle_bin("//no-such-server/share/Replays")  # network share


# B-003: action of a replay taken as open from a stale state (page hidden, polling stopped, game left the replay) sent
# its focus & time to the game at once, without confirmation
def test_b003_action_on_stale_state_asks_and_opens_replay(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import dialogs
    from neopedal.ui.quick.replays_common import ReplayAction

    backend = answered(replays_page, GAME_ANSWERS)
    asked: list[str] = []
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action, on_result, **kwargs: asked.append(text))
    backend.playing = "Bahrain R1"  # opened from the page, open in game (told by the answer just received)
    action = ReplayAction("Bahrain R1", 300.0, ("Kevin Ramirez",))
    replays_page.sent.clear()
    backend.watch("Bahrain R1", action)  # recent answer: done at once
    wait_commands(backend)
    assert not asked and ("PUT", "/rest/watch/replaytime/295") in replays_page.sent
    replays_page.sent.clear()
    backend.state_time -= 60  # page hidden for a minute: the game may have left the replay
    backend.watch("Bahrain R1", action)
    wait_commands(backend)
    assert asked and "Open replay" in asked[0] and replays_page.sent == []


# B-006: map of a replay drew its cars at positions read in shared memory, frozen during replays (another session's)
def test_b006_replay_map_never_uses_shared_memory(replays_page, monkeypatch):  # noqa: F811
    from tests.test_replay_map_motion import FakeReader

    backend = replays_page.backend
    reader = FakeReader([(7, 890.0, -241.0)])  # slot of the replay, position of another session
    monkeypatch.setattr(type(backend), "reader", staticmethod(lambda: reader))
    backend.setPanel(2)
    answered(replays_page, GAME_ANSWERS)  # replay open
    replays_page.resize(1400, 860)
    replays_page.show()
    for _ in range(10):
        QCoreApplication.processEvents()
    assert backend.gameState == "replay" and backend.map_center and backend._shown
    backend.read_live_positions()
    assert not backend.live_wanted() and backend.mapLive == {}


# B-007: one click on an incident in a live session sent the game to its replay, without confirmation
def test_b007_jump_in_live_session_asks_first(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import dialogs

    backend = answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": False})
    assert backend.gameState == "session"
    answers: list[bool] = [False]
    asked: list[str] = []

    def confirm(parent, title, text, action, on_result, **kwargs):
        asked.append(text)
        on_result(answers[0])

    monkeypatch.setattr(dialogs, "confirm", confirm)
    key = backend.incidentRows.rows[1]["key"]
    replays_page.sent.clear()
    backend.jumpTo(key, "")  # cancelled: the game stays live
    wait_commands(backend)
    assert asked and "session" in asked[0] and replays_page.sent == []
    answers[0] = True
    backend.jumpTo(key, "")
    wait_commands(backend)
    assert ("POST", "/rest/replay/toggleactive") in replays_page.sent


# B-008: replay of the live session showed live time & laps (standings stay live), lap steps never reached their lap,
# and the jump sent right after the replay opened could be ignored by the game
def test_b008_replay_of_live_session_time_and_laps_unknown(replays_page, monkeypatch):  # noqa: F811
    backend = answered(replays_page, GAME_ANSWERS)
    assert backend.replayTime > 0 and backend.cameraLap > 0  # replay of a recorded session: from standings
    backend.rewatching = True  # replay of the live session opened by a jump
    answered(replays_page, GAME_ANSWERS)
    assert backend.replayTime == -1 and backend.cameraLap == 0
    replays_page.sent.clear()
    backend.stepLap(1)
    wait_commands(backend)
    assert replays_page.sent == [] and backend.noticeError and "timeline" in backend.noticeText


def test_b008_live_replay_waits_before_taking_commands(monkeypatch):
    from neopedal.ui.quick import replays_common

    slept: list[float] = []
    monkeypatch.setattr(replays_common.time, "sleep", slept.append)
    active = iter([False, False, True])
    connection = SimpleNamespace(get=lambda resource: next(active), send=lambda *args: True)
    assert replays_common.enter_replay(connection)
    assert slept[-1] == replays_common.REPLAY_READY  # replay open: commands after a moment
