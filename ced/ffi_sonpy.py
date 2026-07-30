# -*- coding: utf-8 -*-
"""
ffi_sonpy.py
============
A *drop-in* replacement for ``ced/ffi_ceds64.py`` that is backed by CED's official
**sonpy** package (https://pypi.org/project/sonpy/) instead of the compiled
``ceds64int`` DLL + cffi extension.

Why this exists
---------------
The original ``ffi_ceds64.py`` wraps the native SON64 DLL through a hand-built cffi
extension. That path is Windows-only and requires the prebuilt ``.pyd`` files
shipped in the package. ``sonpy`` is CED's own cross-platform binding (Windows,
macOS, Linux) and so makes a convenient *second* backend.

This module exposes the **same public names, signatures and return shapes** as
``ffi_ceds64.py``, so ``main.py`` treats the two as interchangeable modules and
picks one at runtime::

    ced.read_file(path, backend="sonpy")     # -> this module
    ced.read_file(path, backend="ceds64")    # -> ffi_ceds64
    ced.read_file(path)                      # -> first one available

See ``_get_backend()`` in main.py. Note the two are interchangeable only for
what main.py needs: ``edit_marker``, ``write_ext_marks``, ``extra_data`` and
the ``mask_*`` functions exist in ffi_ceds64.py and have no equivalent here.

------------------------------------------------------------------------------
HOW THE TRANSLATION WAS DONE  (read this!)
------------------------------------------------------------------------------
This file was written by translating the documented sonpy 1.9.5 API (the man
pages / ``SonPy.pdf`` shipped inside the wheel) onto the ``ffi_ceds64.py`` contract.
The mapping was reasoned from documentation and the bundled example scripts
(``MakeFile.py``, ``ReadFile.py``, ``ReadWave.py``); it has **not** been run
end-to-end here. Anything that could not be 100% pinned down from the docs is
marked ``# VERIFY:`` so it is easy to find and confirm against a live install.

Key structural differences between the two APIs and how they are bridged:

1. OBJECT vs HANDLE.
   sonpy is object-oriented: ``f = sonpy.SonFile(path, True)``. ``ffi_ceds64.py``
   uses an *integer* file handle. We keep a small registry mapping an int
   handle -> SonFile object so the ``fhand: int`` contract is preserved.
   ``open()`` returns a positive int on success or a negative error code.

2. CHANNEL NUMBERING.
   The native DLL / ``ffi_ceds64.py`` use **1-based** channel numbers (``main.py``
   loops ``range(1, n_chans + 1)``). sonpy uses **0-based** channel numbers
   (``ReadFile.py`` loops ``range(MaxChannels())`` and prints ``i + 1``).
   Every channel-taking function here therefore calls sonpy with ``chan - 1``.

3. WAVEFORM READS + GAPS.
   ``ffi_ceds64.read_wave_s`` returns ``(n_read, data, t_first)``; the DLL
   returns data only up to the next gap, which ``main.py`` relies on to split
   a channel into WaveformSegments. sonpy's ``ReadInts``/``ReadFloats`` return
   only the data array, so we recover the first tick with ``FirstTime()``.

   The sonpy docs suggest a read "will simply be passed over" a gap, which
   would collapse a paused recording into one segment. Measured against
   sonpy 1.9.12 that is NOT what happens: reading Demo1.smr (6 segments of
   1200 samples, separated by pauses) returns 1200 samples and stops at the
   first gap, exactly as the DLL does. test_backend_parity.py asserts the two
   backends agree on segment count and content for that file.

4. NEW vs OLD sonpy import path.
   sonpy <= 1.9.5 exposed the library as ``sonpy.lib`` (``from sonpy import
   lib as sp``). Newer sonpy (e.g. 1.9.12) exposes everything directly on the
   top-level ``sonpy`` module (``import sonpy; sonpy.SonFile(...)``). We detect
   both so this file works against either.

------------------------------------------------------------------------------
"""

from __future__ import annotations

#Standard
#---------------------------
from typing import Dict, List, Optional, Tuple, Union

#Third
#---------------------------
import numpy as np

#Local
#---------------------------
from .son_types import (
    ChanType,
    CEDMarker,
    CEDTextMark,
    CEDRealMark,
    CEDWaveMark,
    CEDExtMark,
)

# ---------------------------------------------------------------------------
# Import sonpy, supporting both the new (sonpy.X) and old (sonpy.lib.X) layouts
# ---------------------------------------------------------------------------
try:
    import sonpy as _sonpy_pkg
except ImportError as exc:  # pragma: no cover - environment dependent
    raise ImportError(
        "The 'sonpy' package is required by ffi_sonpy. Install it with "
        "`pip install sonpy`. Note sonpy ships platform/Python-specific "
        "binaries; make sure a build exists for your interpreter."
    ) from exc

# New sonpy puts SonFile et al. straight on the package; older sonpy (<=1.9.5)
# puts them on the `.lib` sub-module. Pick whichever actually has SonFile.
if hasattr(_sonpy_pkg, "SonFile"):
    sp = _sonpy_pkg                      # new layout: sonpy.SonFile, sonpy.DataType
