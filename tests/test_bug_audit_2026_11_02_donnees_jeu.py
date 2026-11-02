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
from tests.test_module_vehicles_field import field  # noqa: F401


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


# --- B-003: laps, consumption & track measures of a car followed (spectate) never saved as the player's
class Follow:
    """Reader of the car followed: telemetry_sim cars sharing one clock, follow.car picks the one read"""

    def __init__(self, sims):
        from tests.telemetry_sim import fake_reader

        self.sims = sims
        self.car = 0
        self.readers = [fake_reader(sim) for sim in sims]
        for slot_id, (sim, reader) in enumerate(zip(sims, self.readers), 10):
            reader.session.identifier = lambda sim=sim: (1, int(sim.elapsed), sim.lap_index)
            reader.vehicle.slot_id = lambda index=None, slot_id=slot_id: slot_id

    def __getattr__(self, name):
        return getattr(self.readers[self.car], name)


def run_delta(monkeypatch, tmp_path, switch_at: float, spectate: bool, seconds: float = 200.0):
    """Delta module on car A (60 s laps), car B (58 s laps, 25 s into its lap) followed from switch_at,
    returns delta output & seconds of each tick after the switch with (lapTimeSession, lapTimeStint)"""
    from types import SimpleNamespace

    from neopedal import validator
    from neopedal.api_control import api
    from neopedal.module import _base, module_delta
    from neopedal.module_info import DeltaInfo
    from tests.telemetry_sim import LapSim

    now = {"t": 1000.0}
    monkeypatch.setattr(validator, "time", SimpleNamespace(time=lambda: now["t"]))
    monkeypatch.setattr(_base, "monotonic", lambda: now["t"])
    monkeypatch.setattr(module_delta, "queue_save", lambda saver, *args, sync=False, **kwargs: saver(*args, **kwargs))
    monkeypatch.setattr(realtime_state, "active", True)
    monkeypatch.setattr(realtime_state, "spectating", False)
    step = 0.02
    car_a = LapSim([60.0] * 20, step=step)
    car_b = LapSim([58.0] * 20, step=step)
    car_b.lap_start = -25.0
    follow = Follow([car_a, car_b])
    monkeypatch.setattr(api, "read", follow)
    output = DeltaInfo()
    gen_dist = module_delta.calc_delta_distance(output=output)
    gen = module_delta.calc_delta_time(
        output=output, filepath=f"{tmp_path.as_posix()}/", min_delta_distance=5, delta_smoothing_samples=1,
        laptime_pace_samples=6, laptime_pace_margin=5)
    resets = 1
    after = []
    for _ in range(int(seconds / step)):
        car_a.tick()
        car_b.tick()
        now["t"] += step
        if follow.car == 0 and car_a.elapsed >= switch_at:
            follow.car = 1
            resets += 1
            realtime_state.spectating = spectate
        gen_dist.send(resets)
        gen.send(resets)
        if follow.car == 1:
            after.append((car_a.elapsed - switch_at, output.lapTimeSession, output.lapTimeStint))
    return output, after


def delta_best_laptime(tmp_path) -> float:
    from neopedal.const_common import DELTA_DEFAULT, MAX_SECONDS
    from neopedal.userfile.delta_best import read_delta_best_file

    (_, laptime), _ = read_delta_best_file(f"{tmp_path.as_posix()}/", "SimTrack - SimCar", (DELTA_DEFAULT, MAX_SECONDS))
    return laptime


def test_b003_followed_car_laps_never_saved_as_delta_best(monkeypatch, tmp_path):
    from neopedal.const_common import MAX_SECONDS

    output, _ = run_delta(monkeypatch, tmp_path, switch_at=10.0, spectate=True)
    assert output.lapTimeBest == pytest.approx(58.0, abs=0.05)  # car followed still shown
    assert delta_best_laptime(tmp_path) == MAX_SECONDS  # never saved as the player's
    assert not list(tmp_path.glob("*.session*"))


def test_b003_own_laps_still_saved(monkeypatch, tmp_path):
    run_delta(monkeypatch, tmp_path, switch_at=1000.0, spectate=False, seconds=130.0)  # car A only
    assert delta_best_laptime(tmp_path) == pytest.approx(60.0, abs=0.05)


def test_b003_lap_state_saves_only_data_loaded_for_own_car(monkeypatch):
    from neopedal.module._lap_state import LapState

    saves = []
    monkeypatch.setattr(realtime_state, "active", True)
    monkeypatch.setattr(realtime_state, "spectating", True)
    state = LapState(lambda lap, valid: None, lambda: saves.append(1))
    state.receive(1)  # loaded while spectating another car
    state.delayed_save = True
    monkeypatch.setattr(realtime_state, "spectating", False)  # spectate off: reset, data of car followed
    state.receive(2)
    assert saves == [] and not state.delayed_save
    state.delayed_save = True
    state.receive(3)  # data loaded for own car: saved
    assert saves == [1]


