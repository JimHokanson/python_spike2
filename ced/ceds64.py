"""
CEDS64 - Python ctypes wrapper for the CED SON64 library (ceds64int.dll).

A Python port of the CEDS64ML MATLAB interface originally provided by
Cambridge Electronic Design (CED). This module wraps the native
ceds64int.dll to read and write CED Spike2 .smr/.smrx files.

Original MATLAB code: Copyright (C) Cambridge Electronic Design Limited 2014
Python port: based on the GPL-3.0 licensed CEDS64ML interface.

Requirements:
    - Windows (the DLL is Windows-only)
    - The ceds64int.dll and son64.dll files from CED's CEDS64ML distribution
      must be accessible (placed next to this file or on the system PATH).

License: GPL-3.0 (same as the original CEDS64ML)
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import platform
import sys
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char,
    c_char_p,
    c_double,
    c_float,
    c_int,
    c_longlong,
    c_short,
    c_ubyte,
    c_uint,
    create_string_buffer,
)
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILES = 100
MAX_FILTERS = 1000


class ChanType(IntEnum):
    """Channel type codes returned by chan_type()."""
    OFF = 0
    ADC = 1          # Waveform (16-bit integer)
    EVENT_FALL = 2
    EVENT_RISE = 3
    EVENT_BOTH = 4
    MARKER = 5
    ADC_MARK = 6     # WaveMark
    REAL_MARK = 7
    TEXT_MARK = 8
    REAL_WAVE = 9    # Waveform (32-bit float)


# ---------------------------------------------------------------------------
# C Structure matching the DLL's S64Marker
# ---------------------------------------------------------------------------

class _S64Marker(Structure):
    """C-level marker structure matching the DLL's S64Marker typedef."""
    _fields_ = [
        ("m_Time", c_longlong),
        ("m_Code1", c_ubyte),
        ("m_Code2", c_ubyte),
        ("m_Code3", c_ubyte),
        ("m_Code4", c_ubyte),
    ]
    # Pad to 16 bytes total (8 time + 4 codes + 4 pad)
    _pack_ = 1


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

    def _to_c(self) -> _S64Marker:
        m = _S64Marker()
        m.m_Time = self.time
        m.m_Code1 = self.code1
        m.m_Code2 = self.code2
        m.m_Code3 = self.code3
        m.m_Code4 = self.code4
        return m

    @classmethod
    def _from_c(cls, m: _S64Marker) -> "CEDMarker":
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
    """A marker with attached float data (rows x cols)."""
    data: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=np.float32))


@dataclass
class CEDWaveMark(CEDMarker):
    """A marker with attached int16 waveform data (rows x cols)."""
    data: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=np.int16))


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

class CEDS64Error(Exception):
    """Raised when a DLL function returns a negative error code."""
    def __init__(self, code: int, message: str = ""):
        self.code = code
        super().__init__(f"CEDS64 error {code}: {message}" if message else f"CEDS64 error code {code}")


# ---------------------------------------------------------------------------
# Library loader
# ---------------------------------------------------------------------------

_lib: Optional[ctypes.CDLL] = None


def load_lib(path: Optional[str] = None) -> ctypes.CDLL:
    """
    Load the ceds64int DLL.

    Parameters
    ----------
    path : str, optional
        Directory containing ceds64int.dll (and son64.dll).  If *None* the
        directory of this Python file is searched, then the system PATH.

    Returns
    -------
    ctypes.CDLL
        The loaded library handle.
    """
    global _lib
    if _lib is not None:
        return _lib

    if path is None:
        path = str(Path(__file__).parent)
        #dll_dir = path
        
        
    
    arch = platform.architecture()[0]
    if arch == "64bit":
        subdir = "x64"
    else:
        subdir = "x86"

    dll_dir = os.path.join(path, subdir)
    
    if os.path.isdir(dll_dir):
        # Add DLL directory to search path (Python 3.8+)
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(dll_dir)
        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        dll_path = os.path.join(dll_dir, "ceds64int.dll")
    else:
        dll_path = os.path.join(path, "ceds64int.dll")

    _lib = ctypes.CDLL(dll_path)
    _setup_prototypes(_lib)
    return _lib


