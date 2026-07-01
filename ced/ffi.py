# -*- coding: utf-8 -*-
"""
Created on Sat May 23 06:47:19 2026

@author: Jim
"""

from __future__ import annotations

#Standard
#----------------------
import os
import platform
from pathlib import Path
from typing import List, Optional, Tuple, Union
 
#Third 
#----------------------
import numpy as np

#Local
#----------------------
from .son_types import (
    ChanType,
    CEDMarker,
    CEDTextMark,
    CEDRealMark,
    CEDWaveMark,
    CEDExtMark,
)

# ---------------------------------------------------------------------------
# Import the compiled extension
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_PLATFORM_FOLDER = ("x64" if platform.architecture()[0] == "64bit" else "x86")
_ARCH_DIR = os.path.join(_THIS_DIR,_PLATFORM_FOLDER)
 

# Python 3.8+ requires explicit DLL directories
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(str(_ARCH_DIR))

# Also add to PATH as a fallback for older Python / ctypes loads
os.environ["PATH"] = str(_ARCH_DIR) + os.pathsep + os.environ.get("PATH", "")

#This needs to be done after the path manipulation work
from ._ceds64_cffi import ffi, lib


# ---------------------------------------------------------------------------
# Constants / enums
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Python-side marker data classes
# ---------------------------------------------------------------------------



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
    """cffi buffer to numpy array"""
    
    #0 - empty
    #less than 0 - error (also return empty)
    if count <= 0:
        return np.empty(0, dtype=dtype)
    else:
        ffi_buffer = ffi.buffer(buf, count * np.dtype(dtype).itemsize)
        return np.frombuffer(ffi_buffer, dtype=dtype).copy()


def _marker_to_c(marker: CEDMarker):
    """Convert a shared CEDMarker object to a cffi S64Marker *."""
    m = ffi.new("S64Marker *")
    m.m_Time = marker.time
    m.m_Code1 = marker.code1
    m.m_Code2 = marker.code2
    m.m_Code3 = marker.code3
    m.m_Code4 = marker.code4
    return m


def _marker_from_c(m) -> CEDMarker:
    """Convert a cffi S64Marker struct to a shared CEDMarker object."""
    return CEDMarker(
        time=m.m_Time,
        code1=m.m_Code1,
        code2=m.m_Code2,
        code3=m.m_Code3,
        code4=m.m_Code4,
    )

# ===================================================================
# Public API
# ===================================================================

# ── File management ───────────────────────────────────────────────

def file_count() -> int:
    """
    CEDS64FileCount
    
    Return the number of currently open SON files.
    
    """
    return lib.S64FileCount()


def close_all() -> int:
    """
    CEDS64CloseAll
    
    Close all open SON files. Returns 0 on success.
    """
    return lib.S64CloseAll()


def create(filename: str, n_chans: int = 32, file_type: int = -1) -> int:
    """
    CEDS64Create
    
    Create a new empty SON file.

    Parameters
    ----------
    filename : path to the new .smr or .smrx file.
    n_chans  : maximum channel count (min 32).
    file_type: 
        0=old 32-bit .smr
        1=big 32-bit .smr
        2=64-bit .smrx,
        -1=infer from extension.

    Returns a positive file handle or a negative error code.
    """
    return lib.S64Create(filename.encode(), n_chans, file_type)


def open(filename: str, mode: int = 1) -> int:
    """
    CEDS64Open
    
    Open an existing SON file.

    mode: default 1
        1 = read-only
        0 = read/write
        -1= try r/w then r/o.
    
    Returns a positive file handle or a negative error code.
    """
    return lib.S64Open(filename.encode(), mode)


def is_open(fhand: int) -> int:
    """
    CEDS64IsOpen
    
    1 if the handle is in use, 0 if not, -1 if invalid.
    """
    return lib.S64IsOpen(fhand)