elif hasattr(_sonpy_pkg, "lib") and hasattr(_sonpy_pkg.lib, "SonFile"):
    sp = _sonpy_pkg.lib                  # old layout: sonpy.lib.SonFile
else:  # pragma: no cover
    raise ImportError(
        "Could not locate SonFile in the installed sonpy package. Tried "
        "sonpy.SonFile and sonpy.lib.SonFile."
    )


# ---------------------------------------------------------------------------
# DataType (sonpy) -> ChanType (this package) mapping
# ---------------------------------------------------------------------------
# sonpy's ``DataType`` enum uses the same integer codes as the CED SON channel
# types (Off=0, Adc=1, EventFall=2, EventRise=3, EventBoth=4, Marker=5,
# AdcMark=6, RealMark=7, TextMark=8, RealWave=9), which is exactly how
# ``ChanType`` is defined in son_types.py. We therefore pair them by integer
# value. The tables are built dynamically so they track whatever members the
# installed sonpy actually exposes, and are looked up by both enum-member
# identity (_DATATYPE_TO_CHANTYPE) and member name (_DT_NAME_TO_CHANTYPE) by
# chan_type().
_DATATYPE_TO_CHANTYPE: Dict[object, ChanType] = {}
_DT_NAME_TO_CHANTYPE: Dict[str, ChanType] = {}
for _name in dir(sp.DataType):
    if _name.startswith("_"):
        continue
    _member = getattr(sp.DataType, _name)
    try:
        _code = int(_member)
    except (TypeError, ValueError):
        continue  # skip non-member attributes such as 'name'/'value'
    try:
        _ct = ChanType(_code)
    except ValueError:
        continue  # sonpy code with no ChanType equivalent
    _DATATYPE_TO_CHANTYPE[_member] = _ct
    _DT_NAME_TO_CHANTYPE[_name] = _ct
del _name, _member, _code, _ct


# ---------------------------------------------------------------------------
# Handle registry  (int handle  <->  sonpy.SonFile object)
# ---------------------------------------------------------------------------

_files: Dict[int, "object"] = {}   # handle -> SonFile
_next_handle: int = 1

# sonpy "no error" sentinel; SonError.Son_OK == 0 in the library.
_S64_OK = 0


def _register(sonfile) -> int:
    """Store a SonFile and return a fresh positive integer handle."""
    global _next_handle
    h = _next_handle
    _next_handle += 1
    _files[h] = sonfile
    return h


def _get(fhand: int):
    """Resolve an int handle to a SonFile, or raise a clear error."""
    try:
        return _files[fhand]
    except KeyError:
        raise ValueError(
            f"Invalid/closed sonpy file handle: {fhand!r}. "
            f"Open handles: {sorted(_files)}"
        )


def _max_tick(sonfile) -> int:
    """
    A safe 'read to the end' upper bound in ticks. sonpy read functions take a
    tUpto; ffi_ceds64.py uses t_to == -1 to mean 'to the end'. We translate that to
    the largest legal 64-bit tick (or, failing that, the file's max time + 1).
    """
    try:
        return int(sp.MaxTime64())
    except Exception:
        try:
            return int(sonfile.MaxTime()) + 1
        except Exception:
            return np.iinfo(np.int64).max


def _resolve_tupto(sonfile, t_to: int) -> int:
    """ffi_ceds64.py convention: t_to < 0 means 'to the end'."""
    return _max_tick(sonfile) if t_to is None or t_to < 0 else int(t_to)


# ===================================================================
# Public API
# ===================================================================

# -- File management ------------------------------------------------

def file_count() -> int:
    """Number of currently open SON files (handles tracked by this module)."""
    return len(_files)


def close_all() -> int:
    """Close every open SON file. Returns 0 on success."""
    for h in list(_files):
        close(h)
    return _S64_OK


def create(filename: str, n_chans: int = 32, file_type: int = -1) -> int:
    """
    Create a new empty SON file.

    sonpy maps to the *creating* SonFile constructor::

        SonFile(sName, nChans=32, nArea=0)

    NOTE on ``file_type``: the native DLL lets you force 0=old .smr,
    1=big .smr, 2=.smrx, -1=infer-from-extension. sonpy instead *always*
    infers the architecture from the file extension ('.smr' -> 32-bit, else
    64-bit) and exposes no equivalent flag, so ``file_type`` is accepted for
    signature compatibility but ignored beyond a sanity check. Choose the
    extension to control the format.  (# VERIFY: behaviour for '.smr')

    Returns a positive handle or a negative error code.
    """
    sonfile = sp.SonFile(str(filename), int(n_chans), 0)
    err = sonfile.GetOpenError()
    if err != _S64_OK:
        return int(err)
    return _register(sonfile)