def _setup_prototypes(lib: ctypes.CDLL) -> None:
    """Declare return types and argument types for all DLL functions."""
    # fmt: off
    _decl = {
        # Basic file functions
        "S64FileCount":      (c_int, []),
        "S64CloseAll":       (c_int, []),
        "S64Create":         (c_int, [c_char_p, c_int, c_int]),
        "S64Open":           (c_int, [c_char_p, c_int]),
        "S64IsOpen":         (c_int, [c_int]),
        "S64Close":          (c_int, [c_int]),
        "S64Empty":          (c_int, [c_int]),

        # File properties
        "S64GetFileComment": (c_int, [c_int, c_int, c_char_p, c_int]),
        "S64SetFileComment": (c_int, [c_int, c_int, c_char_p]),
        "S64GetFreeChan":    (c_int, [c_int]),
        "S64MaxChans":       (c_int, [c_int]),
        "S64GetTimeBase":    (c_double, [c_int]),
        "S64SetTimeBase":    (c_int, [c_int, c_double]),
        "S64SecsToTicks":    (c_longlong, [c_int, c_double]),
        "S64TicksToSecs":    (c_double, [c_int, c_longlong]),
        "S64GetVersion":     (c_int, [c_int]),
        "S64FileSize":       (c_longlong, [c_int]),
        "S64MaxTime":        (c_longlong, [c_int]),
        "S64TimeDate":       (c_int, [c_int, POINTER(c_longlong), POINTER(c_longlong), c_int]),
        "S64AppID":          (c_int, [c_int, POINTER(c_int), POINTER(c_int), c_int]),

        "S64GetExtraData":   (c_int, [c_int, ctypes.c_void_p, c_uint, c_uint]),
        "S64SetExtraData":   (c_int, [c_int, ctypes.c_void_p, c_uint, c_uint]),

        # Channel properties
        "S64ChanType":       (c_int, [c_int, c_int]),
        "S64ChanDivide":     (c_longlong, [c_int, c_int]),
        "S64GetIdealRate":   (c_double, [c_int, c_int]),
        "S64SetIdealRate":   (c_double, [c_int, c_int, c_double]),
        "S64GetChanComment": (c_int, [c_int, c_int, c_char_p, c_int]),
        "S64SetChanComment": (c_int, [c_int, c_int, c_char_p]),
        "S64GetChanTitle":   (c_int, [c_int, c_int, c_char_p, c_int]),
        "S64SetChanTitle":   (c_int, [c_int, c_int, c_char_p]),
        "S64GetChanScale":   (c_int, [c_int, c_int, POINTER(c_double)]),
        "S64SetChanScale":   (c_int, [c_int, c_int, c_double]),
        "S64GetChanOffset":  (c_int, [c_int, c_int, POINTER(c_double)]),
        "S64SetChanOffset":  (c_int, [c_int, c_int, c_double]),
        "S64GetChanUnits":   (c_int, [c_int, c_int, c_char_p, c_int]),
        "S64SetChanUnits":   (c_int, [c_int, c_int, c_char_p]),
        "S64ChanMaxTime":    (c_longlong, [c_int, c_int]),
        "S64ChanDelete":     (c_int, [c_int, c_int]),
        "S64ChanUndelete":   (c_int, [c_int, c_int]),
        "S64GetChanYRange":  (c_int, [c_int, c_int, POINTER(c_double), POINTER(c_double)]),
        "S64SetChanYRange":  (c_int, [c_int, c_int, c_double, c_double]),
        "S64ItemSize":       (c_int, [c_int, c_int]),
        "S64PrevNTime":      (c_longlong, [c_int, c_int, c_longlong, c_longlong, c_int, c_int, c_int]),

        # Channel setup
        "S64SetEventChan":   (c_int, [c_int, c_int, c_double, c_int]),
        "S64SetWaveChan":    (c_int, [c_int, c_int, c_longlong, c_int, c_double]),
        "S64SetMarkerChan":  (c_int, [c_int, c_int, c_double, c_int]),
        "S64SetLevelChan":   (c_int, [c_int, c_int, c_double]),
        "S64SetInitLevel":   (c_int, [c_int, c_int, c_int]),
        "S64SetTextMarkChan":(c_int, [c_int, c_int, c_double, c_int]),
        "S64SetExtMarkChan": (c_int, [c_int, c_int, c_double, c_int, c_int, c_int, c_longlong]),
        "S64GetExtMarkInfo": (c_int, [c_int, c_int, POINTER(c_int), POINTER(c_int)]),

        # Event read/write
        "S64WriteEvents":    (c_int, [c_int, c_int, POINTER(c_longlong), c_int]),
        "S64ReadEvents":     (c_int, [c_int, c_int, POINTER(c_longlong), c_int, c_longlong, c_longlong, c_int]),

        # Marker read/write
        "S64WriteMarkers":   (c_int, [c_int, c_int, POINTER(_S64Marker), c_int]),
        "S64ReadMarkers":    (c_int, [c_int, c_int, POINTER(_S64Marker), c_int, c_longlong, c_longlong, c_int]),
        "S64EditMarker":     (c_int, [c_int, c_int, c_longlong, POINTER(_S64Marker)]),

        # Level read/write
        "S64WriteLevels":    (c_int, [c_int, c_int, POINTER(c_longlong), c_int]),
        "S64ReadLevels":     (c_int, [c_int, c_int, POINTER(c_longlong), c_int, c_longlong, c_longlong, POINTER(c_int)]),

        # Extended marker read/write
        "S64Write1TextMark": (c_int, [c_int, c_int, POINTER(_S64Marker), c_char_p, c_int]),
        "S64Write1RealMark": (c_int, [c_int, c_int, POINTER(_S64Marker), POINTER(c_float), c_int]),
        "S64Write1WaveMark": (c_int, [c_int, c_int, POINTER(_S64Marker), POINTER(c_short), c_int]),
        "S64Read1TextMark":  (c_int, [c_int, c_int, POINTER(_S64Marker), c_char_p, c_longlong, c_longlong, c_int]),
        "S64Read1RealMark":  (c_int, [c_int, c_int, POINTER(_S64Marker), POINTER(c_float), c_longlong, c_longlong, c_int]),
        "S64Read1WaveMark":  (c_int, [c_int, c_int, POINTER(_S64Marker), POINTER(c_short), c_longlong, c_longlong, c_int]),

        # Waveform read/write
        "S64WriteWaveS":     (c_longlong, [c_int, c_int, POINTER(c_short), c_int, c_longlong]),
        "S64WriteWaveF":     (c_longlong, [c_int, c_int, POINTER(c_float), c_int, c_longlong]),
        "S64WriteWave64":    (c_longlong, [c_int, c_int, POINTER(c_double), c_int, c_longlong]),
        "S64ReadWaveS":      (c_int, [c_int, c_int, POINTER(c_short), c_int, c_longlong, c_longlong, POINTER(c_longlong), c_int]),
        "S64ReadWaveF":      (c_int, [c_int, c_int, POINTER(c_float), c_int, c_longlong, c_longlong, POINTER(c_longlong), c_int]),
        "S64ReadWave64":     (c_int, [c_int, c_int, POINTER(c_double), c_int, c_longlong, c_longlong, POINTER(c_longlong), c_int]),

        # Marker masks
        "S64GetMaskCodes":   (c_int, [c_int, POINTER(c_int), POINTER(c_int)]),
        "S64SetMaskCodes":   (c_int, [c_int, POINTER(c_int)]),
        "S64SetMaskMode":    (c_int, [c_int, c_int]),
        "S64GetMaskMode":    (c_int, [c_int]),
        "S64SetMaskCol":     (c_int, [c_int, c_int]),
        "S64GetMaskCol":     (c_int, [c_int]),
        "S64ResetMask":      (c_int, [c_int]),
        "S64ResetAllMasks":  (c_int, []),
    }
    # fmt: on

    for name, (restype, argtypes) in _decl.items():
        fn = getattr(lib, name, None)
        if fn is not None:
            fn.restype = restype
            fn.argtypes = argtypes


