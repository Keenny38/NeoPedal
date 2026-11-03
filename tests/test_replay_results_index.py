"""Results stream index of a replay (LMU) built from the start of each frame only: same index as from whole
decoded frames, a fraction of the work while playback decodes frames (seek cost doubled while indexing)"""

import json
import struct
import time
import zlib

from neopedal import replay as replay_module
from neopedal.replay import (
    FRAME_HEADER_V1,
    KEYFRAME_INTERVAL,
    MAGIC_V1,
    ReplayFile,
    ReplayWriter,
)

FRAME_SIZE = 8192
ELAPSED = 16  # offset of session elapsed time (double)
STREAM = 64  # offset of results stream
STREAM_SIZE = 512
FRAMES = 3 * KEYFRAME_INTERVAL + 37
SESSION_START = 2 * KEYFRAME_INTERVAL + 11  # elapsed time goes back: next session


def make_frames() -> list[bytes]:
    frames = []
    for index in range(FRAMES):
        frame = bytearray(FRAME_SIZE)
        elapsed = (index if index < SESSION_START else index - SESSION_START) * 0.1
        struct.pack_into("<d", frame, ELAPSED, elapsed)
        if index % 9 < 6:  # stream empty on some frames, same stream on following frames
            stream = b'<Incident et="%d">Driver(%d) reported contact</Incident>' % (index // 3, index // 3)
            frame[STREAM:STREAM + len(stream)] = stream
        frame[-64:] = bytes((index * 7 + offset) % 256 for offset in range(64))  # telemetry: changes every frame
        frames.append(bytes(frame))
    return frames


def write_replay(path, frames: list[bytes], damaged: tuple[int, ...] = ()) -> str:
    filename = str(path / "results.tpreplay")
    with open(filename, "wb") as file:
        writer = ReplayWriter(file, FRAME_SIZE, 10)
        for index, frame in enumerate(frames):
            writer.write(index * 0.1, frame)
        writer.finish()
    replay = ReplayFile(filename)
    offsets = [replay._heads[index] + replay._frame_header.size for index in damaged]
    replay.close()
    with open(filename, "r+b") as file:  # flip a payload byte: CRC fails
        for offset in offsets:
            file.seek(offset)
            byte = file.read(1)
            file.seek(offset)
            file.write(bytes((byte[0] ^ 0xFF,)))
    return filename


def expected_index(frames: list[bytes], damaged: tuple[int, ...] = ()) -> tuple[list, list, list]:
    """Index from whole frames, frames played after damage skipped until next keyframe"""
    indexes, streams, starts = [], [], [0]
    last_stream, last_elapsed, broken = b"", float("-inf"), False
    for index, frame in enumerate(frames):
        if index % KEYFRAME_INTERVAL == 0:
            broken = False
        if index in damaged:
            broken = True
        if broken:
            continue
        elapsed = struct.unpack_from("<d", frame, ELAPSED)[0]
        if elapsed < last_elapsed - 0.001:
            starts.append(index)
            last_stream = b""
        last_elapsed = elapsed
        stream = frame[STREAM:STREAM + STREAM_SIZE].split(b"\0", 1)[0]
        if stream != last_stream:
            last_stream = stream
            if stream:
                indexes.append(index)
                streams.append(stream)
    return indexes, streams, starts


def built_index(replay: ReplayFile) -> tuple[list, list, list]:
    stream = replay.results_index(ELAPSED, STREAM, STREAM_SIZE)
    deadline = time.monotonic() + 30.0
    while not stream.ready:
        assert time.monotonic() < deadline, "results index not built"
        time.sleep(0.005)
    return list(stream._indexes), list(stream._streams), list(stream._starts)


def spy_work(monkeypatch, replay: ReplayFile) -> dict:
    """Whole frame decodes & largest XOR of index thread"""
    work = {"decodes": 0, "xor": 0}
    decode, xor = replay._decode, replay_module.xor_bytes

    def spy_decode(*args):
        work["decodes"] += 1
        return decode(*args)

    def spy_xor(data, base):
        work["xor"] = max(work["xor"], len(data))
        return xor(data, base)

    monkeypatch.setattr(replay, "_decode", spy_decode)
    monkeypatch.setattr(replay_module, "xor_bytes", spy_xor)
    return work


def test_results_index_decodes_only_elapsed_time_and_stream(tmp_path, monkeypatch):
    frames = make_frames()
    replay = ReplayFile(write_replay(tmp_path, frames))
    work = spy_work(monkeypatch, replay)
    try:
        assert built_index(replay) == expected_index(frames)
    finally:
        replay.close()
    assert work["decodes"] == 0  # no whole frame decoded (playback decodes frames meanwhile)
    assert 0 < work["xor"] <= STREAM_SIZE  # only elapsed time & stream XORed with previous frame


def test_results_index_skips_damaged_frames_until_keyframe(tmp_path, monkeypatch):
    frames = make_frames()
    damaged = (5, KEYFRAME_INTERVAL, SESSION_START + 2)  # delta frame, keyframe, delta frame of next session
    replay = ReplayFile(write_replay(tmp_path, frames, damaged))
    try:
        assert built_index(replay) == expected_index(frames, damaged)
        assert replay.frame(6) == frames[4]  # playback holds last good frame, as indexed
    finally:
        replay.close()


def test_results_index_same_as_whole_frame_decode(tmp_path, monkeypatch):
    frames = make_frames()
    damaged = (KEYFRAME_INTERVAL + 3,)
    filename = write_replay(tmp_path, frames, damaged)
    replay = ReplayFile(filename)
    try:
        partial = built_index(replay)
    finally:
        replay.close()
    replay = ReplayFile(filename)
    replay._frame_header = struct.Struct(replay_module.FRAME_HEADER.format)  # same header, not format 2: whole frames
    work = spy_work(monkeypatch, replay)
    try:
        assert built_index(replay) == partial
    finally:
        replay.close()
    assert work["decodes"] > 0


def test_format_1_results_index_decodes_whole_frames(tmp_path, monkeypatch):
    frames = make_frames()
    filename = str(tmp_path / "old.tpreplay")
    with open(filename, "wb") as file:  # format 1: no CRC, every frame a keyframe
        file.write(MAGIC_V1 + json.dumps({"frame_size": FRAME_SIZE, "rate": 10}).encode() + b"\n")
        for index, frame in enumerate(frames):
            payload = zlib.compress(frame)
            file.write(FRAME_HEADER_V1.pack(index * 0.1, 1, len(payload)) + payload)
    replay = ReplayFile(filename)
    work = spy_work(monkeypatch, replay)
    try:
        assert built_index(replay) == expected_index(frames)
    finally:
        replay.close()
    assert work["decodes"] == len(frames)
