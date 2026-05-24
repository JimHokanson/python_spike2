# -*- coding: utf-8 -*-
"""
Created on Fri May 22 22:23:28 2026

@author: Jim

ctypes implementation

NOT USING

"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple, Union

import numpy as np

# ---------------------------------------------------------------------------
# Import the compiled extension
# ---------------------------------------------------------------------------
from _ceds64_cffi import ffi, lib


# ---------------------------------------------------------------------------
# Constants / enums
# ---------------------------------------------------------------------------

class ChanType(IntEnum):
    """Channel type codes returned by :func:`chan_type`."""
    OFF = 0
    ADC = 1
    EVENT_FALL = 2
    EVENT_RISE = 3
    EVENT_BOTH = 4
    MARKER = 5
    ADC_MARK = 6
    REAL_MARK = 7
    TEXT_MARK = 8
    REAL_WAVE = 9


# ---------------------------------------------------------------------------
# Python-side marker data classes
# ---------------------------------------------------------------------------

@dataclass
class CEDMarker:
    """A basic marker: 64-bit timestamp plus four 8-bit codes."""
    time: int = 0
    code1: int = 0
    code2: int = 0
    code3: int = 0
    code4: int = 0

    @property
    def codes(self) -> Tuple[int, int, int, int]:
        return (self.code1, self.code2, self.code3, self.code4)

    def _to_c(self):
        """Return a cffi S64Marker cdata object."""
        m = ffi.new("S64Marker *")
        m.m_Time = self.time
        m.m_Code1 = self.code1
        m.m_Code2 = self.code2
        m.m_Code3 = self.code3
        m.m_Code4 = self.code4
        return m

    @classmethod
    def _from_c(cls, m) -> "CEDMarker":
        return cls(
            time=m.m_Time,
            code1=m.m_Code1,
            code2=m.m_Code2,
            code3=m.m_Code3,
            code4=m.m_Code4,
        )


@dataclass
class CEDTextMark(CEDMarker):
    """A marker with attached text data."""
    data: str = ""


@dataclass
class CEDRealMark(CEDMarker):
    """A marker with attached float32 data (rows × cols)."""
    data: np.ndarray = field(
        default_factory=lambda: np.empty((0, 0), dtype=np.float32)
    )


@dataclass
class CEDWaveMark(CEDMarker):
    """A marker with attached int16 waveform data (rows × cols)."""
    data: np.ndarray = field(
        default_factory=lambda: np.empty((0, 0), dtype=np.int16)
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_string(getter_fn, *id_args) -> str:
    """
    Two-pass string read used by file_comment, chan_title, chan_comment,
    chan_units.  First call with nGetSize=-1 to get length, then allocate
    and call again with nGetSize=0.
    """
    dummy = ffi.new("char[2]")
    size = getter_fn(*id_args, dummy, -1)
    if size < 0:
        return ""
    buf = ffi.new(f"char[{size + 1}]")
    getter_fn(*id_args, buf, 0)
    return ffi.string(buf).decode(errors="replace")


def _np_from_buf(buf, dtype, count):
    """Zero-copy (where possible) numpy array from a cffi buffer."""
    if count <= 0:
        return np.empty(0, dtype=dtype)
    return np.frombuffer(ffi.buffer(buf, count * np.dtype(dtype).itemsize),
                         dtype=dtype).copy()


# ===================================================================
# Public API
# ===================================================================

# ── File management ───────────────────────────────────────────────

def file_count() -> int:
    """Return the number of currently open SON files."""
    return lib.S64FileCount()


def close_all() -> int:
    """Close all open SON files. Returns 0 on success."""
    return lib.S64CloseAll()


def create(filename: str, n_chans: int = 32, file_type: int = -1) -> int:
    """
    Create a new empty SON file.

    Parameters
    ----------
    filename : path to the new .smr or .smrx file.
    n_chans  : maximum channel count (min 32).
    file_type: 0=old 32-bit .smr, 1=big 32-bit .smr, 2=64-bit .smrx,
               -1=infer from extension.

    Returns a positive file handle or a negative error code.
    """
    return lib.S64Create(filename.encode(), n_chans, file_type)


def open(filename: str, mode: int = 1) -> int:
    """
    Open an existing SON file.

    mode: 1=read-only, 0=read/write, -1=try r/w then r/o.
    Returns a positive file handle or a negative error code.
    """
    return lib.S64Open(filename.encode(), mode)


def is_open(fhand: int) -> int:
    """1 if the handle is in use, 0 if not, -1 if invalid."""
    return lib.S64IsOpen(fhand)


def close(fhand: int) -> int:
    """Close a file. Returns 0 on success."""
    return lib.S64Close(fhand)


def empty_file(fhand: int) -> int:
    """Clear all data but keep channel definitions."""
    return lib.S64Empty(fhand)


# ── File properties ───────────────────────────────────────────────

def time_base(fhand: int, new_tb: Optional[float] = None) -> float:
    """Get (and optionally set) seconds per tick."""
    tb = lib.S64GetTimeBase(fhand)
    if new_tb is not None and tb > 0:
        lib.S64SetTimeBase(fhand, new_tb)
    return tb


def max_time(fhand: int) -> int:
    """Maximum time (ticks) across all channels."""
    return lib.S64MaxTime(fhand)


def max_channels(fhand: int) -> int:
    """Maximum number of channels the file can hold."""
    return lib.S64MaxChans(fhand)


def file_size(fhand: int) -> int:
    """Estimated file size in bytes."""
    return lib.S64FileSize(fhand)


def version(fhand: int) -> int:
    """File format version (major*256 + minor)."""
    return lib.S64GetVersion(fhand)


def secs_to_ticks(fhand: int, seconds: float) -> int:
    """Convert seconds → file ticks."""
    return lib.S64SecsToTicks(fhand, seconds)


def ticks_to_secs(fhand: int, ticks: int) -> float:
    """Convert file ticks → seconds."""
    return lib.S64TicksToSecs(fhand, ticks)


def get_free_chan(fhand: int) -> int:
    """Lowest unused channel number."""
    return lib.S64GetFreeChan(fhand)


def file_comment(fhand: int, index: int,
                 new_comment: Optional[str] = None) -> str:
    """Get (and optionally set) file comment *index* (1-5)."""
    old = _get_string(lib.S64GetFileComment, fhand, index)
    if new_comment is not None:
        lib.S64SetFileComment(fhand, index, new_comment.encode())
    return old


def time_date(fhand: int) -> Tuple[int, ...]:
    """
    Creation time/date stored in the file.

    Returns (hundredths, seconds, minutes, hours, day, month, year).
    """
    buf_get = ffi.new("long long[8]")
    buf_set = ffi.new("long long[8]")
    lib.S64TimeDate(fhand, buf_get, buf_set, -1)
    return tuple(buf_get[i] for i in range(7))


def app_id(fhand: int) -> Tuple[int, ...]:
    """Application ID stored in the file (tuple of 4 ints)."""
    buf_get = ffi.new("int[4]")
    buf_set = ffi.new("int[4]")
    lib.S64AppID(fhand, buf_get, buf_set, -1)
    return tuple(buf_get[i] for i in range(4))


# ── Channel properties ────────────────────────────────────────────

def chan_type(fhand: int, chan: int) -> ChanType:
    """Channel type as a :class:`ChanType` enum."""
    val = lib.S64ChanType(fhand, chan)
    try:
        return ChanType(val)
    except ValueError:
        return val


def chan_divide(fhand: int, chan: int) -> int:
    """Sample interval in file ticks."""
    return lib.S64ChanDivide(fhand, chan)


def ideal_rate(fhand: int, chan: int,
               new_rate: Optional[float] = None) -> float:
    """Get (and optionally set) the ideal sample/event rate (Hz)."""
    rate = lib.S64GetIdealRate(fhand, chan)
    if new_rate is not None:
        lib.S64SetIdealRate(fhand, chan, new_rate)
    return rate


def chan_title(fhand: int, chan: int,
              new_title: Optional[str] = None) -> str:
    """Get (and optionally set) channel title."""
    old = _get_string(lib.S64GetChanTitle, fhand, chan)
    if new_title is not None:
        lib.S64SetChanTitle(fhand, chan, new_title.encode())
    return old


def chan_comment(fhand: int, chan: int,
                new_comment: Optional[str] = None) -> str:
    """Get (and optionally set) channel comment."""
    old = _get_string(lib.S64GetChanComment, fhand, chan)
    if new_comment is not None:
        lib.S64SetChanComment(fhand, chan, new_comment.encode())
    return old


def chan_units(fhand: int, chan: int,
              new_units: Optional[str] = None) -> str:
    """Get (and optionally set) channel units string."""
    old = _get_string(lib.S64GetChanUnits, fhand, chan)
    if new_units is not None:
        lib.S64SetChanUnits(fhand, chan, new_units.encode())
    return old


def chan_scale(fhand: int, chan: int,
              new_scale: Optional[float] = None) -> float:
    """Get (and optionally set) channel scale."""
    val = ffi.new("double *")
    lib.S64GetChanScale(fhand, chan, val)
    if new_scale is not None:
        lib.S64SetChanScale(fhand, chan, new_scale)
    return val[0]


def chan_offset(fhand: int, chan: int,
               new_offset: Optional[float] = None) -> float:
    """Get (and optionally set) channel offset."""
    val = ffi.new("double *")
    lib.S64GetChanOffset(fhand, chan, val)
    if new_offset is not None:
        lib.S64SetChanOffset(fhand, chan, new_offset)
    return val[0]


def chan_max_time(fhand: int, chan: int) -> int:
    """Time (ticks) of the last item in the channel."""
    return lib.S64ChanMaxTime(fhand, chan)


def chan_y_range(fhand: int, chan: int,
                new_low: Optional[float] = None,
                new_high: Optional[float] = None) -> Tuple[float, float]:
    """Get (and optionally set) Y-axis display range."""
    lo = ffi.new("double *")
    hi = ffi.new("double *")
    lib.S64GetChanYRange(fhand, chan, lo, hi)
    if new_low is not None and new_high is not None:
        lib.S64SetChanYRange(fhand, chan, new_low, new_high)
    return lo[0], hi[0]


def chan_delete(fhand: int, chan: int) -> int:
    """Delete a channel."""
    return lib.S64ChanDelete(fhand, chan)


def chan_undelete(fhand: int, chan: int) -> int:
    """Attempt to undelete a channel."""
    return lib.S64ChanUndelete(fhand, chan)


def get_ext_mark_info(fhand: int, chan: int) -> Tuple[int, int, int]:
    """Return (pre_alignment_points, rows, cols) for extended markers."""
    rows = ffi.new("int *")
    cols = ffi.new("int *")
    pre = lib.S64GetExtMarkInfo(fhand, chan, rows, cols)
    return pre, rows[0], cols[0]


def prev_n_time(fhand: int, chan: int, t_from: int, t_to: int,
                n: int = 1, mask: int = -1, as_wave: int = 0) -> int:
    """Time of N items before *t_from*."""
    return lib.S64PrevNTime(fhand, chan, t_from, t_to, n, mask, as_wave)


# ── Channel creation ──────────────────────────────────────────────

def set_wave_chan(fhand: int, chan: int, t_div: int,
                 chan_type_code: int = 1, rate: float = 0.0) -> int:
    """Create a waveform channel. 1=Adc (int16), 9=RealWave (float32)."""
    return lib.S64SetWaveChan(fhand, chan, t_div, chan_type_code, rate)


def set_event_chan(fhand: int, chan: int, rate: float,
                  event_type: int = 3) -> int:
    """Create an event channel. 2=Fall, 3=Rise, 4=Both."""
    return lib.S64SetEventChan(fhand, chan, rate, event_type)


def set_marker_chan(fhand: int, chan: int, rate: float,
                   kind: int = 5) -> int:
    """Create a marker channel. 5=Marker, 4=Level."""
    return lib.S64SetMarkerChan(fhand, chan, rate, kind)


def set_level_chan(fhand: int, chan: int, rate: float) -> int:
    """Create an EventBoth (level) channel."""
    return lib.S64SetLevelChan(fhand, chan, rate)


def set_init_level(fhand: int, chan: int, level: int) -> int:
    """Set initial level of an EventBoth channel (0=low)."""
    return lib.S64SetInitLevel(fhand, chan, level)


def set_text_mark_chan(fhand: int, chan: int, rate: float,
                      max_chars: int) -> int:
    """Create a TextMark channel."""
    return lib.S64SetTextMarkChan(fhand, chan, rate, max_chars)


def set_ext_mark_chan(fhand: int, chan: int, rate: float,
                     ext_type: int = 1, rows: int = 1,
                     cols: int = 1, t_div: int = 0) -> int:
    """
    Create an extended marker channel.
    ext_type: 1=AdcMark, 2=RealMark, 3=TextMark.
    """
    return lib.S64SetExtMarkChan(fhand, chan, rate, ext_type,
                                 rows, cols, t_div)


# ── Waveform read / write ─────────────────────────────────────────

def write_wave(fhand: int, chan: int,
               data: np.ndarray, t_from: int) -> int:
    """
    Write waveform data.  Accepts int16 or float32 numpy arrays.
    Returns next write time or a negative error code.
    """
    n = len(data)
    if data.dtype == np.int16:
        buf = ffi.from_buffer("short[]", data)
        return lib.S64WriteWaveS(fhand, chan, buf, n, t_from)
    else:
        data = np.ascontiguousarray(data, dtype=np.float32)
        buf = ffi.from_buffer("float[]", data)
        return lib.S64WriteWaveF(fhand, chan, buf, n, t_from)


def read_wave_f(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1, mask: int = -1,
                ) -> Tuple[int, np.ndarray, int]:
    """
    Read waveform data as float32.

    Returns (n_read, float32_array, first_time_ticks).
    """
    buf = ffi.new(f"float[{n_max}]")
    t_first = ffi.new("long long *")
    n_read = lib.S64ReadWaveF(fhand, chan, buf, n_max,
                              t_from, t_to, t_first, mask)
    arr = _np_from_buf(buf, np.float32, n_read)
    return n_read, arr, t_first[0]


def read_wave_s(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1, mask: int = -1,
                ) -> Tuple[int, np.ndarray, int]:
    """
    Read waveform data as int16.

    Returns (n_read, int16_array, first_time_ticks).
    """
    buf = ffi.new(f"short[{n_max}]")
    t_first = ffi.new("long long *")
    n_read = lib.S64ReadWaveS(fhand, chan, buf, n_max,
                              t_from, t_to, t_first, mask)
    arr = _np_from_buf(buf, np.int16, n_read)
    return n_read, arr, t_first[0]


# ── Event read / write ────────────────────────────────────────────

def write_events(fhand: int, chan: int, times: np.ndarray) -> int:
    """Write event times (int64, in ticks). Returns 0 on success."""
    times = np.ascontiguousarray(times, dtype=np.int64)
    buf = ffi.from_buffer("long long[]", times)
    return lib.S64WriteEvents(fhand, chan, buf, len(times))


def read_events(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1, mask: int = -1,
                ) -> Tuple[int, np.ndarray]:
    """
    Read event times.

    Returns (n_read, int64_array).
    """
    buf = ffi.new(f"long long[{n_max}]")
    n_read = lib.S64ReadEvents(fhand, chan, buf, n_max,
                               t_from, t_to, mask)
    arr = _np_from_buf(buf, np.int64, n_read)
    return n_read, arr


# ── Level (EventBoth) read / write ────────────────────────────────

def write_levels(fhand: int, chan: int, times: np.ndarray) -> int:
    """Write level-toggle times to an EventBoth channel."""
    times = np.ascontiguousarray(times, dtype=np.int64)
    buf = ffi.from_buffer("long long[]", times)
    return lib.S64WriteLevels(fhand, chan, buf, len(times))


def read_levels(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1) -> Tuple[int, np.ndarray, int]:
    """
    Read level data.

    Returns (n_read, int64_times, initial_level).
    """
    buf = ffi.new(f"long long[{n_max}]")
    level = ffi.new("int *")
    n_read = lib.S64ReadLevels(fhand, chan, buf, n_max,
                               t_from, t_to, level)
    arr = _np_from_buf(buf, np.int64, n_read)
    return n_read, arr, level[0]


# ── Marker read / write ──────────────────────────────────────────

def write_markers(fhand: int, chan: int,
                  markers: List[CEDMarker]) -> int:
    """Write a list of :class:`CEDMarker` to a marker channel."""
    n = len(markers)
    buf = ffi.new(f"S64Marker[{n}]")
    for i, mk in enumerate(markers):
        buf[i].m_Time = mk.time
        buf[i].m_Code1 = mk.code1
        buf[i].m_Code2 = mk.code2
        buf[i].m_Code3 = mk.code3
        buf[i].m_Code4 = mk.code4
    return lib.S64WriteMarkers(fhand, chan, buf, n)


def read_markers(fhand: int, chan: int, n_max: int, t_from: int,
                 t_to: int = -1, mask: int = -1,
                 ) -> Tuple[int, List[CEDMarker]]:
    """Read markers. Returns (n_read, list_of_CEDMarker)."""
    buf = ffi.new(f"S64Marker[{n_max}]")
    n_read = lib.S64ReadMarkers(fhand, chan, buf, n_max,
                                t_from, t_to, mask)
    if n_read > 0:
        return n_read, [CEDMarker._from_c(buf[i]) for i in range(n_read)]
    return n_read, []


def edit_marker(fhand: int, chan: int, time: int,
                marker: CEDMarker) -> int:
    """Replace the codes of an existing marker at *time*."""
    m = marker._to_c()
    return lib.S64EditMarker(fhand, chan, time, m)


# ── Extended marker read / write ──────────────────────────────────

def write_ext_marks(
    fhand: int, chan: int,
    markers: List[Union[CEDTextMark, CEDRealMark, CEDWaveMark]],
) -> int:
    """Write extended markers one at a time."""
    ct = lib.S64ChanType(fhand, chan)

    for mk in markers:
        cm = mk._to_c()

        if ct == ChanType.TEXT_MARK:
            raw = mk.data.encode() if isinstance(mk.data, str) else mk.data
            ret = lib.S64Write1TextMark(fhand, chan, cm, raw, len(raw))

        elif ct == ChanType.REAL_MARK:
            d = np.ascontiguousarray(mk.data, dtype=np.float32).ravel()
            buf = ffi.from_buffer("float[]", d)
            ret = lib.S64Write1RealMark(fhand, chan, cm, buf, len(d))

        elif ct == ChanType.ADC_MARK:
            d = np.ascontiguousarray(mk.data, dtype=np.int16).ravel()
            buf = ffi.from_buffer("short[]", d)
            ret = lib.S64Write1WaveMark(fhand, chan, cm, buf, len(d))
        else:
            return -1

        if ret < 0:
            return ret

    return 0


def read_ext_marks(
    fhand: int, chan: int, n_max: int, t_from: int,
    t_to: int = -1, mask: int = -1,
) -> Tuple[int, List[Union[CEDTextMark, CEDRealMark, CEDWaveMark]]]:
    """
    Read extended markers from a TextMark, RealMark, or WaveMark channel.

    Returns (n_read, list_of_extended_markers).
    """
    ct = lib.S64ChanType(fhand, chan)
    pre, rows, cols = get_ext_mark_info(fhand, chan)

    if t_to < 0:
        t_upto = -1
        t_end = max_time(fhand) + 1
    else:
        t_upto = t_to
        t_end = t_to

    cursor = t_from
    results: list = []
    cm = ffi.new("S64Marker *")

    for _ in range(n_max):
        if cursor >= t_end > 0:
            break

        if ct == ChanType.TEXT_MARK:
            text_buf = ffi.new(f"char[{rows + 8}]")
            n = lib.S64Read1TextMark(fhand, chan, cm, text_buf,
                                     cursor, t_upto, mask)
            if n <= 0:
                break
            mk = CEDTextMark(
                time=cm.m_Time,
                code1=cm.m_Code1, code2=cm.m_Code2,
                code3=cm.m_Code3, code4=cm.m_Code4,
                data=ffi.string(text_buf).decode(errors="replace"),
            )

        elif ct == ChanType.REAL_MARK:
            n_reals = rows * cols
            fbuf = ffi.new(f"float[{n_reals}]")
            n = lib.S64Read1RealMark(fhand, chan, cm, fbuf,
                                     cursor, t_upto, mask)
            if n <= 0:
                break
            arr = _np_from_buf(fbuf, np.float32, n_reals).reshape(rows, cols)
            mk = CEDRealMark(
                time=cm.m_Time,
                code1=cm.m_Code1, code2=cm.m_Code2,
                code3=cm.m_Code3, code4=cm.m_Code4,
                data=arr,
            )

        elif ct == ChanType.ADC_MARK:
            n_shorts = rows * cols
            sbuf = ffi.new(f"short[{n_shorts}]")
            n = lib.S64Read1WaveMark(fhand, chan, cm, sbuf,
                                     cursor, t_upto, mask)
            if n <= 0:
                break
            arr = (_np_from_buf(sbuf, np.int16, n_shorts)
                   .reshape(cols, rows).T.copy())
            mk = CEDWaveMark(
                time=cm.m_Time,
                code1=cm.m_Code1, code2=cm.m_Code2,
                code3=cm.m_Code3, code4=cm.m_Code4,
                data=arr,
            )
        else:
            break

        results.append(mk)
        cursor = cm.m_Time + 1

    return len(results), results


# ── Marker masks ──────────────────────────────────────────────────

def mask_reset(mask_handle: Optional[int] = None) -> int:
    """Reset one mask, or all masks if *mask_handle* is ``None``."""
    if mask_handle is None:
        return lib.S64ResetAllMasks()
    return lib.S64ResetMask(mask_handle)


def mask_mode(mask_handle: int,
              new_mode: Optional[int] = None) -> int:
    """Get (and optionally set) mask mode. 0=AND, 1=OR."""
    prev = lib.S64GetMaskMode(mask_handle)
    if new_mode is not None:
        lib.S64SetMaskMode(mask_handle, new_mode)
    return prev


def mask_col(mask_handle: int,
             new_col: Optional[int] = None) -> int:
    """Get (and optionally set) mask column select."""
    prev = lib.S64GetMaskCol(mask_handle)
    if new_col is not None:
        lib.S64SetMaskCol(mask_handle, new_col)
    return prev


def mask_codes(mask_handle: int,
               new_codes: Optional[np.ndarray] = None) -> np.ndarray:
    """Get (and optionally set) the 256×4 mask code matrix."""
    out_codes = ffi.new("int[1024]")
    out_mode = ffi.new("int *")
    lib.S64GetMaskCodes(mask_handle, out_codes, out_mode)
    arr = _np_from_buf(out_codes, np.int32, 1024).reshape(256, 4)
    if new_codes is not None:
        flat = np.ascontiguousarray(new_codes, dtype=np.int32).ravel()
        in_buf = ffi.new("int[1024]")
        for i in range(min(len(flat), 1024)):
            in_buf[i] = flat[i]
        lib.S64SetMaskCodes(mask_handle, in_buf)
    return arr


# ── Extra data ────────────────────────────────────────────────────

def extra_data(fhand: int, n_bytes: int, offset: int,
               data_in: Optional[bytes] = None) -> bytes:
    """Get (and optionally set) raw extra header data."""
    buf = ffi.new(f"unsigned char[{n_bytes}]")
    lib.S64GetExtraData(fhand, buf, n_bytes, offset)
    out = bytes(ffi.buffer(buf, n_bytes))
    if data_in is not None:
        in_buf = ffi.from_buffer("unsigned char[]",
                                 bytearray(data_in))
        lib.S64SetExtraData(fhand, in_buf, len(data_in), offset)
    return out