def close(fhand: int) -> int:
    """
    CEDS64Close
    Close a file. Returns 0 on success.
    """
    return lib.S64Close(fhand)


def empty_file(fhand: int) -> int:
    """
    CEDS64EmptyFile
    Clear all data but keep channel definitions.
    """
    return lib.S64Empty(fhand)


##  ── File properties ───────────────────────────────────────────────

def time_base(fhand: int, new_tb: Optional[float] = None) -> float:
    """
    CEDS64TimeBase
    Get (and optionally set) seconds per tick.
    """
    tb = lib.S64GetTimeBase(fhand)
    if new_tb is not None and tb > 0:
        lib.S64SetTimeBase(fhand, new_tb)
    return tb


def max_time(fhand: int) -> int:
    """
    CEDS64MaxTime
    Maximum time (ticks) across all channels."""
    return lib.S64MaxTime(fhand)


def max_channels(fhand: int) -> int:
    """
    CEDS64MaxChan
    Maximum number of channels the file can hold."""
    return lib.S64MaxChans(fhand)


def file_size(fhand: int) -> int:
    """
    CEDS64FileSize
    Estimated file size in bytes."""
    return lib.S64FileSize(fhand)


def version(fhand: int) -> int:
    """
    CEDS64Version
    File format version (major*256 + minor)."""
    
    
    r"""
    //! Get the version of the data file
    /*!
    The returned value is the major file system version * 256 + the minor version. The
    major version number of the 32-bit filing system opened through this interface is 0.
    The first major version of the 64-bit filing system is 1, so the returned value is
    a minimum of 256 for a 64-bit file and less for a 32-bit file.
    \param nFid An integer file handle (1-8)
    \return (Major_Rev * 256)+Minor_Rev
    */
    MATINT_API int S64GetVersion(const int nFid);
    """
    
    return lib.S64GetVersion(fhand)


def secs_to_ticks(fhand: int, seconds) -> Union[int, np.ndarray]:
    """
    CEDS64SecsToTicks
    
    Convert seconds to file ticks.

    Parameters
    ----------
    seconds : float or array-like
        Scalar or array of times in seconds.

    Returns
    -------
    int or np.ndarray of int64
        Time(s) in ticks.
    """
    if np.ndim(seconds) == 0:
        # Scalar — use the DLL directly
        return lib.S64SecsToTicks(fhand, float(seconds))
    else:
        # Array — DLL only handles scalars, so convert manually
        tb = lib.S64GetTimeBase(fhand)
        if tb > 0:
            return np.asarray(seconds / tb, dtype=np.int64)
        else:
            return int(tb)

def ticks_to_secs(fhand: int, ticks) -> Union[float, np.ndarray]:
    """
    Convert file ticks to seconds.

    Parameters
    ----------
    ticks : int or array-like
        Scalar or array of times in ticks.

    Returns
    -------
    float or np.ndarray of float64
        Time(s) in seconds.
    """
    if np.ndim(ticks) == 0:
        return lib.S64TicksToSecs(fhand, int(ticks))
    else:
        tb = lib.S64GetTimeBase(fhand)
        if tb > 0:
            return np.asarray(ticks, dtype=np.float64) * tb
        else:
            return tb


def get_free_chan(fhand: int) -> int:
    """
    CEDS64GetFreeChan
    Lowest unused channel number.
    """
    return lib.S64GetFreeChan(fhand)


def file_comment(fhand: int, index: int,
                 new_comment: Optional[str] = None) -> str:
    """
    CEDS64FileComment
    Get (and optionally set) file comment 
    
    Parameters
    ----------
    index : integer
        An integer value between 1 and 5
    new_comment : string
        The new comment value.
    """
    old = _get_string(lib.S64GetFileComment, fhand, index)
    if new_comment is not None:
        lib.S64SetFileComment(fhand, index, new_comment.encode())
    return old