def _get_lib() -> ctypes.CDLL:
    if _lib is None:
        raise RuntimeError(
            "Library not loaded. Call ceds64.load_lib(path) first, "
            "passing the path to your CEDS64ML directory."
        )
    return _lib


# ---------------------------------------------------------------------------
# Public API — each function mirrors the original MATLAB wrapper
# ---------------------------------------------------------------------------

# ── File management ──────────────────────────────────────────────────────

def file_count() -> int:
    """Return the number of currently open SON files."""
    return _get_lib().S64FileCount()


def close_all() -> int:
    """Close all open SON files. Returns 0 on success."""
    return _get_lib().S64CloseAll()


def create(filename: str, n_chans: int = 32, file_type: int = -1) -> int:
    """
    Create a new, empty SON file.

    Parameters
    ----------
    filename : str
        Path for the new file (.smr or .smrx).
    n_chans : int
        Maximum number of channels (minimum 32).
    file_type : int
        0 = old 32-bit .smr (2 GB limit), 1 = big 32-bit .smr (1 TB limit),
        2 = 64-bit .smrx. -1 = infer from extension.

    Returns
    -------
    int
        Positive file handle on success, negative error code on failure.
    """
    return _get_lib().S64Create(filename.encode(), n_chans, file_type)


def open(filename: str, mode: int = 1) -> int:
    """
    Open an existing SON file.

    Parameters
    ----------
    filename : str
        Path to the file.
    mode : int
        1 = read-only, 0 = read/write, -1 = try read/write then read-only.

    Returns
    -------
    int
        Positive file handle on success, negative error code on failure.
    """
    return _get_lib().S64Open(filename.encode(), mode)


