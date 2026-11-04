"""Audit I lot A: driver ranks lookups by name & memo, serial only on real changes, rank history kept in memory &
trimmed"""

import os
import threading
import time

import pytest

from neopedal.process import driver_ranks as dr
from tests.test_driver_ranks import storage_text
from tests.test_home_view import home  # noqa: F401

NOON = time.mktime((2026, 10, 18, 12, 0, 0, 0, 0, -1))  # local noon: + a few minutes stays the same day


def counted(calls: list, function):
    """function adding its arguments to calls"""
    def call(*args):
        calls.append(args)
        return function(*args)
    return call


def ranks_of(name, driver=("Silver", 2, 40), steam_id=""):
    return dr.DriverRanks(name, steam_id, "", "", dr.Rank(*driver), None)


# --- B3: index by name & memo of rank_info lookups
def test_find_name_same_as_find_driver():
    drivers = [ranks_of("Keenny Hess"), ranks_of("keenny hess", ("Gold", 1, 0)), ranks_of("Flo"), ranks_of("")]
    watcher = dr.RankWatcher(lambda: dr.Located("", "", ()))
    watcher.drivers = drivers  # set without check: index made by first lookup
    for name in ("Keenny Hess", "KEENNY HESS ", " flo", "", "  ", "Nobody"):
        assert watcher.find_name(name) is dr.find_driver(drivers, name=name)
    assert watcher.find_name("keenny hess") is drivers[0]  # first one kept
    assert watcher.find_name("FLO") is drivers[2]
    watcher.drivers = [ranks_of("Other")]  # list replaced: index made again
    assert watcher.find_name("Flo") is None and watcher.find_name("other") is not None


@pytest.fixture
def lookups(monkeypatch):
    """rank_info lookups on fake ranks: drivers of watcher set by test"""
    from neopedal import rank_info

    monkeypatch.setattr(rank_info.ranks, "poll", lambda: None)
    monkeypatch.setattr(rank_info.ranks, "drivers", [ranks_of("Keenny Hess"), ranks_of("Austin Martin", ("Bronze", 3, 0))])
    found: list[tuple] = []
    monkeypatch.setattr(rank_info.ranks, "find_name", counted(found, rank_info.ranks.find_name))
    return rank_info, found


def test_driver_ranks_memo_until_ranks_change(lookups, monkeypatch):
    rank_info, found = lookups
    assert rank_info.driver_ranks("Keenny Hess#12").driver.text == "Silver 2"
    assert rank_info.driver_ranks("Austin Martin#9566").driver.text == "Bronze 3"
    assert rank_info.driver_ranks("Nobody") is None
    for _ in range(3):  # each update: memo, nothing looked for again
        assert rank_info.driver_ranks("Keenny Hess#12").driver.text == "Silver 2"
        assert rank_info.driver_ranks("Nobody") is None
    assert found == [("Keenny Hess",), ("Austin Martin",), ("Nobody",)]
    # Player ranks changed (list replaced): looked for again
    monkeypatch.setattr(rank_info.ranks, "drivers", [ranks_of("Keenny Hess", ("Gold", 1, 0))])
    assert rank_info.driver_ranks("Keenny Hess#12").driver.text == "Gold 1"
    assert rank_info.driver_ranks("Austin Martin#9566") is None
    # Serial alone incremented (values set without replacing the list): looked for again
    count = len(found)
    monkeypatch.setattr(rank_info.ranks, "serial", rank_info.ranks.serial + 1)
    rank_info.driver_ranks("Keenny Hess#12")
    assert len(found) == count + 1


def test_driver_ranks_memo_bounded(lookups, monkeypatch):
    rank_info, _found = lookups
    monkeypatch.setattr(rank_info, "MEMO_NAMES", 3)
    for name in ("a", "b", "c", "d"):
        rank_info.driver_ranks(name)
    assert len(rank_info._current_memo().ranks) <= 3
    assert rank_info.driver_ranks("Keenny Hess").driver.text == "Silver 2"


