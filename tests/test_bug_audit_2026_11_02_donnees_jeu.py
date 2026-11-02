"""Bug audit 2026-11-02, game data acquisition (audit_bugs_donnees_jeu_2026-11-02.md): B-001 to B-039

Shared memory sync loop driven tick by tick (Ticks: no thread, fake clock), data modules on scripted readers,
REST cache & replay on local data: deterministic, no game, no fixed network port.
"""

import pytest

from neopedal import realtime_state
from neopedal.adapter import _sync, lmu_connector
from neopedal.module import module_mapping
from neopedal.module_info import MappingInfo
from pyLMUSharedMemory import lmu_data
from tests.test_module_mapping_stats_notes import drive_map_lap, tele  # noqa: F401


class MemoryShmm:
    """LMU shared memory zone kept in memory (no mmap), same interface as MMapControl"""

    def __init__(self):
        self.data = lmu_data.LMUObjectOut()

    def create(self, *args):
        pass

    def update(self):
        return None  # unknown whether changed, like direct access

    def close(self):
        pass


class Ticks:
    """Event of sync update loop: each wait runs next step (game writes between ticks), fake monotonic clock

    The loop runs in the test thread (sync._SyncData__update_loop(ticks)) and ends once steps are used up.
    """

    def __init__(self, monkeypatch, steps=()):
        self.now = 1000.0
        self.steps = list(steps)
        monkeypatch.setattr(_sync, "monotonic", lambda: self.now)

    def wait(self, delay: float) -> bool:
        self.now += delay
        if not self.steps:
            return True
        self.steps.pop(0)()
        return False

    def is_set(self) -> bool:
        return not self.steps


@pytest.fixture
def lmu_game(monkeypatch):
    """LMU sync data on in-memory structure, 3 cars (slot ids 3, 5, 7, same order in telemetry), player slot 3"""
    for name in ("resets", "active", "paused"):  # realtime state written by sync loop, restored after test
        monkeypatch.setattr(realtime_state, name, getattr(realtime_state, name))
    sync = lmu_connector.SyncData()
    shmm = MemoryShmm()
    sync.dataset.shmm = shmm
    data = shmm.data
    data.scoring.scoringInfo.mNumVehicles = 3
    data.telemetry.activeVehicles = 3
    data.scoring.scoringInfo.mCurrentET = 10.0
    for index, slot_id in enumerate((3, 5, 7)):
        data.scoring.vehScoringInfo[index].mID = slot_id
        data.scoring.vehScoringInfo[index].mDriverName = b"Driver %d" % slot_id
        data.telemetry.telemInfo[index].mID = slot_id
        data.telemetry.telemInfo[index].mFuel = float(slot_id)
    data.scoring.vehScoringInfo[0].mIsPlayer = True
    return sync, data


def run_loop(sync, ticks) -> None:
    """Sync loop as started by _start_updating (first player sync), in test thread"""
    sync._update_indexes()
    if not sync._SyncData__sync_player_data():
        sync._SyncData__sync_player_scor()
        sync._SyncData__sync_player_tele()
    sync._SyncData__update_loop(ticks)


# --- B-001: followed car change counted as a reset at once, not on next scoring sample
def test_b001_followed_car_change_resets_before_next_scoring_sample(lmu_game, monkeypatch):
    sync, data = lmu_game
    seen = []

    def follow(slot_id):
        def step():
            sync.override_player_index = True
            sync.player_slot_id = slot_id
        return step

    def record():
        seen.append((sync.player_scor.mID, sync.resets, realtime_state.resets))

    def next_sample():
        data.scoring.scoringInfo.mCurrentET += 0.2

    # Resume & first sync, then follow car 5 while scoring sample time stays the same (5 Hz scoring)
    steps = [next_sample, next_sample, lambda: None, record, follow(5), record, record, next_sample, record]
    run_loop(sync, Ticks(monkeypatch, steps))
    first, switched, same_sample, after_sample = seen
    assert first[0] == 3
    assert switched[0] == 5  # new car read by modules from this tick
    assert switched[1] == first[1] + 1  # reset counted on the same tick, not on next scoring sample
    assert switched[2] == switched[1]  # published to modules at once (not on next overlay control poll)
    assert same_sample[1] == after_sample[1] == switched[1]  # never counted twice


def test_b001_track_map_of_lap_cut_short_not_saved(tele, tmp_path):  # noqa: F811
    filepath = f"{tmp_path.as_posix()}/"
    output = MappingInfo()
    gen = module_mapping.record_track_map(output, filepath)
    tele.update({"timing.start": 0.0, "timing.last_laptime": -1.0})
    gen.send(1)
    # Lap start of another car followed ends the lap at 3/4 of the track (both sector lines crossed)
    drive_map_lap(tele, gen, lap_start=10.0, length=3000.0)
    tele.update({"timing.start": 100.0, "timing.current_laptime": 2.0, "timing.last_laptime": 90.0})
    gen.send(1)
    gen.send(1)
    assert not (tmp_path / "SimTrack.svg").exists()


# --- B-002: lap waiting for validation dropped once another car is followed
@pytest.fixture
def followed(monkeypatch):
    """Scripted reader of car followed: car["slot"] slot id, car["last"] game last lap time"""
    from types import SimpleNamespace

    from neopedal.api_control import api

    car = {"slot": 3, "last": 0.0, "index": 0}
    monkeypatch.setattr(api, "read", SimpleNamespace(
        vehicle=SimpleNamespace(slot_id=lambda index=None: car["slot"], player_index=lambda: car["index"]),
        timing=SimpleNamespace(last_laptime=lambda index=None: car["last"]),
    ))
    monkeypatch.setattr(realtime_state, "active", True)
    return car


def test_b002_pending_lap_of_former_car_dropped_at_once(followed):
    from neopedal.module._base import PendingLap
    from neopedal.module._lap_state import LOAD, LapState

    resolved = []
    state = LapState(lambda lap, valid: resolved.append(valid))
    state.receive(0)
    state.pending = PendingLap(90.0, 120.0)  # car 3 just crossed the line, game lap time not given yet
    followed["slot"] = 5  # another car followed: its last lap time never matches
    followed["last"] = 95.0
    assert state.receive(1) == LOAD  # new car loaded at once, not after PENDING_WAIT
    assert resolved == [False] and state.pending is None


def test_b002_pending_lap_still_waits_for_same_car(followed):
    from neopedal.module._base import PendingLap
    from neopedal.module._lap_state import LOAD, SKIP, LapState

    state = LapState(lambda lap, valid: None)
    state.receive(0)
    state.pending = PendingLap(90.0, 120.0)
    followed["index"] = -1  # player left (not synced): lap still waits for the game lap time
    assert state.receive(1) == SKIP and state.pending is not None
    followed["index"] = 0
    followed["last"] = 90.0  # back to garage just after the line: same car validates its lap
    assert state.receive(1) == LOAD and state.pending is None