def is_open(fhand: int) -> int:
    """Check if a file handle is assigned to an open file. 1=yes, 0=no."""
    return _get_lib().S64IsOpen(fhand)


def close(fhand: int) -> int:
    """Close an open SON file. Returns 0 on success."""
    return _get_lib().S64Close(fhand)


def empty_file(fhand: int) -> int:
    """Clear all data from a file while leaving channels intact."""
    return _get_lib().S64Empty(fhand)


# ── File properties ──────────────────────────────────────────────────────

def time_base(fhand: int, new_time_base: Optional[float] = None) -> float:
    """
    Get (and optionally set) the seconds-per-tick time base.

    Returns the current (or previous) time base value.
    """
    lib = _get_lib()
    tb = lib.S64GetTimeBase(fhand)
    if new_time_base is not None and tb > 0:
        lib.S64SetTimeBase(fhand, new_time_base)
    return tb


def max_time(fhand: int) -> int:
    """Return the maximum time (in ticks) across all channels."""
    return _get_lib().S64MaxTime(fhand)


def max_channels(fhand: int) -> int:
    """Return the maximum number of channels the file can hold."""
    return _get_lib().S64MaxChans(fhand)


def file_size(fhand: int) -> int:
    """Return the estimated file size in bytes."""
    return _get_lib().S64FileSize(fhand)


def version(fhand: int) -> int:
    """Return (major * 256 + minor) version of the file format."""
    return _get_lib().S64GetVersion(fhand)


def secs_to_ticks(fhand: int, seconds: float) -> int:
    """Convert seconds to file ticks."""
    return _get_lib().S64SecsToTicks(fhand, seconds)


def ticks_to_secs(fhand: int, ticks: int) -> float:
    """Convert file ticks to seconds."""
    return _get_lib().S64TicksToSecs(fhand, ticks)


def get_free_chan(fhand: int) -> int:
    """Return the lowest unused channel number."""
    return _get_lib().S64GetFreeChan(fhand)


def file_comment(fhand: int, index: int, new_comment: Optional[str] = None) -> str:
    """
    Get (and optionally set) a file comment (indices 1-5).

    Returns the current (or previous) comment string.
    """
    lib = _get_lib()
    # Query length
    dummy = create_string_buffer(2)
    size = lib.S64GetFileComment(fhand, index, dummy, -1)
    if size < 0:
        return ""
    buf = create_string_buffer(size + 1)
    lib.S64GetFileComment(fhand, index, buf, 0)
    old = buf.value.decode(errors="replace")
    if new_comment is not None:
        lib.S64SetFileComment(fhand, index, new_comment.encode())
    return old


def time_date(fhand: int) -> Tuple[int, ...]:
    """
    Get the creation time/date stored in the file.

    Returns a tuple of 7 int64 values:
    (hundredths, seconds, minutes, hours, day, month, year).
    """
    lib = _get_lib()
    buf_get = (c_longlong * 8)()
    buf_set = (c_longlong * 8)()
    lib.S64TimeDate(fhand, buf_get, buf_set, -1)
    return tuple(buf_get[i] for i in range(7))


def app_id(fhand: int) -> Tuple[int, ...]:
    """Get the application ID stored in the file. Returns a tuple of 4 ints."""
    lib = _get_lib()
    buf_get = (c_int * 4)()
    buf_set = (c_int * 4)()
    lib.S64AppID(fhand, buf_get, buf_set, -1)
    return tuple(buf_get[i] for i in range(4))


# ── Channel properties ───────────────────────────────────────────────────

def chan_type(fhand: int, chan: int) -> ChanType:
    """Return the type of a channel as a ChanType enum value."""
    val = _get_lib().S64ChanType(fhand, chan)
    try:
        return ChanType(val)
    except ValueError:
        return val  # negative error code


def chan_divide(fhand: int, chan: int) -> int:
    """Return the sample interval in file ticks for a channel."""
    return _get_lib().S64ChanDivide(fhand, chan)


def ideal_rate(fhand: int, chan: int, new_rate: Optional[float] = None) -> float:
    """Get (and optionally set) the ideal sample/event rate for a channel."""
    lib = _get_lib()
    rate = lib.S64GetIdealRate(fhand, chan)
    if new_rate is not None:
        lib.S64SetIdealRate(fhand, chan, new_rate)
    return rate