def open(filename: str, mode: int = 1) -> int:
    """
    Open an existing SON file.

    ffi_ceds64.py ``mode``:  1 = read-only, 0 = read/write, -1 = try r/w then r-o.
    sonpy constructor: ``SonFile(sName, bReadOnly, flags=OpenFlags.None)``.

    Returns a positive handle or a negative error code.
    """
    def _try(read_only: bool):
        f = sp.SonFile(str(filename), bool(read_only))
        return f, f.GetOpenError()

    if mode == 0:
        sonfile, err = _try(read_only=False)
    elif mode == -1:
        sonfile, err = _try(read_only=False)
        if err != _S64_OK:
            sonfile, err = _try(read_only=True)
    else:  # default / mode == 1 -> read-only
        sonfile, err = _try(read_only=True)

    if err != _S64_OK:
        return int(err)
    return _register(sonfile)


def is_open(fhand: int) -> int:
    """1 if the handle is in use, 0 if not. (-1 unused; kept for parity.)"""
    return 1 if fhand in _files else 0


def close(fhand: int) -> int:
    """
    Close a file. Returns 0 on success.

    sonpy has no explicit Close(); the file is flushed/saved when the SonFile
    object is destroyed. We commit (if writable) then drop our reference so the
    object can be finalised.
    """
    sonfile = _files.pop(fhand, None)
    if sonfile is None:
        return _S64_OK
    try:
        if sonfile.CanWrite():
            sonfile.Commit()          # flush header + buffered data to disk
    except Exception:
        pass
    del sonfile                       # release; SonFile destructor saves/closes
    return _S64_OK


def empty_file(fhand: int) -> int:
    """Clear all data but keep channel definitions."""
    return int(_get(fhand).EmptyFile())


# -- File properties ------------------------------------------------

def time_base(fhand: int, new_tb: Optional[float] = None) -> float:
    """Get (and optionally set) seconds per tick."""
    sonfile = _get(fhand)
    tb = float(sonfile.GetTimeBase())
    if new_tb is not None and tb > 0:
        sonfile.SetTimeBase(float(new_tb))
    return tb


def max_time(fhand: int) -> int:
    """Maximum time (ticks) across all channels."""
    return int(_get(fhand).MaxTime())


def max_channels(fhand: int) -> int:
    """Maximum number of channels the file can hold."""
    return int(_get(fhand).MaxChannels())


def file_size(fhand: int) -> int:
    """Estimated file size in bytes."""
    return int(_get(fhand).FileSize())


def version(fhand: int) -> int:
    """
    File format version. The native call returns ``major*256 + minor``.
    sonpy's ``GetVersion()`` returns the underlying SON version integer, which
    we pass through. Used by main.py only as metadata. (# VERIFY: exact value)
    """
    return int(_get(fhand).GetVersion())


def secs_to_ticks(fhand: int, seconds) -> Union[int, np.ndarray]:
    """
    Convert seconds to file ticks. sonpy exposes no SecsToTicks, so we compute
    it from the timebase: ticks = round(seconds / timebase).
    """
    tb = float(_get(fhand).GetTimeBase())
    if tb <= 0:
        return 0 if np.ndim(seconds) == 0 else np.zeros_like(np.asarray(seconds), dtype=np.int64)
    if np.ndim(seconds) == 0:
        return int(round(float(seconds) / tb))
    return np.asarray(np.round(np.asarray(seconds, dtype=np.float64) / tb), dtype=np.int64)


def ticks_to_secs(fhand: int, ticks) -> Union[float, np.ndarray]:
    """Convert file ticks to seconds (ticks * timebase)."""
    tb = float(_get(fhand).GetTimeBase())
    if np.ndim(ticks) == 0:
        return float(ticks) * tb
    return np.asarray(ticks, dtype=np.float64) * tb


def get_free_chan(fhand: int) -> int:
    """
    Lowest unused channel number. sonpy ``GetFreeChannel`` is 0-based; we add 1
    to return a 1-based channel to match the rest of this (ffi_ceds64.py) interface.
    """
    return int(_get(fhand).GetFreeChannel()) + 1


def file_comment(fhand: int, index: int,
                 new_comment: Optional[str] = None) -> str:
    """
    Get (and optionally set) a file comment.

    ffi_ceds64.py / main.py use 1-based comment indices (main.py reads 1..8). sonpy is
    0-based (MakeFile.py uses ``SetFileComment(0, ...)``) so we pass index - 1.
    """
    sonfile = _get(fhand)
    idx0 = int(index) - 1
    old = str(sonfile.GetFileComment(idx0))
    # sonpy returns the raw fixed-size comment buffer, which for *empty* comment
    # slots can contain leftover bytes after a leading NUL (e.g. '\x00onverted
    # from CFS...'). Apply C-string semantics and keep only the text up to the
    # first NUL, so empty slots come back as '' like the ceds64 backend.
    old = old.split("\x00", 1)[0]
    if new_comment is not None:
        sonfile.SetFileComment(idx0, str(new_comment))
    return old