def time_date(fhand: int, new_time_date=None):
    """
    CEDS64TimeDate
    
    Calling Forms
    -------------
    #1) Get the time
    time_date(fhand)
    
    #2) Set the time
    time_data(fhand,buffer)
    
    Improvements
    -----------
    If new_time_date is datetime, convert to buffer
    
    
    Returns (hundredths, seconds, minutes, hours, day, month, year).
    """
    
    buf_get = ffi.new("long long *")
    buf_set = ffi.new("long long *", 0)

    if new_time_date is None:
        # Get current time/date
        lib.S64TimeDate(fhand, buf_get, buf_set, -1)
        packed = buf_get[0]
    
        result = (
            (packed >>  0) & 0xFF,    # hundredths
            (packed >>  8) & 0xFF,    # seconds
            (packed >> 16) & 0xFF,    # minutes
            (packed >> 24) & 0xFF,    # hours
            (packed >> 32) & 0xFF,    # day
            (packed >> 40) & 0xFF,    # month
            (packed >> 48) & 0xFFFF,  # year (16 bits)
        )
        return result
    else:
        # Set new time/date if provided
        if new_time_date is not None:
            if len(new_time_date) != 7:
                raise ValueError("new_time_date must have exactly 7 elements")
            packed_in = (
                  (new_time_date[0] & 0xFF)
                | (new_time_date[1] & 0xFF)   << 8
                | (new_time_date[2] & 0xFF)   << 16
                | (new_time_date[3] & 0xFF)   << 24
                | (new_time_date[4] & 0xFF)   << 32
                | (new_time_date[5] & 0xFF)   << 40
                | (new_time_date[6] & 0xFFFF) << 48
            )
            buf_set[0] = packed_in
            lib.S64TimeDate(fhand, buf_get, buf_set, 0)


def app_id(fhand: int, new_app_id=None) -> Tuple[int, ...]:
    """
    CEDS64AppID
    
    Get (and optionally set) the 8-byte application ID.

    Returns a tuple of 8 uint8 values.
    """
    # 2 ints = 8 bytes, matching MATLAB's zeros(1, 8, 'int8')
    buf_get = ffi.new("int[8]", [0, 0])
    buf_set = ffi.new("int[8]", [0, 0])
        
    lib.S64AppID(fhand, buf_get, buf_set, -1)
    result = tuple(buf_get[i] & 0xFF for i in range(8))
    
    # Set new app ID if provided
    if new_app_id is not None:
        if isinstance(new_app_id, str):
            new_app_id = new_app_id.encode()
        new_app_id = bytes(new_app_id)[:8].ljust(8, b'\x00')
        buf_set_new = ffi.new("int[8]")
        for i in range(8):
            buf_set_new[i] = new_app_id[i]
        lib.S64AppID(fhand, buf_get, buf_set_new, 0)

    return result


# ── Channel properties ────────────────────────────────────────────

def chan_type(fhand: int, chan: int) -> ChanType:
    """
    CEDS64ChanType
    Channel type as a :class:`ChanType` enum.
    """
    val = lib.S64ChanType(fhand, chan)
    try:
        return ChanType(val)
    except ValueError:
        return val


def chan_divide(fhand: int, chan: int) -> int:
    """
    CEDS64ChanDiv
    Sample interval in file ticks.
    """
    return lib.S64ChanDivide(fhand, chan)


def ideal_rate(fhand: int, chan: int,
               new_rate: Optional[float] = None) -> float:
    """
    CEDS64IdealRate
    
    Get (and optionally set) the ideal sample/event rate (Hz).
    """
    rate = lib.S64GetIdealRate(fhand, chan)
    if new_rate is not None:
        lib.S64SetIdealRate(fhand, chan, new_rate)
    return rate


def chan_title(fhand: int, chan: int,
              new_title: Optional[str] = None) -> str:
    """
    CEDS64ChanTitle
    Get (and optionally set) channel title."""
    old = _get_string(lib.S64GetChanTitle, fhand, chan)
    if new_title is not None:
        lib.S64SetChanTitle(fhand, chan, new_title.encode())
    return old