def test_b003_stint_history_and_track_info_not_saved_while_spectating(tele, monkeypatch, tmp_path):  # noqa: F811
    from neopedal.module import module_mapping as mapping
    from neopedal.module import module_stint
    from neopedal.module_info import HistoryInfo

    saved = []
    monkeypatch.setattr(mapping, "save_track_info", lambda name, **values: saved.append(("track", values)))
    monkeypatch.setattr(module_stint, "queue_save", lambda *args, **kwargs: saved.append(("history",)))
    monkeypatch.setattr(realtime_state, "spectating", True)
    info = mapping.record_track_info(MappingInfo())
    history = module_stint.record_consumption_history(HistoryInfo(), f"{tmp_path.as_posix()}/")
    info.send(1)
    history.send(1)
    tele.update({"vehicle.in_pits": 0, "vehicle.speed": 30.0, "lap.distance": 100.0})
    info.send(1)
    tele.update({"vehicle.in_pits": 1, "lap.distance": 3900.0})  # car followed enters pit lane: measured
    info.send(1)
    monkeypatch.setattr(realtime_state, "spectating", False)
    info.send(2)  # reset: measures of the car followed dropped
    history.send(2)
    info.send(3)  # own car: nothing measured (new track only added)
    assert saved == [("track", {})]


@pytest.mark.parametrize("spectating", [True, False])
def test_b003_recorder_saves_laps_of_own_car_only(monkeypatch, spectating):
    from neopedal.api_control import api
    from neopedal.module import module_recorder
    from tests.telemetry_sim import LapSim, fake_reader

    monkeypatch.setattr(realtime_state, "active", True)
    monkeypatch.setattr(realtime_state, "spectating", spectating)
    monkeypatch.setattr(api, "_api", type("Api", (), {"NAME": "Le Mans Ultimate"})())
    sim = LapSim([95.0, 90.0, 92.0])
    monkeypatch.setattr(api, "read", fake_reader(sim))
    saved = []
    gen = module_recorder.record_telemetry(
        filepath="", min_lap_fraction=0.9, max_saved_laps=10,
        saver=lambda pending, options, valid: saved.append(pending.lap_time))
    while not sim.finished:
        gen.send(0)
        sim.tick()
    assert saved == ([] if spectating else [90.0])


# --- B-007: session & stint bests of the car followed before never kept for the new one
def test_b007_followed_car_starts_without_former_car_bests(monkeypatch, tmp_path):
    from neopedal.const_common import MAX_SECONDS

    _, after = run_delta(monkeypatch, tmp_path, switch_at=130.0, spectate=True, seconds=135.0)  # A: 2 laps of 60 s
    seconds, session_best, stint_best = after[-1]
    assert seconds > 4.0
    assert session_best == stint_best == MAX_SECONDS  # car B: no lap completed since followed


# --- B-005: Rest API garage values of the local car never given for a car followed (spectate)
@pytest.mark.parametrize("game", ["lmu", "rf2"])
@pytest.mark.parametrize("own_car", [True, False])
def test_b005_rest_values_of_own_car_only(game, own_car):
    from importlib import import_module
    from types import SimpleNamespace

    reader = import_module(f"neopedal.adapter.{game}_reader")
    rest = SimpleNamespace(
        repairTime=42.0, pitStopTime=55.0, absoluteRefill=80.0, maxVirtualEnergy=9e8, expectedFuelConsumption=3.1,
        expectedEnergyConsumption=0.05, steeringWheelRange=540.0, lastCarSetup=("x",), setupName="Qatar",
        setupModified=True)
    car = SimpleNamespace(mIsPlayer=own_car, mPhysicalSteeringWheelRange=0.0)
    rows = {f"{game}ScorVeh": lambda index=None: car, f"{game}TeleVeh": lambda index=None: car}
    shmm = SimpleNamespace(playerIndex=5, **rows)  # spectate: player index points at the car followed
    vehicle, engine, inputs = (getattr(reader, name)(shmm, rest) for name in ("Vehicle", "Engine", "Inputs"))
    values = (vehicle.repair_time(), vehicle.pit_stop_time(), vehicle.absolute_refill(), vehicle.setup(),
              vehicle.setup_name(), vehicle.setup_modified(), engine.expected_fuel_consumption(),
              engine.expected_energy_consumption(), inputs.steering_range_physical())
    if own_car:
        assert values == (42.0, 55.0, 80.0, ("x",), "Qatar", True, 3.1, pytest.approx(5.0), 540.0)
    else:
        assert values == (0.0, 0.0, 0.0, (), "", False, 0.0, 0.0, 0.0)
    if game == "lmu":
        assert engine.max_virtual_energy() == (9e8 if own_car else 0.0)