def time_date(fhand: int, new_time_date=None):
    """
    Get (or set) the file start time/date.

    Returns a tuple ``(hundredths, seconds, minutes, hours, day, month, year)``
    -- the same order ``ffi_ceds64.py`` documents. sonpy ``GetTimeDate()`` returns a
    vector<uint16_t> built from the native ``TTimeDate`` struct, whose field
    order is hun, sec, min, hour, day, mon, year -- i.e. identical. We pass it
    through unchanged.

    # VERIFY: the element order of GetTimeDate() against a live install. If a
    # file has no stored date, sonpy returns all-zeros, which main.py already
    # treats as 'no datetime'.
    """
    sonfile = _get(fhand)
    if new_time_date is None:
        vals = list(sonfile.GetTimeDate())
        # Pad/truncate to the 7-tuple ffi_ceds64.py promises.
        vals = (list(vals) + [0] * 7)[:7]
        return tuple(int(v) for v in vals)
    else:
        if len(new_time_date) != 7:
            raise ValueError("new_time_date must have exactly 7 elements")
        # sonpy SetTimeDate takes a py::list in the same field order.
        sonfile.SetTimeDate([int(v) for v in new_time_date])
        return None


def app_id(fhand: int, new_app_id=None) -> Tuple[int, ...]:
    """
    Get (and optionally set) the 8-byte application ID.

    Returns a tuple of 8 uint8 values (matching ffi_ceds64.py). sonpy stores the
    AppID as a string (``GetAppID`` / ``SetAppID``), so we encode/decode the
    bytes. # VERIFY: encoding of non-ASCII app-id bytes.
    """
    sonfile = _get(fhand)
    raw = sonfile.GetAppID()
    raw_bytes = (raw.encode("latin-1", "replace") if isinstance(raw, str)
                 else bytes(raw))
    raw_bytes = raw_bytes[:8].ljust(8, b"\x00")
    result = tuple(int(b) for b in raw_bytes)

    if new_app_id is not None:
        if isinstance(new_app_id, str):
            new_app_id = new_app_id.encode("latin-1", "replace")
        new_app_id = bytes(new_app_id)[:8].ljust(8, b"\x00")
        sonfile.SetAppID(new_app_id.decode("latin-1"))

    return result


# -- Channel properties ---------------------------------------------
#
# Reminder: every `chan` argument below is 1-based (ffi_ceds64.py convention) and is
# translated to sonpy's 0-based numbering via `chan - 1`.

def chan_type(fhand: int, chan: int) -> ChanType:
    """Channel type as a :class:`ChanType` enum."""
    dt = _get(fhand).ChannelType(chan - 1)
    ct = _DATATYPE_TO_CHANTYPE.get(dt)
    if ct is not None:
        return ct
    # Fall back: try to coerce via the member name, else return raw.
    name = getattr(dt, "name", None)
    if name in _DT_NAME_TO_CHANTYPE:
        return _DT_NAME_TO_CHANTYPE[name]
    return dt  # unknown / error code


def chan_divide(fhand: int, chan: int) -> int:
    """
    Sample interval in file ticks.

    ``chan_div`` is only physically meaningful for sampled channels (Adc,
    RealWave and AdcMark/WaveMark); for those, sonpy and ceds64 already agree
    and we return sonpy's value directly.

    For non-sampled channels (events, markers, levels, text/real marks) the
    value is not meaningful and the two backends diverge: sonpy's
    ``ChannelDivide`` always returns 1, whereas the native ``S64ChanDivide``
    returns 0 for 64-bit (.smrx) files but 1 for 32-bit (.smr) files. We mirror
    that format-dependent behaviour -- keyed off the documented version
    boundary (>= 256 == 64-bit filing system) -- so the backends report
    identical ``chan_div`` (and hence identical ``Channel.fs``) on both formats.
    """
    sonfile = _get(fhand)
    ct = chan_type(fhand, chan)
    if ct in (ChanType.ADC, ChanType.REAL_WAVE, ChanType.ADC_MARK):
        return int(sonfile.ChannelDivide(chan - 1))
    # Non-sampled channel: match ceds64's format-dependent value.
    if version(fhand) >= 256:        # 64-bit (.smrx)
        return 0
    return int(sonfile.ChannelDivide(chan - 1))


def ideal_rate(fhand: int, chan: int,
               new_rate: Optional[float] = None) -> float:
    """Get (and optionally set) the ideal sample/event rate (Hz)."""
    sonfile = _get(fhand)
    rate = float(sonfile.GetIdealRate(chan - 1))
    if new_rate is not None:
        sonfile.SetIdealRate(chan - 1, float(new_rate))
    return rate


def chan_title(fhand: int, chan: int,
               new_title: Optional[str] = None) -> str:
    """Get (and optionally set) channel title."""
    sonfile = _get(fhand)
    old = str(sonfile.GetChannelTitle(chan - 1))
    if new_title is not None:
        sonfile.SetChannelTitle(chan - 1, str(new_title))
    return old


def chan_comment(fhand: int, chan: int,
                 new_comment: Optional[str] = None) -> str:
    """Get (and optionally set) channel comment."""
    sonfile = _get(fhand)
    old = str(sonfile.GetChannelComment(chan - 1))
    if new_comment is not None:
        sonfile.SetChannelComment(chan - 1, str(new_comment))
    return old


def chan_units(fhand: int, chan: int,
               new_units: Optional[str] = None) -> str:
    """Get (and optionally set) channel units string."""
    sonfile = _get(fhand)
    old = str(sonfile.GetChannelUnits(chan - 1))
    if new_units is not None:
        sonfile.SetChannelUnits(chan - 1, str(new_units))
    return old