def chan_comment(fhand: int, chan: int,
                new_comment: Optional[str] = None) -> str:
    """
    CEDS64ChanComment
    Get (and optionally set) channel comment.
    """
    old = _get_string(lib.S64GetChanComment, fhand, chan)
    if new_comment is not None:
        lib.S64SetChanComment(fhand, chan, new_comment.encode())
    return old


def chan_units(fhand: int, chan: int,
              new_units: Optional[str] = None) -> str:
    """
    CEDS64ChanUnits
    Get (and optionally set) channel units string."""
    old = _get_string(lib.S64GetChanUnits, fhand, chan)
    if new_units is not None:
        lib.S64SetChanUnits(fhand, chan, new_units.encode())
    return old


def chan_scale(fhand: int, chan: int,
              new_scale: Optional[float] = None) -> float:
    """
    CEDS64ChanScale
    Get (and optionally set) channel scale."""
    val = ffi.new("double *")
    lib.S64GetChanScale(fhand, chan, val)
    if new_scale is not None:
        lib.S64SetChanScale(fhand, chan, new_scale)
    return val[0]


def chan_offset(fhand: int, chan: int,
               new_offset: Optional[float] = None) -> float:
    """
    CEDS64ChanOffset
    Get (and optionally set) channel offset.
    """
    val = ffi.new("double *")
    lib.S64GetChanOffset(fhand, chan, val)
    if new_offset is not None:
        lib.S64SetChanOffset(fhand, chan, new_offset)
    return val[0]


def chan_max_time(fhand: int, chan: int) -> int:
    """
    CEDS64ChanMaxTime
    Time (ticks) of the last item in the channel."""
    return lib.S64ChanMaxTime(fhand, chan)


def chan_y_range(fhand: int, chan: int,
                new_low: Optional[float] = None,
                new_high: Optional[float] = None) -> Tuple[float, float]:
    """
    CEDS64ChanYRange
    Get (and optionally set) Y-axis display range."""
    lo = ffi.new("double *")
    hi = ffi.new("double *")
    lib.S64GetChanYRange(fhand, chan, lo, hi)
    if new_low is not None and new_high is not None:
        lib.S64SetChanYRange(fhand, chan, new_low, new_high)
    return lo[0], hi[0]


def chan_delete(fhand: int, chan: int) -> int:
    """
    CEDS64ChanDelete
    Delete a channel.
    
    Parameters
    ----------
    chan : 1 based
    """
    return lib.S64ChanDelete(fhand, chan)


def chan_undelete(fhand: int, chan: int) -> int:
    """
    Attempt to undelete a channel.
    
    not exposed in MATLAB version ...
    """
    return lib.S64ChanUndelete(fhand, chan)


def get_ext_mark_info(fhand: int, chan: int) -> Tuple[int, int, int]:
    """
    Return (pre_alignment_points, rows, cols) for extended markers.
    """
    rows = ffi.new("int *")
    cols = ffi.new("int *")
    pre = lib.S64GetExtMarkInfo(fhand, chan, rows, cols)
    return pre, rows[0], cols[0]


def prev_n_time(fhand: int, chan: int, t_from: int, t_to: int,
                n: int = 1, mask: int = -1, as_wave: int = 0) -> int:
    """
    CEDS64PrevNTime
    Time of N items before *t_from*.
    
    t_from but BEFORE t_to. If there aren't iN items between t_to and 
    t_from returns -1
    
    Parameters
    ----------
    fhand - An integer handle to an open file
    chan - An integer channel number
    t_from - The UPPER bound of the time range
    t_to - (Optional) The LOWER bound of the range, if not given it is set to 0
    n - (Optional) The number of items to go back, if not given it is set to 1
    mask - (Optional) An integer handle to a marker mask
    as_wave - (Optional) Only used for extended marker channels, 0 - read 
    the data as events, 1 - read the data as a wave if not given it is set
    to 1, read as events
    
    Outputs
    i64Time - The time in ticks of the item, -1 if no item in the range or
    a negative error cod
    
    
    """
    return lib.S64PrevNTime(fhand, chan, t_from, t_to, n, mask, as_wave)