def chan_title(fhand: int, chan: int, new_title: Optional[str] = None) -> str:
    """Get (and optionally set) the title of a channel."""
    lib = _get_lib()
    dummy = create_string_buffer(2)
    size = lib.S64GetChanTitle(fhand, chan, dummy, -1)
    if size < 0:
        return ""
    buf = create_string_buffer(size + 1)
    lib.S64GetChanTitle(fhand, chan, buf, 0)
    old = buf.value.decode(errors="replace")
    if new_title is not None:
        lib.S64SetChanTitle(fhand, chan, new_title.encode())
    return old


def chan_comment(fhand: int, chan: int, new_comment: Optional[str] = None) -> str:
    """Get (and optionally set) the comment of a channel."""
    lib = _get_lib()
    dummy = create_string_buffer(2)
    size = lib.S64GetChanComment(fhand, chan, dummy, -1)
    if size < 0:
        return ""
    buf = create_string_buffer(size + 1)
    lib.S64GetChanComment(fhand, chan, buf, 0)
    old = buf.value.decode(errors="replace")
    if new_comment is not None:
        lib.S64SetChanComment(fhand, chan, new_comment.encode())
    return old


def chan_units(fhand: int, chan: int, new_units: Optional[str] = None) -> str:
    """Get (and optionally set) the units string of a channel."""
    lib = _get_lib()
    dummy = create_string_buffer(2)
    size = lib.S64GetChanUnits(fhand, chan, dummy, -1)
    if size < 0:
        return ""
    buf = create_string_buffer(size + 1)
    lib.S64GetChanUnits(fhand, chan, buf, 0)
    old = buf.value.decode(errors="replace")
    if new_units is not None:
        lib.S64SetChanUnits(fhand, chan, new_units.encode())
    return old


def chan_scale(fhand: int, chan: int, new_scale: Optional[float] = None) -> float:
    """Get (and optionally set) the scale for a channel."""
    lib = _get_lib()
    val = c_double(0.0)
    lib.S64GetChanScale(fhand, chan, byref(val))
    if new_scale is not None:
        lib.S64SetChanScale(fhand, chan, new_scale)
    return val.value


def chan_offset(fhand: int, chan: int, new_offset: Optional[float] = None) -> float:
    """Get (and optionally set) the offset for a channel."""
    lib = _get_lib()
    val = c_double(0.0)
    lib.S64GetChanOffset(fhand, chan, byref(val))
    if new_offset is not None:
        lib.S64SetChanOffset(fhand, chan, new_offset)
    return val.value


def chan_max_time(fhand: int, chan: int) -> int:
    """Return the time (in ticks) of the last item in a channel."""
    return _get_lib().S64ChanMaxTime(fhand, chan)


def chan_y_range(
    fhand: int, chan: int,
    new_low: Optional[float] = None, new_high: Optional[float] = None,
) -> Tuple[float, float]:
    """Get (and optionally set) the Y-axis display range for a channel."""
    lib = _get_lib()
    lo, hi = c_double(0.0), c_double(0.0)
    lib.S64GetChanYRange(fhand, chan, byref(lo), byref(hi))
    if new_low is not None and new_high is not None:
        lib.S64SetChanYRange(fhand, chan, new_low, new_high)
    return lo.value, hi.value


def chan_delete(fhand: int, chan: int) -> int:
    """Delete a channel. Returns 0 on success."""
    return _get_lib().S64ChanDelete(fhand, chan)


def chan_undelete(fhand: int, chan: int) -> int:
    """Attempt to undelete a channel. Returns 0 on success."""
    return _get_lib().S64ChanUndelete(fhand, chan)


def get_ext_mark_info(fhand: int, chan: int) -> Tuple[int, int, int]:
    """
    Get extended marker info: (pre_alignment_points, rows, cols).
    """
    lib = _get_lib()
    rows, cols = c_int(0), c_int(0)
    pre = lib.S64GetExtMarkInfo(fhand, chan, byref(rows), byref(cols))
    return pre, rows.value, cols.value


def prev_n_time(
    fhand: int, chan: int, t_from: int, t_to: int,
    n: int = 1, mask: int = -1, as_wave: int = 0,
) -> int:
    """Find the time of N items before a given time."""
    return _get_lib().S64PrevNTime(fhand, chan, t_from, t_to, n, mask, as_wave)


# ── Channel creation ─────────────────────────────────────────────────────

