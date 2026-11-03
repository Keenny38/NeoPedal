"""
LMU Memory Map Control

Inherit Python mapping of LMU Shared Memory Interface
"""

from __future__ import annotations

import ctypes
import gc
import logging
import mmap
import platform
import time
from collections.abc import Callable
from typing import Any

try:
    from . import lmu_data
    from .lmu_data import LMUConstants
except ImportError:  # standalone, not package
    import lmu_data
    from lmu_data import LMUConstants

PLATFORM = platform.system()
MAX_VEHICLES = LMUConstants.MAX_MAPPED_VEHICLES
LOCK_SIZE = 8  # waiters & busy of the lock of the game, 2 LONG
LOCK_BUSY_OFFSET = 4
LOCK_RETRY_SECONDS = 1.0  # lock of the game looked for again (game started after the app) at most this often
# Lock busy longer than this: game stopped while writing (crashed), lock let go: copied without it, and its memory
# never kept alive by the app (a game started again makes a fresh lock), looked for again after LOCK_STUCK_RETRY
LOCK_STUCK_SECONDS = 0.5
LOCK_STUCK_RETRY = 30.0
# Data unchanged this long (game paused, in menus, closed or crashed, maybe while writing: busy flag left set): lock
# let go, so its section never outlives the game because of the app (else a game started again finds it, skips its
# reset and waits on the busy flag left set), opened again once data changes
LOCK_IDLE_SECONDS = 2.0
INVALID_INDEX = -1


def get_root_logger_name():
    """Get root logger name"""
    for logger_name in logging.root.manager.loggerDict:
        return logger_name
    return __name__


logger = logging.getLogger(get_root_logger_name())


def no_update() -> None:
    """Update placeholder while mmap is not created (None: unknown whether data changed)"""


def close_mmap(mmap_buffer: mmap.mmap, name: str) -> bool:
    """Close mmap, once more after a garbage collection if a ctypes view of it is only kept alive by a
    reference cycle (direct access), returns True if closed"""
    for collected in (False, True):
        try:
            mmap_buffer.close()
            logger.info("sharedmemory: CLOSED: %s", name)
            return True
        except BufferError:  # exported buffer (struct from_buffer) still referenced
            if not collected:
                gc.collect()
    logger.error("sharedmemory: buffer error while closing %s", name)
    return False


def platform_mmap(name: str, size: int) -> mmap.mmap:
    """Platform memory mapping"""
    if PLATFORM == "Windows":
        return windows_mmap(name, size)
    return linux_mmap(name, size)


def windows_mmap(name: str, size: int) -> mmap.mmap:
    """Windows mmap"""
    return mmap.mmap(-1, size, name)


def open_mapping(name: str) -> tuple[Any, int]:
    """(kernel32, handle) of named shared memory made already (Windows), handle 0 if none, never made here:
    a section the game makes itself must keep the game's rights (made by the app, an app run as administrator
    could leave the game unable to write it)"""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenFileMappingW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.OpenFileMappingW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32, kernel32.OpenFileMappingW(0x0004, False, name) or 0  # FILE_MAP_READ