# ── Channel creation ──────────────────────────────────────────────

def set_wave_chan(fhand: int, chan: int, t_div: int,
                 chan_type_code: int = 1, rate: float = 0.0) -> int:
    """
    CEDS64SetWaveChan
    Create a waveform channel. 
    
    1=Adc (int16)
    9=RealWave (float32).
    
    Parameters
    fhand - An integer handle to an open file
    chan - An integer channel number
    t_div - The channel divide rate
    chan_type_code - The type of the new channel 1 = waveform, 9 = realwave
    rate - (Optional) The rate of the new channel as a double
    
    """
    return lib.S64SetWaveChan(fhand, chan, t_div, chan_type_code, rate)


def set_event_chan(fhand: int, chan: int, rate: float,
                  event_type: int = 2) -> int:
    """
    CEDS64SetEventChan
      
    Parameters
    ----------
    fhand - An integer handle to an open file
    chan - An integer channel number
    rate - The rate of the new channel as a double
    event_type - (Optional) , default 2
        The type of the new channel 
        2 = falling event
        3 = rising event
        4 = both
  """
    return lib.S64SetEventChan(fhand, chan, rate, event_type)


def set_marker_chan(fhand: int, chan: int, rate: float,
                   kind: int = 5) -> int:
    """
    CEDS64SetMarkerChan
    
    Parameters
    ----------
    fhand - An integer handle to an open file
    chan - An integer channel number
    rate - The rate of the new channel as a double
    kind - (Optional) , default 5
        The type of the new channel 
        5 = marker channel
        4 = level channel.
    """
    return lib.S64SetMarkerChan(fhand, chan, rate, kind)


def set_level_chan(fhand: int, chan: int, rate: float) -> int:
    """
    CEDS64SetLevelChan
    
    Parameters
    ----------
    fhand - An integer handle to an open file
    chan - An integer channel number
    rate - The rate of the new channel as a double
    
    Create an EventBoth (level) channel.
    """
    return lib.S64SetLevelChan(fhand, chan, rate)


def set_init_level(fhand: int, chan: int, level: int) -> int:
    """
    Set initial level of an EventBoth channel (0=low).
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - An integer channel number
%   iLevel - If 0 then the initial level is low, otherwise it is high
    """
    return lib.S64SetInitLevel(fhand, chan, level)


def set_text_mark_chan(fhand: int, chan: int, rate: float,
                      max_chars: int) -> int:
    """
    Create a TextMark channel.
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - An integer channel number
%   dRate - The rate of the new channel as a double
%   iMax - Length of the text string that can be attatched to each marker
%   channel
    
    """
    return lib.S64SetTextMarkChan(fhand, chan, rate, max_chars)


def set_ext_mark_chan(fhand: int, chan: int, rate: float,
                     ext_type: int = 1, rows: int = 1,
                     cols: int = 1, t_div: int = 0) -> int:
    """
    Create an extended marker channel.
    ext_type: 
        1=AdcMark
        2=RealMark
        3=TextMark.
    
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - An integer channel number
%   dRate - The rate of the new channel as a double
%   iType - The type of the new channel 6 = wave mark channel, 7 = real
%   mark channel, 8 = text mark channel (use CED64SetTextMark instead?)
%   iRows - Number of rows for the channel
%   iCols - (Optional) Number of columns for the channel, if not supplied
%   defualts to 1
%   i64Div - (Optional) Sets the divide rate for the channel, only used in wavemark
%   channels
    
    """
    return lib.S64SetExtMarkChan(fhand, chan, rate, ext_type,
                                 rows, cols, t_div)