# --- B-004: player row gone (array compacted): the car moved to its index never served as the player
def test_b004_car_moved_to_player_index_never_served_as_player(lmu_game, monkeypatch):
    sync, data = lmu_game
    seen = []

    def next_sample():
        data.scoring.scoringInfo.mCurrentET += 0.2

    def player_leaves():  # player (slot 3, index 0) leaves: cars 5 & 7 move up one index
        scoring, telemetry = data.scoring.vehScoringInfo, data.telemetry.telemInfo
        for index, slot_id in enumerate((5, 7)):
            scoring[index].mID = telemetry[index].mID = slot_id
            scoring[index].mDriverName = b"Driver %d" % slot_id
            scoring[index].mIsPlayer = False
            telemetry[index].mFuel = float(slot_id)
        data.scoring.scoringInfo.mNumVehicles = data.telemetry.activeVehicles = 2
        next_sample()

    def record():
        seen.append((sync.synced, sync.player_scor.mDriverName, sync.player_tele.mFuel, sync.resets))

    steps = [next_sample, next_sample, lambda: None, record, player_leaves, record, next_sample, record]
    run_loop(sync, Ticks(monkeypatch, steps))
    before, *after = seen
    assert before[:3] == (True, b"Driver 3", 3.0)
    for synced, name, fuel, resets in after:
        assert name != b"Driver 5" and fuel != 5.0  # never the car now at the player's index
        assert not synced and resets == before[3]  # no false reset counted either


# --- B-006: finished car moved to the index of a car that left measures its own gaps
def test_b006_finished_car_never_keeps_gaps_of_car_that_left(field, monkeypatch):  # noqa: F811
    import ctypes

    from neopedal.api_control import api
    from neopedal.module import module_vehicles

    monkeypatch.setattr(module_vehicles, "_index_slot_ids", {})
    monkeypatch.setattr(module_vehicles, "_point_times", {})
    data = api._api._shmmapi._shmm.data
    scoring, telemetry = data.scoring.vehScoringInfo, data.telemetry.telemInfo
    for index in range(4):
        scoring[index].mFinishStatus = 1  # race over: gaps frozen at the line
    module_vehicles.update_vehicle_data(field, 1.0, 1.0, True, 600.0, True)
    module_vehicles.update_vehicle_data(field, 1.0, 1.0, True, 601.0, True)
    kept = field.dataSet[2].gapBehindLeader, field.dataSet[2].gapBehindNext
    # Car of index 2 leaves, the game moves car of index 3 up to index 2
    ctypes.memmove(ctypes.addressof(scoring[2]), ctypes.addressof(scoring[3]), ctypes.sizeof(scoring[3]))
    ctypes.memmove(ctypes.addressof(telemetry[2]), ctypes.addressof(telemetry[3]), ctypes.sizeof(telemetry[3]))
    data.scoring.scoringInfo.mNumVehicles = data.telemetry.activeVehicles = 3
    data.scoring.scoringInfo.mCurrentET = 602.0
    api._api._shmmapi._sync._update_indexes()
    module_vehicles.update_vehicle_data(field, 1.0, 1.0, True, 602.0, True, veh_total=3)
    moved = field.dataSet[2]
    assert moved.gapsFrozen  # its own gaps, frozen now
    assert (moved.gapBehindLeader, moved.gapBehindNext) != kept


# --- B-009: resume after a game pause keeps session timing of every car (recorded session)
def play_vehicles(monkeypatch, frames: int, pause_at: int | None) -> list:
    """Vehicles module on recorded session frames, game paused (connector frozen) on frame pause_at"""
    from neopedal.api_control import api
    from neopedal.module import module_vehicles
    from neopedal.module_info import VehiclesInfo, minfo
    from neopedal.setting import cfg
    from tests.recorded_session import RecordedSession, lockstep_modules

    monkeypatch.setattr(minfo, "vehicles", VehiclesInfo())
    monkeypatch.setattr(module_vehicles, "_index_slot_ids", {})
    monkeypatch.setattr(module_vehicles, "_point_times", {})
    session = RecordedSession("lmu_lusail_practice_pit", dict(cfg.api))
    monkeypatch.setattr(api, "_api", session.connector)
    monkeypatch.setattr(api, "read", session.reader)
    try:
        with lockstep_modules(monkeypatch, ["module_vehicles"], cfg) as lockstep:
            for index in range(frames):
                def load(index=index):
                    session.load(index)
                    if index == pause_at:
                        realtime_state.paused = True  # connector frozen (game paused), resumes next frame
                lockstep.step(load)
            lockstep.finish()
            output = minfo.vehicles
            return [(tuple(data.sectors.best), data.classBestSectors, data.sectors.last_kind)
                    for data in output.dataSet[:output.totalVehicles]]
    finally:
        session.close()