def set_wave_chan(
    fhand: int, chan: int, t_div: int,
    chan_type_code: int = 1, rate: float = 0.0,
) -> int:
    """
    Create a waveform channel. chan_type_code: 1=Adc (int16), 9=RealWave (float32).
    """
    return _get_lib().S64SetWaveChan(fhand, chan, t_div, chan_type_code, rate)


def set_event_chan(fhand: int, chan: int, rate: float, event_type: int = 3) -> int:
    """
    Create an event channel. event_type: 2=EventFall, 3=EventRise, 4=EventBoth.
    """
    return _get_lib().S64SetEventChan(fhand, chan, rate, event_type)


def set_marker_chan(fhand: int, chan: int, rate: float, kind: int = 5) -> int:
    """Create a marker channel. kind: 5=Marker, 4=Level (EventBoth)."""
    return _get_lib().S64SetMarkerChan(fhand, chan, rate, kind)


def set_level_chan(fhand: int, chan: int, rate: float) -> int:
    """Create an EventBoth (level) channel."""
    return _get_lib().S64SetLevelChan(fhand, chan, rate)


def set_init_level(fhand: int, chan: int, level: int) -> int:
    """Set the initial level (0=low, non-zero=high) of an EventBoth channel."""
    return _get_lib().S64SetInitLevel(fhand, chan, level)


def set_text_mark_chan(fhand: int, chan: int, rate: float, max_chars: int) -> int:
    """Create a TextMark channel. max_chars includes the null terminator."""
    return _get_lib().S64SetTextMarkChan(fhand, chan, rate, max_chars)


def set_ext_mark_chan(
    fhand: int, chan: int, rate: float,
    ext_type: int = 1, rows: int = 1, cols: int = 1, t_div: int = 0,
) -> int:
    """
    Create an extended marker channel.
    ext_type: 1=AdcMark (int16), 2=RealMark (float32), 3=TextMark (char).
    """
    return _get_lib().S64SetExtMarkChan(fhand, chan, rate, ext_type, rows, cols, t_div)


# ── Waveform read/write ──────────────────────────────────────────────────

def write_wave(
    fhand: int, chan: int, data: np.ndarray, t_from: int,
) -> int:
    """
    Write waveform data. Accepts int16 or float32 numpy arrays.

    Returns the next time to write to, or a negative error code.
    """
    lib = _get_lib()
    n = len(data)
    if data.dtype == np.int16:
        buf = data.ctypes.data_as(POINTER(c_short))
        return lib.S64WriteWaveS(fhand, chan, buf, n, t_from)
    else:
        data = np.asarray(data, dtype=np.float32)
        buf = data.ctypes.data_as(POINTER(c_float))
        return lib.S64WriteWaveF(fhand, chan, buf, n, t_from)


def read_wave_f(
    fhand: int, chan: int, n_max: int, t_from: int,
    t_to: int = -1, mask: int = -1,
) -> Tuple[int, np.ndarray, int]:
    """
    Read waveform data as float32.

    Returns (n_read, float_array, first_time_ticks).
    """
    lib = _get_lib()
    buf = (c_float * n_max)()
    t_first = c_longlong(0)
    n_read = lib.S64ReadWaveF(fhand, chan, buf, n_max, t_from, t_to, byref(t_first), mask)
    if n_read > 0:
        arr = np.ctypeslib.as_array(buf)[:n_read].copy()
    else:
        arr = np.empty(0, dtype=np.float32)
    return n_read, arr, t_first.value


def read_wave_s(
    fhand: int, chan: int, n_max: int, t_from: int,
    t_to: int = -1, mask: int = -1,
) -> Tuple[int, np.ndarray, int]:
    """
    Read waveform data as int16.

    Returns (n_read, int16_array, first_time_ticks).
    """
    lib = _get_lib()
    buf = (c_short * n_max)()
    t_first = c_longlong(0)
    n_read = lib.S64ReadWaveS(fhand, chan, buf, n_max, t_from, t_to, byref(t_first), mask)
    if n_read > 0:
        arr = np.ctypeslib.as_array(buf)[:n_read].copy()
    else:
        arr = np.empty(0, dtype=np.int16)
    return n_read, arr, t_first.value


# ── Event read/write ─────────────────────────────────────────────────────

def write_events(fhand: int, chan: int, times: np.ndarray) -> int:
    """Write event times (int64 array, in ticks). Returns 0 on success."""
    times = np.asarray(times, dtype=np.int64)
    buf = times.ctypes.data_as(POINTER(c_longlong))
    return _get_lib().S64WriteEvents(fhand, chan, buf, len(times))