def chan_scale(fhand: int, chan: int,
               new_scale: Optional[float] = None) -> float:
    """
    Get (and optionally set) channel scale.

    Same scale/offset convention as the native DLL:
        user units = integer * scale / 6553.6 + offset
    so main.py's int16 -> physical conversion is unchanged.
    """
    sonfile = _get(fhand)
    val = float(sonfile.GetChannelScale(chan - 1))
    if new_scale is not None:
        sonfile.SetChannelScale(chan - 1, float(new_scale))
    return val


def chan_offset(fhand: int, chan: int,
                new_offset: Optional[float] = None) -> float:
    """Get (and optionally set) channel offset."""
    sonfile = _get(fhand)
    val = float(sonfile.GetChannelOffset(chan - 1))
    if new_offset is not None:
        sonfile.SetChannelOffset(chan - 1, float(new_offset))
    return val


def chan_max_time(fhand: int, chan: int) -> int:
    """Time (ticks) of the last item in the channel (-1 if no data)."""
    return int(_get(fhand).ChannelMaxTime(chan - 1))


def chan_first_time(fhand: int, chan: int, t_from: int = 0,
                    t_to: int = -1) -> int:
    """
    Tick of the first item at or after *t_from*, or -1 if the channel holds
    no data in the range. sonpy exposes this directly as ``FirstTime``.

    Deliberately NOT implemented as a one-sample ``read_wave_s``: a single
    negative sample value is indistinguishable from sonpy's negative error
    sentinel (see _looks_like_error_array).
    """
    sonfile = _get(fhand)
    tupto = _resolve_tupto(sonfile, t_to)
    t = int(sonfile.FirstTime(chan - 1, int(t_from), tupto))
    return t if t >= 0 else -1


def chan_y_range(fhand: int, chan: int,
                 new_low: Optional[float] = None,
                 new_high: Optional[float] = None) -> Tuple[float, float]:
    """
    Get (and optionally set) Y-axis display range.
    sonpy ``GetChannelYRange`` returns a (low, high) pair.
    """
    sonfile = _get(fhand)
    lo, hi = sonfile.GetChannelYRange(chan - 1)
    if new_low is not None and new_high is not None:
        sonfile.SetChannelYRange(chan - 1, float(new_low), float(new_high))
    return float(lo), float(hi)


def chan_delete(fhand: int, chan: int) -> int:
    """Delete a channel (1-based)."""
    return int(_get(fhand).ChannelDelete(chan - 1))


def chan_undelete(fhand: int, chan: int) -> int:
    """Attempt to undelete a channel."""
    return int(_get(fhand).ChannelUndelete(chan - 1, True))


def get_ext_mark_info(fhand: int, chan: int) -> Tuple[int, int, int]:
    """
    Return ``(pre_alignment_points, rows, cols)`` for extended markers.

    NOTE the reordering: sonpy ``GetExMarkInfo`` returns ``[nRows, nCols, nPre]``
    whereas ffi_ceds64.py returns ``(pre, rows, cols)``.
    """
    info = list(_get(fhand).GetExMarkInfo(chan - 1))
    info = (list(info) + [0, 0, 0])[:3]
    rows, cols, pre = int(info[0]), int(info[1]), int(info[2])
    return pre, rows, cols


def prev_n_time(fhand: int, chan: int, t_from: int, t_to: int = 0,
                n: int = 1, mask: int = -1, as_wave: int = 0) -> int:
    """
    Time of the N-th item before ``t_from`` (and at/after ``t_to``), or -1.

    sonpy: ``PreviousNTime(chan, trStart, trEnd=0, n=1, bAsWave=False, Filter)``.
    The ffi_ceds64.py ``mask`` argument has no plain sonpy equivalent (sonpy uses a
    MarkerFilter object); we ignore it and use sonpy's default filter.
    """
    return int(_get(fhand).PreviousNTime(
        chan - 1, int(t_from), int(t_to), int(n), bool(as_wave)))


# -- Channel creation -----------------------------------------------

def set_wave_chan(fhand: int, chan: int, t_div: int,
                  chan_type_code: int = 1, rate: float = 0.0) -> int:
    """
    Create a waveform channel. ``chan_type_code``: 1=Adc(int16), 9=RealWave.
    sonpy: ``SetWaveChannel(chan, tDivide, eKind, dRate=0, iPhysChan=-1)``.
    """
    kind = sp.DataType.RealWave if int(chan_type_code) == 9 else sp.DataType.Adc
    return int(_get(fhand).SetWaveChannel(chan - 1, int(t_div), kind, float(rate)))


def set_event_chan(fhand: int, chan: int, rate: float,
                   event_type: int = 2) -> int:
    """
    Create an event channel. ``event_type``: 2=fall, 3=rise, 4=both.
    sonpy: ``SetEventChannel(chan, dRate, evtKind=EventFall, iPhysChan=-1)``.
    """
    kind = {
        2: sp.DataType.EventFall,
        3: sp.DataType.EventRise,
        4: sp.DataType.EventBoth,
    }.get(int(event_type), sp.DataType.EventFall)
    return int(_get(fhand).SetEventChannel(chan - 1, float(rate), kind))


