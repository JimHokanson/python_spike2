# Starter type stub for the `ffi` module.
#
# Signatures here were INFERRED from how each function is called in main.py,
# not from the actual ffi implementation. Anything marked "TODO: verify"
# should be checked against the real C-DLL wrapper (return types, integer
# widths, and error-code conventions in particular).
#
# Drop this next to ffi.py (same directory, same base name). A .pyi takes
# precedence over the .py for type checking only; it has no runtime effect.

import os
from enum import IntEnum
from typing import Any

import numpy as np

StrPath = str | os.PathLike[str]


# ----------------------------------------------------------------------
# Channel type enum
# ----------------------------------------------------------------------
class ChanType(IntEnum):
    OFF: int          # TODO: verify the integer values match the DLL
    ADC: int
    EVENT_FALL: int
    EVENT_RISE: int
    EVENT_BOTH: int
    MARKER: int
    ADC_MARK: int
    REAL_MARK: int
    TEXT_MARK: int


# ----------------------------------------------------------------------
# Extended-marker record types (returned by read_markers / read_ext_marks)
# ----------------------------------------------------------------------
class CEDMarker:
    """Plain marker record (read_markers)."""
    time: int         # tick timestamp; main.py divides by fs to get seconds
    code1: int
    code2: int
    code3: int
    code4: int

class CEDWaveMark:   # TODO: fill in real fields
    ...

class CEDRealMark:   # TODO: fill in real fields
    ...

class CEDTextMark:   # TODO: fill in real fields
    ...


# ----------------------------------------------------------------------
# File-level functions
# ----------------------------------------------------------------------
def open(file_path: StrPath, mode: int = ...) -> int: ...
def close(fhand: int) -> None: ...
def version(fhand: int) -> int: ...
def app_id(fhand: int) -> tuple[Any, ...]: ...          # TODO: verify element types
def file_size(fhand: int) -> int: ...
def file_comment(fhand: int, index: int) -> str: ...
def max_time(fhand: int) -> int: ...                    # TODO: verify int vs float (main.py wraps in float())
def time_date(fhand: int) -> tuple[int, int, int, int, int, int]: ...  # TODO: verify length/order (sec..year)
def time_base(fhand: int) -> float: ...
def max_channels(fhand: int) -> int: ...
def secs_to_ticks(fhand: int, secs: float) -> int: ...


# ----------------------------------------------------------------------
# Per-channel metadata
# ----------------------------------------------------------------------
def chan_type(fhand: int, chan_id: int) -> ChanType: ...
def chan_max_time(fhand: int, chan_id: int) -> int: ...
def chan_title(fhand: int, chan_id: int) -> str: ...
def chan_units(fhand: int, chan_id: int) -> str: ...
def chan_comment(fhand: int, chan_id: int) -> str: ...
def chan_divide(fhand: int, chan_id: int) -> int: ...
def chan_offset(fhand: int, chan_id: int) -> float: ...
def chan_scale(fhand: int, chan_id: int) -> float: ...
def chan_y_range(fhand: int, chan_id: int) -> tuple[float, float]: ...
def ideal_rate(fhand: int, chan_id: int) -> float: ...


# ----------------------------------------------------------------------
# Data readers
# Each returns n_read first (negative on error), then payload(s).
# ----------------------------------------------------------------------
def read_wave_s(
    fhand: int, chan_id: int, n_samples: int, t1: int, t2: int
) -> tuple[int, np.ndarray, int]: ...   # n_read, data (int16), start_tick

def read_wave_f(
    fhand: int, chan_id: int, n_samples: int, t1: int, t2: int
) -> tuple[int, np.ndarray, int]: ...   # n_read, data (float), start_tick

def read_events(
    fhand: int, chan_id: int, max_events: int, t1: int, t2: int
) -> tuple[int, np.ndarray]: ...        # n_read, raw_times (ticks)

def read_levels(
    fhand: int, chan_id: int, max_events: int, t1: int, t2: int
) -> tuple[int, np.ndarray, int]: ...   # n_read, raw_times, start_level

def read_markers(
    fhand: int, chan_id: int, max_events: int, t1: int, t2: int
) -> tuple[int, list[CEDMarker]]: ...    # n_read, markers

def read_ext_marks(
    fhand: int, chan_id: int, max_events: int, t_from: int, t_to: int
) -> tuple[int, list[Any]]: ...          # n_read, markers; list[Any] so each
                                         # caller can narrow to its own record