# ── Waveform read / write ─────────────────────────────────────────

def write_wave(fhand: int, chan: int,
               data: np.ndarray, t_from: int) -> int:
    """
    Write waveform data.  Accepts int16 or float32 numpy arrays.
    Returns next write time or a negative error code.
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - An integer channel number
%   Wave - A vector of 16-bit integers or floating-point values
%   i64STime - The time in ticks of the first point
    
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
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - A channel number for a Waveform or Realwave channel
%   iN - The maximum number of data points  to copy
%   i64From - The time in ticks of the earliest time you want to read
%   i64To - (Optional) The time in ticks of the latest time you want to
%   read. If not set or set to -1, read to the end of the channel
%   maskh - (Optional) An integer handle to a marker mask (only used when reading wavemarkers)
    
    
    
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
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - A channel number for a Waveform or Realwave channel
%   iN - The maximum number of data points  to copy
%   i64From - The time in TICKS of the earliest time you want to read
%   i64To - (Optional) The time in ticks of the latest time you want to
%   read. If not set or set to -1, read to the end of the channel
%   maskh - (Optional) An integer handle to a marker mask (only used when reading wavemarkers)
    
    
    """
    
    
    r"""
    \param nFid An integer file handle (1-8)
    \param nChan The waveform channel to read. This can be either Adc or RealWave.
    \param pData The buffer to receive the read data.
    \param nMax The maximum number of values to read.
    \param tFrom This and tUpto define a time range in which to locate the data to read. The first data point will
    be at or after tFrom.
    \param tUpto Not data returned will be at or after this time.
    \param tFirst If any data is returned this is set to the time of the first item.
    \param nMask Integer filter handle Used with AdcMark channels to filter the data.
    \return The number of values returned or a negative error code.
    */
    MATINT_API int S64ReadWaveS(
        const int nFid, 
        const int nChan, 
        short* pData, 
        const int nMax,
        const long long tFrom, 
        const long long tUpto, 
        long long* tFirst, 
        const int nMask);
    """
    
    buf = ffi.new(f"short[{n_max}]")
    t_first = ffi.new("long long *")
    n_read = lib.S64ReadWaveS(fhand, chan, buf, n_max,
                              t_from, t_to, t_first, mask)
    arr = _np_from_buf(buf, np.int16, n_read)
    return n_read, arr, t_first[0]


# ── Event read / write ────────────────────────────────────────────

def write_events(fhand: int, chan: int, times: np.ndarray) -> int:
    """
    Write event times (int64, in ticks). Returns 0 on success.
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - An channel number for an event channel
%   i64Event - A vector of 64-bit integer times (in ticks)
    """
    times = np.ascontiguousarray(times, dtype=np.int64)
    buf = ffi.from_buffer("long long[]", times)
    return lib.S64WriteEvents(fhand, chan, buf, len(times))


def read_events(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1, mask: int = -1,
                ) -> Tuple[int, np.ndarray]:
    """
    Read event times.

    Returns (n_read, int64_array).
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - A channel number for a Waveform or Realwave channel
%   iN - The maximum number of events to read
%   i64From - The time in ticks of the earliest time you want to read
%   i64To - (Optional) The time in ticks of the latest time you want to
%   read. If not set or set to -1, read to the end of the channel
%   maskh - (Optional) An integer handle to a marker mask
    
    """
    buf = ffi.new(f"long long[{n_max}]")
    n_read = lib.S64ReadEvents(fhand, chan, buf, n_max,
                               t_from, t_to, mask)
    arr = _np_from_buf(buf, np.int64, n_read)
    return n_read, arr


# ── Level (EventBoth) read / write ────────────────────────────────

def write_levels(fhand: int, chan: int, times: np.ndarray) -> int:
    """
    
    Write level-toggle times to an EventBoth channel.
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - An integer channel number
%   i64Level - A vector of 64-bit integer times (in ticks)
    
    """
    times = np.ascontiguousarray(times, dtype=np.int64)
    buf = ffi.from_buffer("long long[]", times)
    return lib.S64WriteLevels(fhand, chan, buf, len(times))