def test_b009_resume_after_pause_keeps_sector_bests(ui_env, monkeypatch):
    for name in ("active", "paused", "resets", "shown", "session_type", "in_pits"):
        monkeypatch.setattr(realtime_state, name, getattr(realtime_state, name))
    realtime_state.active = realtime_state.paused = realtime_state.shown = False
    assert play_vehicles(monkeypatch, 436, 430) == play_vehicles(monkeypatch, 436, None)


# --- B-008: session.start() is the event start time of day, never subtracted from the session elapsed time
@pytest.fixture
def race_session(monkeypatch):
    """Race read as recorded in LMU: start() 43200 (12:00, seconds since midnight), 287 s into a 3 h session"""
    from types import SimpleNamespace

    from neopedal.api_control import api

    session = SimpleNamespace(
        session_type=lambda: 4, finish_type=lambda: 0, in_race=lambda: True, start=lambda: 43200.0,
        elapsed=lambda: 287.0, end=lambda: 10800.0, track_time=lambda: 43487.0, time_scale=lambda: 1.0)
    monkeypatch.setattr(api, "read", SimpleNamespace(session=session))
    return session


def test_b008_race_length_and_start_time_of_live_race(race_session):
    from neopedal import race_live_data
    from neopedal.ui.quick import race_model

    assert race_live_data.race_length() == ("minutes", 180)
    assert race_model.live_race_length() == ("minutes", 180)
    assert race_live_data.start_minutes_now() == 12 * 60  # race started at 12:00, not "now"


# --- B-010 & B-011: back to game from a replay (or another replay): replay results & Rest API values forgotten
@pytest.mark.parametrize("api_name", ["SimLMU", "SimRF2"])
def test_b010_b011_replay_data_forgotten_on_source_change(monkeypatch, api_name):
    from neopedal import api_connector
    from neopedal.adapter import lmu_connector, restapi_connector, rf2_connector

    class Player:  # replay player stand-in (weak references allowed, as ReplayPlayer)
        pass

    source = {"player": None}
    cls = getattr(api_connector, api_name)
    monkeypatch.setattr(cls, "replay_player", lambda self: source["player"])
    for info in (lmu_connector.LMUInfo, rf2_connector.RF2Info):
        for name in ("setReplay", "start"):
            monkeypatch.setattr(info, name, lambda self, *args: None)
    monkeypatch.setattr(restapi_connector.RestAPIConnector, "start", lambda self: None)
    sim = cls()
    rest = sim._restapi_dataset
    results = getattr(sim._shmmapi._sync, "results", None)

    def play_replay():  # values applied from the replay file
        rest.setupName = "Replay setup"
        rest.aeroDamage = 0.3
        if results is not None:
            results.data[b"Test Driver"] = {"contact_vehicle": 6}
            results.timestamp = 100.0

    source["player"] = replay_a = Player()
    sim.start()
    play_replay()
    sim.start()  # same replay restarted (preset reload): kept
    assert rest.setupName == "Replay setup"
    source["player"] = None  # back to game
    sim.start()
    assert rest.setupName == "" and rest.aeroDamage == type(rest)().aeroDamage
    if results is not None:
        assert not results.data and results.timestamp == 0
    rest.setupName = "Game setup"
    sim.start()  # game restarted: kept
    assert rest.setupName == "Game setup"
    source["player"] = Player()  # another replay
    play_replay()
    del replay_a
    sim.start()
    assert rest.setupName == ""


# --- B-012: no player synced (spectating without override): modules notified at telemetry rate
@pytest.mark.parametrize("synced", [True, False])
def test_b012_modules_notified_on_new_telemetry_without_player(lmu_game, monkeypatch, synced):
    sync, data = lmu_game
    if not synced:
        data.scoring.vehScoringInfo[0].mIsPlayer = False  # no player car in session
    notified = []
    from neopedal.adapter.data_notify import DataNotifier

    monkeypatch.setattr(DataNotifier, "notify", lambda self: notified.append(1))

    def next_scoring():
        data.scoring.scoringInfo.mCurrentET += 0.2

    def next_telemetry():  # telemetry 50 Hz, scoring 5 Hz
        for row in data.telemetry.telemInfo[:3]:
            row.mElapsedTime += 0.02

    def mark():
        notified.append("mark")

    steps = [next_scoring, next_scoring, lambda: None, mark] + [next_telemetry] * 8 + [mark]
    run_loop(sync, Ticks(monkeypatch, steps))
    first, last = notified.index("mark"), len(notified) - 1
    assert last - first - 1 >= 8  # once per telemetry sample, whether a player is synced or not