def mapping_exists(name: str) -> bool:
    """Named shared memory made already (Windows), see open_mapping"""
    if PLATFORM != "Windows":
        return False
    kernel32, handle = open_mapping(name)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def open_game_lock(name: str) -> mmap.mmap | None:
    """Lock of the game opened read only (game writing while its busy flag is set), None if the game has none
    (not started, older build, Linux)

    Its section stays open (handle) while mapped: a game closing meanwhile never lets mmap make a new read only
    section of that name, which the game started again could not map for writing. Never written by the app (read
    only view), and let go once data stays unchanged (see LOCK_IDLE_SECONDS).
    """
    if PLATFORM != "Windows":
        return None
    kernel32, handle = open_mapping(name)
    if not handle:
        return None
    try:
        return mmap.mmap(-1, LOCK_SIZE, name, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        return None
    finally:
        kernel32.CloseHandle(handle)


def lock_busy(lock: mmap.mmap) -> bool:
    """Game writing its shared memory now (busy flag of its lock set)"""
    return lock[LOCK_BUSY_OFFSET:LOCK_BUSY_OFFSET + 4] != b"\x00\x00\x00\x00"


def linux_mmap(name: str, size: int) -> mmap.mmap:
    """Linux mmap - read data from '/dev/shm/filename' if available"""
    file = open("/dev/shm/" + name, "a+b")
    if file.tell() == 0:
        file.write(b"\0" * size)
        file.flush()
    return mmap.mmap(file.fileno(), size)


class MMapControl:
    """Memory map control"""

    __slots__ = (
        "_mmap_name",
        "_mmap_buffer",
        "_struct",
        "_buffer",
        "_realtime",
        "_heads",
        "_lock_name",
        "_lock",
        "_lock_retry",
        "_busy_since",
        "_idle_since",
        "_scratch",
        "update",
        "data",
    )

    def __init__(self, mmap_name: str, data_struct: type[Any],
                 lock_name: str = LMUConstants.LMU_SHARED_MEMORY_LOCK_FILE) -> None:
        """Initialize memory map setting

        Args:
            mmap_name: mmap filename.
            data_struct: ctypes data structure, ex. lmu_data.SharedMemoryEvent.
            lock_name: lock the game holds while writing (copy access waits for it), empty: none.
        """
        self._mmap_name = mmap_name
        self._lock_name = lock_name
        self._lock: mmap.mmap | None = None
        self._lock_retry = 0.0  # time.monotonic() lock of the game looked for again
        self._busy_since = 0.0  # time.monotonic() lock of the game seen busy first, 0: free
        self._idle_since = 0.0  # time.monotonic() data first seen unchanged while lock mapped, 0: changed
        self._scratch = bytearray()  # copy taken while game lock free, kept once still free after it
        self._mmap_buffer = None
        self._struct = data_struct
        self._buffer = bytearray()
        self._realtime = None
        # Copy access: (live scoring info, copied scoring info, live first telemetry, copied first telemetry)
        self._heads: tuple | None = None
        # Returns True if data copy updated, False if not (no new data), None if unknown (direct access)
        self.update: Callable[[], bool | None] = no_update
        self.data: Any = None

    def __del__(self):
        logger.info("sharedmemory: GC: MMap %s", self._mmap_name)

    def create(self, access_mode: int = 0) -> None:
        """Create mmap instance & initial accessible copy

        Args:
            access_mode: 0 = copy access, 1 = direct access.
        """
        self._mmap_buffer = platform_mmap(
            name=self._mmap_name,
            size=ctypes.sizeof(self._struct),
        )

        if access_mode:
            self.data = self._struct.from_buffer(self._mmap_buffer)
            self.update = self.__buffer_share
        else:
            self._buffer[:] = self._mmap_buffer
            self._realtime = self._struct.from_buffer(self._mmap_buffer)
            self.data = self._struct.from_buffer(self._buffer)
            self._heads = None  # made by first update
            self.update = self.__buffer_copy

        mode = "Direct" if access_mode else "Copy"
        logger.info("sharedmemory: ACTIVE: %s (%s Access)", self._mmap_name, mode)

    def close(self) -> None:
        """Close memory mapping

        Create a final accessible mmap data copy before closing mmap instance.
        """
        self.data = self._struct.from_buffer_copy(self._mmap_buffer)
        self._realtime = None
        self._heads = None
        if self._lock is not None:
            self._lock.close()
            self._lock = None
        self._busy_since = self._idle_since = 0.0
        self._scratch = bytearray()
        close_mmap(self._mmap_buffer, self._mmap_name)
        self.update = no_update  # unassign update method (for proper garbage collection)

    def __buffer_share(self) -> None:
        """Share buffer access, may result data desync (data always live, None: unknown whether changed)"""

    def __buffer_copy(self) -> bool:
        """Copy buffer access, helps avoid data desync

        Returns:
            True if data copy updated, False if not copied or same data (copy unchanged).
        """
        # Copy once data changed, with scoring & telemetry vehicle counts matching (generic events are a queue
        # of event values, see LMUEvent: never flags of the game updating data)
        if (
            self._realtime.scoring.scoringInfo.mNumVehicles
            == self._realtime.telemetry.activeVehicles
        ) and self.__changed():
            self._idle_since = 0.0
            if self.__game_lock() is None:
                self._buffer[:] = self._mmap_buffer
                return True
            # Copied while the game does not write (its lock free before & after the copy, and no write done
            # within the copy: sample times of scoring & first telemetry entry unchanged meanwhile): never data
            # of two game ticks mixed, else copied at the next update
            if self.__game_writing():
                return False
            live_scor, _, live_tele, _ = self._heads  # made by __changed
            scor_time, tele_time = live_scor.mCurrentET, live_tele.mElapsedTime
            self._scratch[:] = self._mmap_buffer
            if (self.__game_writing() or live_scor.mCurrentET != scor_time
                    or live_tele.mElapsedTime != tele_time):
                return False
            self._buffer[:] = self._scratch
            return True
        if self._lock is not None:
            self.__release_idle_lock(self._lock)
        return False

    def __release_idle_lock(self, lock: mmap.mmap) -> None:
        """Lock of the game let go once data stayed unchanged for LOCK_IDLE_SECONDS (checked on every update, even
        with a busy flag left set by a game stopped while writing), looked for again at the next data change"""
        now = time.monotonic()
        if not self._idle_since:
            self._idle_since = now
            return
        if now - self._idle_since < LOCK_IDLE_SECONDS:
            return
        logger.info("sharedmemory: lock of %s let go (data unchanged %.1f s)", self._mmap_name,
                    now - self._idle_since)
        lock.close()
        self._lock = None
        self._busy_since = self._idle_since = 0.0
        self._lock_retry = 0.0

    def __game_writing(self) -> bool:
        """Game holding its lock now (False if no lock, or lock let go: held too long, see LOCK_STUCK_SECONDS)"""
        lock = self._lock
        if lock is None:
            return False
        if not lock_busy(lock):
            self._busy_since = 0.0
            return False
        now = time.monotonic()
        if not self._busy_since:
            self._busy_since = now
            return True
        if now - self._busy_since < LOCK_STUCK_SECONDS:
            return True
        logger.warning("sharedmemory: lock of %s held %.1f s (game stopped while writing?): copied without it",
                       self._mmap_name, now - self._busy_since)
        lock.close()
        self._lock = None
        self._busy_since = 0.0
        self._lock_retry = now + LOCK_STUCK_RETRY
        return False

    def __game_lock(self) -> mmap.mmap | None:
        """Lock of the game, looked for again now and then while missing (game started after the app)"""
        if self._lock is None and self._lock_name:
            now = time.monotonic()
            if now >= self._lock_retry:
                self._lock_retry = now + LOCK_RETRY_SECONDS
                self._lock = open_game_lock(self._lock_name)
        return self._lock

    def __changed(self) -> bool:
        """Whether shared memory differs from data copy

        Sample times of scoring & first telemetry entry are compared first: while the game runs they change
        nearly every tick, so the full compare (whole structure, same cost as the copy) only runs on same
        times (paused game, menus), where it mostly finds equal data and saves the copy.
        """
        heads = self._heads
        if heads is None:  # wrappers of live & copied structures, made once (ctypes allocates one per access)
            heads = self._heads = (
                self._realtime.scoring.scoringInfo, self.data.scoring.scoringInfo,
                self._realtime.telemetry.telemInfo[0], self.data.telemetry.telemInfo[0],
            )
        live_scor, copy_scor, live_tele, copy_tele = heads
        return (
            live_scor.mCurrentET != copy_scor.mCurrentET
            or live_tele.mElapsedTime != copy_tele.mElapsedTime
            or self._buffer != self._mmap_buffer
        )


def test_api():
    """API test run"""
    # Add logger
    test_handler = logging.StreamHandler()
    logger.setLevel(logging.INFO)
    logger.addHandler(test_handler)

    # Test run
    SEPARATOR = "=" * 50
    print("Test API - Direct Access")
    info = MMapControl(LMUConstants.LMU_SHARED_MEMORY_FILE, lmu_data.LMUObjectOut)
    info.create(1)
    info.update()

    print(SEPARATOR)
    print("Test API - Close")
    info.close()

    print(SEPARATOR)
    print("Test API - Copy Access")
    info.create(0)
    info.update()

    print(SEPARATOR)
    print("Test API - Read")
    version = info.data.generic.gameVersion
    track = info.data.scoring.scoringInfo.mTrackName.decode()
    vehicle = info.data.telemetry.telemInfo[0].mVehicleName.decode()
    total = info.data.scoring.scoringInfo.mNumVehicles
    print(f"version: {version if version else 'not running'}")
    print(f"track name: {track if version else 'not running'}")
    print(f"vehicle name: {vehicle if version else 'not running'}")
    print(f"total cars: {total if version else 'not running'}")

    print(SEPARATOR)
    info.close()


if __name__ == "__main__":
    test_api()