def read_levels(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1) -> Tuple[int, np.ndarray, int]:
    """
    Read level data.

    Returns (n_read, int64_times, initial_level).
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - A channel number for a Waveform or Realwave channel
%   iN - The maximum number of events to read
%   i64From - The time in ticks of the earliest time you want to read
%   i64To - The time in ticks of the latest time you want to read (optional if not set, read to the end of the channel)
    
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
    """
    CEDS64WriteMarkers
    Write a list of :class:`CEDMarker` to a marker channel.
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - An integer channel number
%   cMarkers - A vector of CMatMarkers
    
    """
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
    r"""
    Read markers. Returns (n_read, list_of_CEDMarker).
    
    
    Improvements
    ------------
    1. Allow outputing as a single object with arrays rather
    than an array of objects
    
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - A channel number for an event or extended event channel
%   iN - The maximum number of data points to read
%   i64From - The time in ticks of the earliest time you want to read
%   i64To - (Optional) The time in ticks of the latest time you want to
%   read. If not set or set to -1, read to the end of the channel
%   maskh - (Optional) An integer handle to a marker mask


    //! Read Marker data from a Marker or extended Marker channel
    /*!
    You can read marker data from any channel that contains markers.
    \param nFid An integer file handle (1-8)
    \param nChan A Marker, EventBoth or extended marker channel.
    \param pData A buffer to receive the marker data.
    \param nMax  The maximum number of Markers to return.
    \param tFrom The first time to include in the search for markers.
    \param tUpto The first time not to include. Returned data will span the time range
    tRom up to but not including tUpto.
    \param nMask Integer filter handle Used with AdcMark channels to filter the data.
    \return The number of markers read or a negative error code.
    */
    MATINT_API int S64ReadMarkers(const int nFid, 
                                  const int nChan, 
                                  S64Marker* pData, 
                                  const int nMax,
                                  const long long tFrom, 
                                  const long long tUpto,
                                  const int nMask);


    """
    buf = ffi.new(f"S64Marker[{n_max}]")
    n_read = lib.S64ReadMarkers(fhand, chan, buf, n_max,
                                t_from, t_to, mask)
    
    
    #JAH: This may be slow/overkill compared to simply mapping
    #to an array.
    if n_read > 0:
        return n_read, [_marker_from_c(buf[i]) for i in range(n_read)]
    return n_read, []


def edit_marker(fhand: int, chan: int, time: int,
                marker: CEDMarker) -> int:
    """Replace the codes of an existing marker at *time*."""
    m = _marker_to_c(marker)
    return lib.S64EditMarker(fhand, chan, time, m)


# ── Extended marker read / write ──────────────────────────────────

def write_ext_marks(
    fhand: int,
    chan: int,
    markers: List[CEDExtMark],
) -> int:
    """Write extended markers one at a time."""
    ct = lib.S64ChanType(fhand, chan)

    for mk in markers:
        cm = _marker_to_c(mk)

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
    fhand: int,
    chan: int,
    n_max: int,
    t_from: int,
    t_to: int = -1,
    mask: int = -1,
) -> Tuple[int, List[CEDExtMark]]:
    """
    CEDS64ReadExtMarks
    Read extended markers from a TextMark, RealMark, or WaveMark channel.

    Returns (n_read, list_of_extended_markers).
    
    %   Inputs
%   fhand - An integer handle to an open file
%   iChan - A channel number for an extended event channel
%   iN - The maximum number of data points to read
%   i64From - The time in ticks of the earliest time you want to read
%   i64To - (Optional) The time in ticks of the latest time you want to
%   read. If not set or set to -1, read to the end of the channel
%   maskh -  (Optional) An integer handle to a marker mask
    
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