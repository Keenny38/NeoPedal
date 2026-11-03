"""Bug audit 2026-11-02, game data acquisition: B-019 & B-020, fixes of the LMU game lock (lmu_mmap.py, uncommitted
work of another session): committed with that work (audit_bugs_donnees_jeu_2026-11-02.md)
"""

import pytest

from pyLMUSharedMemory import lmu_data


# --- B-019: LMU copy with the game lock: a game write done within the copy (lock free before & after) refused
def test_b019_copy_refused_when_game_wrote_within_it(monkeypatch):
    import mmap

    from pyLMUSharedMemory import lmu_mmap

    monkeypatch.setattr(lmu_mmap, "platform_mmap", lambda name, size: mmap.mmap(-1, size))
    control = lmu_mmap.MMapControl("test", lmu_data.LMUObjectOut, lock_name="")
    control.create(0)
    live = lmu_data.LMUObjectOut.from_buffer(control._mmap_buffer)
    live.generic.events.SME_UPDATE_TELEMETRY = 1
    checks = []

    def busy(lock) -> bool:  # lock of game always free when checked
        checks.append(1)
        if len(checks) == 2:  # game wrote a whole tick during the copy, between the two checks
            live.scoring.scoringInfo.mCurrentET = 2.0
            live.telemetry.telemInfo[0].mElapsedTime = 2.0
        return False

    monkeypatch.setattr(lmu_mmap, "lock_busy", busy)
    control._lock = object()  # game lock found
    live.scoring.scoringInfo.mCurrentET = live.telemetry.telemInfo[0].mElapsedTime = 1.0
    try:
        assert control.update() is False  # copy may mix two game ticks: refused, copied next update
        assert control.data.scoring.scoringInfo.mCurrentET == 0.0
        assert control.update() is True and control.data.scoring.scoringInfo.mCurrentET == 2.0
    finally:
        control._lock = None
        live = None  # view of the mapping released before close
        control.close()


# --- B-020: game lock opened while its section is kept open: never a read only section made by the app
@pytest.mark.skipif(__import__("sys").platform != "win32", reason="named shared memory sections: Windows")
def test_b020_game_lock_never_made_read_only_by_app(monkeypatch):
    import mmap
    import os

    from pyLMUSharedMemory import lmu_mmap

    name = f"NeoPedalTestLock{os.getpid()}"
    game = mmap.mmap(-1, 8, name)  # lock section of the running game
    real_mmap = mmap.mmap

    def game_exits_first(*args, **kwargs):  # game closed between the check and the open
        game.close()
        return real_mmap(*args, **kwargs)

    monkeypatch.setattr(mmap, "mmap", game_exits_first)
    lock = lmu_mmap.open_game_lock(name)
    monkeypatch.setattr(mmap, "mmap", real_mmap)
    try:
        again = mmap.mmap(-1, 8, name)  # game started again: maps its lock for writing
        again.close()
    finally:
        if lock is not None:
            lock.close()