def read_events(
    fhand: int, chan: int, n_max: int, t_from: int,
    t_to: int = -1, mask: int = -1,
) -> Tuple[int, np.ndarray]:
    """
    Read event times. Returns (n_read, int64_array_of_times).
    """
    buf = (c_longlong * n_max)()
    n_read = _get_lib().S64ReadEvents(fhand, chan, buf, n_max, t_from, t_to, mask)
    if n_read > 0:
        arr = np.ctypeslib.as_array(buf)[:n_read].copy()
    else:
        arr = np.empty(0, dtype=np.int64)
    return n_read, arr


# ── Level (EventBoth) read/write ─────────────────────────────────────────

def write_levels(fhand: int, chan: int, times: np.ndarray) -> int:
    """Write level-toggle times to an EventBoth channel."""
    times = np.asarray(times, dtype=np.int64)
    buf = times.ctypes.data_as(POINTER(c_longlong))
    return _get_lib().S64WriteLevels(fhand, chan, buf, len(times))


def read_levels(
    fhand: int, chan: int, n_max: int, t_from: int, t_to: int = -1,
) -> Tuple[int, np.ndarray, int]:
    """
    Read level data. Returns (n_read, int64_times, initial_level).
    initial_level is 1 if high, 0 if low.
    """
    buf = (c_longlong * n_max)()
    level = c_int(0)
    n_read = _get_lib().S64ReadLevels(fhand, chan, buf, n_max, t_from, t_to, byref(level))
    if n_read > 0:
        arr = np.ctypeslib.as_array(buf)[:n_read].copy()
    else:
        arr = np.empty(0, dtype=np.int64)
    return n_read, arr, level.value


# ── Marker read/write ────────────────────────────────────────────────────

def write_markers(fhand: int, chan: int, markers: List[CEDMarker]) -> int:
    """Write a list of CEDMarker objects to a marker channel."""
    n = len(markers)
    buf = (_S64Marker * n)()
    for i, mk in enumerate(markers):
        buf[i] = mk._to_c()
    return _get_lib().S64WriteMarkers(fhand, chan, buf, n)


def read_markers(
    fhand: int, chan: int, n_max: int, t_from: int,
    t_to: int = -1, mask: int = -1,
) -> Tuple[int, List[CEDMarker]]:
    """Read markers. Returns (n_read, list_of_CEDMarker)."""
    buf = (_S64Marker * n_max)()
    n_read = _get_lib().S64ReadMarkers(fhand, chan, buf, n_max, t_from, t_to, mask)
    if n_read > 0:
        return n_read, [CEDMarker._from_c(buf[i]) for i in range(n_read)]
    return n_read, []


def edit_marker(fhand: int, chan: int, time: int, marker: CEDMarker) -> int:
    """Replace the codes of an existing marker at the given time."""
    m = marker._to_c()
    return _get_lib().S64EditMarker(fhand, chan, time, byref(m))


# ── Extended marker read/write ───────────────────────────────────────────