def set_marker_chan(fhand: int, chan: int, rate: float, kind: int = 5) -> int:
    """
    Create a marker channel. ffi_ceds64.py ``kind`` 5=marker, 4=level(EventBoth).
    sonpy has a dedicated ``SetMarkerChannel``; a 'level' channel is just an
    EventBoth event channel.
    """
    if int(kind) == 4:
        return int(_get(fhand).SetEventChannel(
            chan - 1, float(rate), sp.DataType.EventBoth))
    return int(_get(fhand).SetMarkerChannel(chan - 1, float(rate)))


def set_level_chan(fhand: int, chan: int, rate: float) -> int:
    """Create an EventBoth (level) channel."""
    return int(_get(fhand).SetEventChannel(
        chan - 1, float(rate), sp.DataType.EventBoth))


def set_init_level(fhand: int, chan: int, level: int) -> int:
    """Set initial level of an EventBoth channel (0=low)."""
    return int(_get(fhand).SetInitialLevel(chan - 1, bool(level)))


def set_text_mark_chan(fhand: int, chan: int, rate: float,
                       max_chars: int) -> int:
    """Create a TextMark channel. sonpy: ``SetTextMarkChannel(chan, rate, nMax)``."""
    return int(_get(fhand).SetTextMarkChannel(
        chan - 1, float(rate), int(max_chars)))


def set_ext_mark_chan(fhand: int, chan: int, rate: float,
                      ext_type: int = 1, rows: int = 1,
                      cols: int = 1, t_div: int = 0) -> int:
    """
    Create an extended marker channel.
    ffi_ceds64.py ``ext_type``: 1=AdcMark(WaveMark), 2=RealMark, 3=TextMark.
    sonpy splits these into separate constructors.
    """
    sonfile = _get(fhand)
    et = int(ext_type)
    if et == 1:      # WaveMark / AdcMark
        return int(sonfile.SetWaveMarkChannel(
            chan - 1, float(rate), int(rows), int(cols), -1, int(t_div)))
    elif et == 2:    # RealMark (single column)
        return int(sonfile.SetRealMarkChannel(
            chan - 1, float(rate), int(rows)))
    elif et == 3:    # TextMark
        return int(sonfile.SetTextMarkChannel(
            chan - 1, float(rate), int(rows)))
    return -1


# -- Waveform read / write ------------------------------------------

def write_wave(fhand: int, chan: int,
               data: np.ndarray, t_from: int) -> int:
    """
    Write waveform data. int16 -> ``WriteInts``; otherwise float32 -> ``WriteFloats``.
    Returns the next write time (ticks) or a negative error code.
    """
    sonfile = _get(fhand)
    if data.dtype == np.int16:
        arr = np.ascontiguousarray(data, dtype=np.int16)
        return int(sonfile.WriteInts(chan - 1, arr, int(t_from)))
    arr = np.ascontiguousarray(data, dtype=np.float32)
    return int(sonfile.WriteFloats(chan - 1, arr, int(t_from)))


def _looks_like_error_array(arr: np.ndarray) -> bool:
    """
    sonpy read functions return 'a single element holding a negative error
    code' on failure (see ReadWave.py's own guard:
    ``if len(WaveData) == 1 and WaveData[0] < 0``). Wave reads in main.py always
    request many samples over a real range, so a length-1 negative result is an
    error rather than genuine data.
    """
    return arr.size == 1 and arr[0] < 0


def read_wave_f(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1, mask: int = -1,
                ) -> Tuple[int, np.ndarray, int]:
    """
    Read waveform data as float32 (scaled to user units by sonpy).
    Returns ``(n_read, float32_array, first_time_ticks)``.

    See ``read_wave_s`` for how gaps are handled (the same applies here).
    """
    sonfile = _get(fhand)
    tupto = _resolve_tupto(sonfile, t_to)
    t_first = int(sonfile.FirstTime(chan - 1, int(t_from), tupto))
    raw = np.asarray(sonfile.ReadFloats(chan - 1, int(n_max), int(t_from), tupto))
    arr = np.ascontiguousarray(raw, dtype=np.float32)
    if _looks_like_error_array(arr):
        return int(arr[0]), np.empty(0, dtype=np.float32), 0
    return arr.size, arr, t_first