STEAM = "76561190000000001"  # Steam ID of the profile of tests.test_driver_ranks.storage_text


def file_watcher(tmp_path, text=None, history_lines=(), mtime=NOON - 3600):
    """Watcher of a game storage file (ranks of the game menu) & history file of tmp_path, clock set by test"""
    path = tmp_path / dr.STORAGE_FILE
    path.write_text(text if text is not None else storage_text(), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    history = tmp_path / dr.HISTORY_FILE
    for entry in history_lines:
        dr.append_history(str(history), entry)
    clock = [0.0]
    watcher = dr.RankWatcher(lambda: dr.Located(str(path), STEAM, ("Keenny Hess",)), lambda: str(history),
                             clock=lambda: clock[0])
    return watcher, clock, path, history


def test_watcher_keeps_equal_drivers_list(tmp_path):
    watcher, clock, path, _history = file_watcher(tmp_path)
    watcher.check()
    drivers, serial = watcher.drivers, watcher.serial
    assert watcher._by_name[0] is drivers  # index made by check (worker), not by first lookup
    path.write_text(storage_text(), encoding="utf-8")  # written again, same ranks
    os.utime(path, (NOON, NOON))
    clock[0] += dr.CHECK_SECONDS
    watcher.check()
    assert watcher.drivers is drivers and watcher.serial == serial


def test_history_of_kept_in_memory(tmp_path, monkeypatch):
    from tests.test_driver_ranks import PROFILE

    old = dr.HistoryEntry(NOON - 7200, dr.Rank("Silver", 3, 80), None, "", STEAM)
    other = dr.HistoryEntry(NOON - 7000, dr.Rank("Bronze", 1, 0), None, "", "76561190000000002")
    watcher, clock, path, history = file_watcher(tmp_path, history_lines=(old, other))
    watcher.check()
    entries = watcher.history_of(STEAM)
    assert isinstance(entries, tuple) and [entry.driver for entry in entries] == [
        dr.Rank("Silver", 3, 80), dr.Rank("Silver", 2, 40)]
    assert len(watcher.history_of("")) == 3  # account unknown: every line, like account_history
    assert list(watcher.history_of("")) == dr.read_history(str(history))
    assert watcher.history_of("76561190000000009") == ()
    monkeypatch.setattr(dr, "read_history", lambda path: pytest.fail("history file read again"))
    path.write_text(storage_text({**PROFILE, "driverRank": {"rank": "Gold", "tier": 1, "progress": 40}}),
                    encoding="utf-8")
    os.utime(path, (NOON + 300, NOON + 300))
    clock[0] += dr.CHECK_SECONDS
    watcher.check()  # rank changed: line added, memory too
    assert [entry.driver.progress for entry in watcher.history_of(STEAM)] == [80, 40, 40]
    assert entries[-1].driver == dr.Rank("Silver", 2, 40)  # snapshot given before never changed
    assert watcher.last_entry(STEAM).driver == dr.Rank("Gold", 1, 40)
    assert [account.steam_id for account in watcher.others] == ["76561190000000002"]


def test_history_of_without_check_and_path_change(tmp_path):
    first, second = tmp_path / "a.history", tmp_path / "b.history"
    dr.append_history(str(first), dr.HistoryEntry(1, dr.Rank("Silver", 1, 0), None, "", STEAM))
    path = [str(first)]
    watcher = dr.RankWatcher(lambda: dr.Located("", "", ()), lambda: path[0])
    assert len(watcher.history_of(STEAM)) == 1  # read once when asked first
    path[0] = str(second)  # config folder changed: read again
    assert watcher.history_of(STEAM) == ()
    assert dr.RankWatcher(lambda: dr.Located("", "", ())).history_of(STEAM) == ()  # no history


def test_trim_history_keeps_last_entry_of_each_account():
    entries = [dr.HistoryEntry(index, dr.Rank("Silver", 1, index), None, "", steam)
               for index, steam in enumerate(["old", "", "a", "a", "b", "a", "a", "a"])]
    kept = dr.trim_history(entries, keep=3)
    assert [entry.time for entry in kept] == [0, 1, 4, 5, 6, 7]  # old, unknown & b kept, newest 3 of a
    assert dr.trim_history(entries, keep=10) == entries


def test_history_file_trimmed(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "HISTORY_KEEP", 5)
    monkeypatch.setattr(dr, "HISTORY_SLACK", 2)
    history = tmp_path / dr.HISTORY_FILE
    dr.append_history(str(history), dr.HistoryEntry(1, dr.Rank("Gold", 1, 0), None, "", "other"))
    watcher = dr.RankWatcher(lambda: dr.Located("", "", ()), lambda: str(history))
    for progress in range(10):
        watcher.record(ranks_of("Keenny Hess", ("Silver", 1, progress)), 100 + progress, STEAM)
        lines = dr.read_history(str(history))
        assert list(watcher.history_of("")) == lines  # memory always same as file
        assert len(lines) <= 5 + 2 + 1
    lines = dr.read_history(str(history))
    assert lines[0].steam_id == "other"  # last line of an account never dropped
    assert lines[-1].driver == dr.Rank("Silver", 1, 9)
    assert not any(name.endswith(".tmp") for name in os.listdir(tmp_path))


def test_history_not_saved_kept_in_memory_for_adopted_account(tmp_path, monkeypatch):
    history = tmp_path / dr.HISTORY_FILE
    dr.append_history(str(history), dr.HistoryEntry(1, dr.Rank("Gold", 1, 0), None))  # line without account
    watcher = dr.RankWatcher(lambda: dr.Located("", "", ()), lambda: str(history))
    monkeypatch.setattr(dr, "append_history", lambda path, entry: False)  # read-only folder
    adopted = watcher.adopt_unknown_account(STEAM)
    assert adopted is not None and watcher.last_entry(STEAM) == adopted
    assert watcher.adopt_unknown_account("76561190000000002") is None  # never given to a second account
    watcher.record(ranks_of("x", ("Silver", 1, 0)), 2, STEAM)  # not saved: not in memory either
    assert watcher.last_entry(STEAM) == adopted


def test_history_concurrent_reader_sees_whole_snapshots(tmp_path):
    history = tmp_path / dr.HISTORY_FILE
    watcher = dr.RankWatcher(lambda: dr.Located("", "", ()), lambda: str(history))
    stop, bad = threading.Event(), []

    def read():
        while not stop.is_set():
            entries = watcher.history_of(STEAM)
            if [entry.time for entry in entries] != list(range(len(entries))):
                bad.append(entries)
            time.sleep(0)  # writer runs too

    reader = threading.Thread(target=read)
    reader.start()
    try:
        for index in range(60):
            watcher.record(ranks_of("x", ("Silver", 1, index % 100)), index, STEAM)
    finally:
        stop.set()
        reader.join(5)
    assert not bad and len(watcher.history_of(STEAM)) == 60


def test_home_driver_card_history_from_memory(home, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    monkeypatch.setattr(rank_info.ranks, "poll", lambda: None)
    monkeypatch.setattr(rank_info.ranks, "_history", dr._History.of(rank_info.history_path(), [
        dr.HistoryEntry(1, dr.Rank("Silver", 1, 90), None, "", "1"),
        dr.HistoryEntry(2, dr.Rank("Bronze", 1, 0), None, "", "2")]))  # other account: left out
    monkeypatch.setattr(dr, "read_history", lambda path: pytest.fail("history file read by page"))
    monkeypatch.setattr(rank_info.ranks, "player", dr.DriverRanks(
        "Keenny Hess", "1", "", "", dr.Rank("Silver", 2, 40), None, ""))
    monkeypatch.setattr(rank_info.ranks, "serial", rank_info.ranks.serial + 1)
    home.backend._driver_key = None
    home.backend.refresh_driver()
    assert home.backend.driver["ranks"][0]["change"] == "+50%"  # 90% S1 -> 40% S2


# --- Architecture 6: storage file not read again while online ranks used