def write_ext_marks(
    fhand: int, chan: int,
    markers: List[Union[CEDTextMark, CEDRealMark, CEDWaveMark]],
) -> int:
    """Write extended markers (TextMark, RealMark, or WaveMark) one at a time."""
    lib = _get_lib()
    ct = lib.S64ChanType(fhand, chan)
    for mk in markers:
        cm = mk._to_c()
        if ct == ChanType.TEXT_MARK:
            text = mk.data.encode() if isinstance(mk.data, str) else mk.data
            ret = lib.S64Write1TextMark(fhand, chan, byref(cm), text, len(text))
        elif ct == ChanType.REAL_MARK:
            d = np.asarray(mk.data, dtype=np.float32).ravel()
            buf = d.ctypes.data_as(POINTER(c_float))
            ret = lib.S64Write1RealMark(fhand, chan, byref(cm), buf, len(d))
        elif ct == ChanType.ADC_MARK:
            d = np.asarray(mk.data, dtype=np.int16).ravel()
            buf = d.ctypes.data_as(POINTER(c_short))
            ret = lib.S64Write1WaveMark(fhand, chan, byref(cm), buf, len(d))
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
    lib = _get_lib()
    ct = lib.S64ChanType(fhand, chan)
    pre, rows, cols = get_ext_mark_info(fhand, chan)

    if t_to < 0:
        t_upto = -1
        t_end = max_time(fhand) + 1
    else:
        t_upto = t_to
        t_end = t_to

    time_cursor = t_from
    results = []
    cm = _S64Marker()

    for _ in range(n_max):
        if time_cursor >= t_end and t_end > 0:
            break

        if ct == ChanType.TEXT_MARK:
            str_len = rows + 8
            text_buf = create_string_buffer(str_len)
            n_read = lib.S64Read1TextMark(fhand, chan, byref(cm), text_buf, time_cursor, t_upto, mask)
            if n_read > 0:
                mk = CEDTextMark(
                    time=cm.m_Time, code1=cm.m_Code1, code2=cm.m_Code2,
                    code3=cm.m_Code3, code4=cm.m_Code4,
                    data=text_buf.value.decode(errors="replace"),
                )
                results.append(mk)
                time_cursor = cm.m_Time + 1
            else:
                break

        elif ct == ChanType.REAL_MARK:
            n_reals = rows * cols
            fbuf = (c_float * n_reals)()
            n_read = lib.S64Read1RealMark(fhand, chan, byref(cm), fbuf, time_cursor, t_upto, mask)
            if n_read > 0:
                arr = np.ctypeslib.as_array(fbuf)[:n_reals].copy().reshape(rows, cols)
                mk = CEDRealMark(
                    time=cm.m_Time, code1=cm.m_Code1, code2=cm.m_Code2,
                    code3=cm.m_Code3, code4=cm.m_Code4,
                    data=arr,
                )
                results.append(mk)
                time_cursor = cm.m_Time + 1
            else:
                break

        elif ct == ChanType.ADC_MARK:
            n_shorts = rows * cols
            sbuf = (c_short * n_shorts)()
            n_read = lib.S64Read1WaveMark(fhand, chan, byref(cm), sbuf, time_cursor, t_upto, mask)
            if n_read > 0:
                # Note: the MATLAB code transposes (cols, rows) -> (rows, cols)
                arr = np.ctypeslib.as_array(sbuf)[:n_shorts].copy().reshape(cols, rows).T
                mk = CEDWaveMark(
                    time=cm.m_Time, code1=cm.m_Code1, code2=cm.m_Code2,
                    code3=cm.m_Code3, code4=cm.m_Code4,
                    data=arr,
                )
                results.append(mk)
                time_cursor = cm.m_Time + 1
            else:
                break
        else:
            break

    return len(results), results


# ── Marker masks ─────────────────────────────────────────────────────────

def mask_reset(mask_handle: Optional[int] = None) -> int:
    """
    Reset a marker mask or all masks if no handle is given.
    """
    lib = _get_lib()
    if mask_handle is None:
        return lib.S64ResetAllMasks()
    return lib.S64ResetMask(mask_handle)


def mask_mode(mask_handle: int, new_mode: Optional[int] = None) -> int:
    """Get (and optionally set) the mode of a mask. 0=AND, 1=OR."""
    lib = _get_lib()
    prev = lib.S64GetMaskMode(mask_handle)
    if new_mode is not None:
        lib.S64SetMaskMode(mask_handle, new_mode)
    return prev


def mask_col(mask_handle: int, new_col: Optional[int] = None) -> int:
    """Get (and optionally set) the column select of a mask."""
    lib = _get_lib()
    prev = lib.S64GetMaskCol(mask_handle)
    if new_col is not None:
        lib.S64SetMaskCol(mask_handle, new_col)
    return prev


def mask_codes(mask_handle: int, new_codes: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Get (and optionally set) the 256x4 mask code matrix.

    Returns a (256, 4) int32 array.
    """
    lib = _get_lib()
    out_codes = (c_int * 1024)()
    out_mode = c_int(0)
    lib.S64GetMaskCodes(mask_handle, out_codes, byref(out_mode))
    arr = np.ctypeslib.as_array(out_codes).copy().reshape(256, 4)
    if new_codes is not None:
        new_codes = np.asarray(new_codes, dtype=np.int32).ravel()
        in_buf = (c_int * 1024)(*new_codes[:1024])
        lib.S64SetMaskCodes(mask_handle, in_buf)
    return arr


# ── Extra data ───────────────────────────────────────────────────────────

def extra_data(
    fhand: int, n_bytes: int, offset: int,
    data_in: Optional[bytes] = None,
) -> bytes:
    """Get (and optionally set) raw extra data stored in the file header."""
    lib = _get_lib()
    buf = (ctypes.c_ubyte * n_bytes)()
    lib.S64GetExtraData(fhand, buf, n_bytes, offset)
    out = bytes(buf)
    if data_in is not None:
        in_buf = (ctypes.c_ubyte * len(data_in))(*data_in)
        lib.S64SetExtraData(fhand, in_buf, len(data_in), offset)
    return out