def read_wave_s(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1, mask: int = -1,
                ) -> Tuple[int, np.ndarray, int]:
    """
    Read waveform data as raw int16.
    Returns ``(n_read, int16_array, first_time_ticks)``.

    main.py applies ``value * scale/6553.6 + offset`` itself, so we return the
    *unscaled* int16 samples (sonpy ``ReadInts`` does exactly that).

    The first-sample tick:
        The native DLL hands back the tick of the first returned sample;
        sonpy's read does not, so we query it separately with
        ``FirstTime(chan, t_from, t_upto)`` which returns the time of the first
        data point at/after t_from.

    GAPS:
        The native DLL returns samples only up to the next gap/pause, and
        main.py loops on that to build one WaveformSegment per contiguous run.
        sonpy behaves the same way, despite documentation implying a read is
        "passed over" a gap. Verified against sonpy 1.9.12 with Demo1.smr
        (6 paused segments of 1200 samples): a full-channel read returns 1200
        and stops at the first gap, matching the DLL exactly. Both backends
        therefore produce the same segment list, which
        test_backend_parity.py asserts.
    """
    sonfile = _get(fhand)
    tupto = _resolve_tupto(sonfile, t_to)
    t_first = int(sonfile.FirstTime(chan - 1, int(t_from), tupto))
    raw = np.asarray(sonfile.ReadInts(chan - 1, int(n_max), int(t_from), tupto))
    arr = np.ascontiguousarray(raw, dtype=np.int16)
    if _looks_like_error_array(arr):
        return int(arr[0]), np.empty(0, dtype=np.int16), 0
    return arr.size, arr, t_first


# -- Event read / write ---------------------------------------------

def write_events(fhand: int, chan: int, times: np.ndarray) -> int:
    """Write event times (int64 ticks). Returns 0 on success."""
    arr = np.ascontiguousarray(times, dtype=np.int64)
    return int(_get(fhand).WriteEvents(chan - 1, arr))


def read_events(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1, mask: int = -1,
                ) -> Tuple[int, np.ndarray]:
    """
    Read event times. Returns ``(n_read, int64_array)``.
    sonpy: ``ReadEvents(chan, nMax, tFrom, tUpto, Filter)`` -> vector<int64>.
    """
    sonfile = _get(fhand)
    tupto = _resolve_tupto(sonfile, t_to)
    raw = np.asarray(sonfile.ReadEvents(chan - 1, int(n_max), int(t_from), tupto))
    arr = np.ascontiguousarray(raw, dtype=np.int64)
    if arr.size == 1 and arr[0] < 0:          # error sentinel
        return int(arr[0]), np.empty(0, dtype=np.int64)
    return arr.size, arr


# -- Level (EventBoth) read / write ---------------------------------

def write_levels(fhand: int, chan: int, times: np.ndarray) -> int:
    """
    Write level-toggle times to an EventBoth channel.
    sonpy has no separate WriteLevels; an EventBoth channel's toggles are just
    events, so we use WriteEvents.
    """
    arr = np.ascontiguousarray(times, dtype=np.int64)
    return int(_get(fhand).WriteEvents(chan - 1, arr))


def read_levels(fhand: int, chan: int, n_max: int, t_from: int,
                t_to: int = -1) -> Tuple[int, np.ndarray, int]:
    """
    Read level/toggle times from an EventBoth channel.
    Returns ``(n_read, int64_times, initial_level)``.

    The native ``S64ReadLevels`` reports the transition times *and* the initial
    level (the level in force just before the first returned transition).
    sonpy exposes ``SetInitialLevel`` but no getter, so we recover the level a
    different way: reading the channel with ``ReadMarkers`` yields a DigMark per
    transition whose ``Code1`` holds the level the signal switches *to*
    (0=low, 1=high). The initial level is therefore the opposite of the first
    transition's resulting level, i.e. ``1 - marks[0].Code1``. The transition
    ticks (``Tick``) are identical to what ``ReadEvents`` returns.

    If the channel has no transitions in range we fall back to ``initial_level
    = 0`` (there is nothing to invert and no level to report).
    """
    sonfile = _get(fhand)
    tupto = _resolve_tupto(sonfile, t_to)
    marks = sonfile.ReadMarkers(chan - 1, int(n_max), int(t_from), tupto)
    marks = list(marks) if marks is not None else []

    # Error form: a single marker whose tick is a negative error code.
    if len(marks) == 1:
        try:
            if int(marks[0].Tick) < 0:
                return int(marks[0].Tick), np.empty(0, dtype=np.int64), 0
        except AttributeError:
            pass

    times = np.array([int(m.Tick) for m in marks], dtype=np.int64)
    if times.size:
        initial_level = 1 - (int(marks[0].Code1) & 1)
    else:
        initial_level = 0
    return times.size, times, initial_level


# -- Marker read / write --------------------------------------------

# VERIFY: DigMark's Python attribute names. The struct's data members are not
# expanded in the sonpy man pages, but its *constructor* params are nTick,
# nCode1..nCode4 (SonPy.pdf), and the binding convention exposes them as the
# attributes below. Confirm with `dir(some_DigMark)` on a live install.
def _digmark_fields(m) -> Tuple[int, int, int, int, int]:
    """(tick, code1, code2, code3, code4) from a sonpy DigMark."""
    return (
        int(m.Tick),
        int(m.Code1),
        int(m.Code2),
        int(m.Code3),
        int(m.Code4),
    )


def write_markers(fhand: int, chan: int, markers: List[CEDMarker]) -> int:
    """Write a list of CEDMarker to a marker channel."""
    sonfile = _get(fhand)
    son_marks = [sp.DigMark(int(mk.time), int(mk.code1), int(mk.code2),
                            int(mk.code3), int(mk.code4)) for mk in markers]
    return int(sonfile.WriteMarkers(chan - 1, son_marks))


def read_markers(fhand: int, chan: int, n_max: int, t_from: int,
                 t_to: int = -1, mask: int = -1,
                 ) -> Tuple[int, List[CEDMarker]]:
    """
    Read markers. Returns ``(n_read, list_of_CEDMarker)``.
    sonpy: ``ReadMarkers(chan, nMax, tFrom, tUpto, Filter)`` -> list<DigMark>.
    """
    sonfile = _get(fhand)
    tupto = _resolve_tupto(sonfile, t_to)
    result = sonfile.ReadMarkers(chan - 1, int(n_max), int(t_from), tupto)

    marks = list(result) if result is not None else []
    # Error form: a single marker whose tick is a negative error code.
    if len(marks) == 1:
        try:
            if int(marks[0].Tick) < 0:
                return int(marks[0].Tick), []
        except AttributeError:
            pass

    out: List[CEDMarker] = []
    for m in marks:
        t, c1, c2, c3, c4 = _digmark_fields(m)
        out.append(CEDMarker(time=t, code1=c1, code2=c2, code3=c3, code4=c4))
    return len(out), out


# -- Extended marker read / write -----------------------------------

def read_ext_marks(
    fhand: int,
    chan: int,
    n_max: int,
    t_from: int,
    t_to: int = -1,
    mask: int = -1,
) -> Tuple[int, List[CEDExtMark]]:
    """
    Read extended markers from a WaveMark (AdcMark), RealMark or TextMark
    channel. Returns ``(n_read, list_of_extended_markers)``.

    sonpy dispatches on type:
        AdcMark  -> ReadWaveMarks -> WaveMarker(.Data: list[list[short]], .GetMark())
        RealMark -> ReadRealMarks -> RealMarker(.Data: list[float],       .GetMark())
        TextMark -> ReadTextMarks -> TextMarker(.Text / .GetString(),     .GetMark())
    """
    sonfile = _get(fhand)
    tupto = _resolve_tupto(sonfile, t_to)
    ct = chan_type(fhand, chan)
    pre, rows, cols = get_ext_mark_info(fhand, chan)

    results: list = []

    # sonpy 1.9.12 reality (verified against a live install):
    #   * The per-marker objects are RealMarker / WaveMarker / TextMarker.
    #   * They expose the timestamp and codes directly as ``.Tick`` and
    #     ``.Code1``..``.Code4`` (NOT via a ``.GetMark()`` accessor, which does
    #     not exist), so we read those fields with ``_digmark_fields``.
    #   * TextMarker exposes its string via ``.GetString()``.
    #   * RealMarker / WaveMarker print their numeric payload in ``repr`` but
    #     expose **no** Python attribute for it (no ``.Data`` / ``GetData``),
    #     and trying to index / buffer-protocol the object crashes the
    #     interpreter. So the sample/real payload cannot currently be recovered
    #     through the sonpy backend: ``data`` is returned empty and the caller
    #     should treat that as "payload unavailable on this backend".
    #     # LIMITATION: RealMark/WaveMark sample data via sonpy 1.9.12.

    def _is_error_sentinel(seq) -> bool:
        return len(seq) == 1 and int(seq[0].Tick) < 0

    if ct == ChanType.ADC_MARK:
        raw = sonfile.ReadWaveMarks(chan - 1, int(n_max), int(t_from), tupto) or []
        if _is_error_sentinel(raw):
            return int(raw[0].Tick), []
        for wm in raw:
            t, c1, c2, c3, c4 = _digmark_fields(wm)
            data = np.empty((0, 0), dtype=np.int16)  # see LIMITATION above
            results.append(CEDWaveMark(time=t, code1=c1, code2=c2,
                                       code3=c3, code4=c4, data=data))

    elif ct == ChanType.REAL_MARK:
        raw = sonfile.ReadRealMarks(chan - 1, int(n_max), int(t_from), tupto) or []
        if _is_error_sentinel(raw):
            return int(raw[0].Tick), []
        for rm in raw:
            t, c1, c2, c3, c4 = _digmark_fields(rm)
            data = np.empty((0, 0), dtype=np.float32)  # see LIMITATION above
            results.append(CEDRealMark(time=t, code1=c1, code2=c2,
                                       code3=c3, code4=c4, data=data))

    elif ct == ChanType.TEXT_MARK:
        raw = sonfile.ReadTextMarks(chan - 1, int(n_max), int(t_from), tupto) or []
        if _is_error_sentinel(raw):
            return int(raw[0].Tick), []
        for tm in raw:
            t, c1, c2, c3, c4 = _digmark_fields(tm)
            text = tm.GetString()
            results.append(CEDTextMark(time=t, code1=c1, code2=c2,
                                       code3=c3, code4=c4, data=str(text)))
    else:
        return -1, []

    return len(results), results


# ---------------------------------------------------------------------------
# Backend selection lives in main.py (_get_backend / read_file's `backend`
# argument), not here. Nothing needs to import this module directly.
# ---------------------------------------------------------------------------
