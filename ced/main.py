# -*- coding: utf-8 -*-
"""
Created on Sat May 23 07:06:27 2026

@author: Jim


Status
------
ADC - done (need to verify timing)
Marker - done
EventBoth - needs to be tested
EventRiseOrFall - needs to be tested

WaveMark - not done
RealMark - not done
TextMark - not done

s2rx parsing - implemented, needs to be tested

PyPi - 

"""

from __future__ import annotations

# Standard
#------------------------------
import os
import sys
import errno
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Optional, Union
import platform
import importlib.util

# Third Party
#------------------------------
import numpy as np

#Local
#--------------------------
from . import utils
from .son_types import CEDExtMark
from .s2rx import S2rxFile


# Backend discovery
#------------------------------
# Both backends are optional and neither is allowed to take the package down
# with it: a backend that cannot be imported is recorded here and the reason
# is only raised if the user actually asks for that backend. See
# _get_backend(). This matters because 'sonpy' ships interpreter-specific
# binaries, so the package is regularly importable-but-broken, and because the
# bundled _ceds64_cffi extension only exists for the Python versions we ship a
# .pyd for.
_BACKEND_ERRORS: dict[str, str] = {}
_BACKEND_EXC: dict[str, BaseException] = {}

ffi_ceds64 = None
if platform.system() != "Windows":
    _BACKEND_ERRORS["ceds64"] = (
        f"not supported on {platform.system()} (the CED DLL is Windows-only)")
else:
    try:
        from . import ffi_ceds64
    except Exception as exc:
        _BACKEND_ERRORS["ceds64"] = (
            f"failed to load ({exc}).\n"
            f"    Two common causes:\n"
            f"      * CED's DLLs need the Microsoft Visual C++ 2012 "
            f"Redistributable (x64). Install it from "
            f"https://www.microsoft.com/en-us/download/details.aspx?id=30679\n"
            f"      * No compiled extension is shipped for Python "
            f"{sys.version_info[0]}.{sys.version_info[1]} on this platform.")
        _BACKEND_EXC["ceds64"] = exc

ffi_sonpy = None
if importlib.util.find_spec("sonpy") is None:
    _BACKEND_ERRORS["sonpy"] = "the 'sonpy' package is not installed"
else:
    try:
        from . import ffi_sonpy
    except Exception as exc:
        # ffi_sonpy already raises a descriptive ImportError, so don't
        # editorialise on top of it -- just pass it through.
        _BACKEND_ERRORS["sonpy"] = f"failed to load ({exc})"
        _BACKEND_EXC["sonpy"] = exc

_BACKENDS = {"ceds64": ffi_ceds64, "sonpy": ffi_sonpy}

if all(mod is None for mod in _BACKENDS.values()):
    raise ImportError(
        "No Spike2 interface backend is available.\n"
        + "\n".join(f"  - {name}: {why}"
                    for name, why in _BACKEND_ERRORS.items())
        + "\nOn Windows this package bundles its own driver; otherwise "
          "install CED's cross-platform package with `pip install sonpy`.")


# How many items to ask for on the first read of an event/marker channel,
# and how fast to grow that request. See _read_all().
_INITIAL_ITEM_READ = 1024
_ITEM_READ_GROWTH = 8


def _resolve_over_range(policy: str, message: str, clamped):
    """
    Apply an out_of_range policy to a request that reaches past the
    available data. Returns the clamped bound when the caller chose to
    continue rather than raise.
    """
    if policy == 'error':
        raise ValueError(message)
    if policy == 'warning':
        warnings.warn(f'{message} - clamped.')
    elif policy != 'clamp':
        raise ValueError(
            f"Unsupported out_of_range {policy!r}. "
            "Expected 'error', 'warning' or 'clamp'.")
    return clamped


def _read_all(read_fn, max_items: Optional[int]):
    """
    Read every item in a range, growing the request until the backend
    stops filling it.

    The SON API wants the buffer size up front and offers no way to ask
    how many items a time range holds, so the only way to be sure nothing
    was left behind is to keep asking for more until it returns fewer
    items than it was offered. The MATLAB library grows the same way.

    Parameters
    ----------
    read_fn : callable
        Takes a buffer size and returns the backend's read tuple, whose
        first element is the number of items read (negative on error).
    max_items : int or None
        Upper bound on items to return, or None for no bound.

    Returns
    -------
    (result, hit_max)
        ``result`` is read_fn's tuple; ``hit_max`` is True only when
        max_items was supplied and reached, i.e. data may be missing.
    """
    capacity = _INITIAL_ITEM_READ
    if max_items is not None:
        capacity = min(capacity, max_items)

    while True:
        result = read_fn(capacity)
        n_read = result[0]

        if n_read < 0:                 # backend error; let the caller see it
            return result, False
        if n_read < capacity:          # buffer was not filled -> that's all
            return result, False
        if max_items is not None and capacity >= max_items:
            return result, True        # stopped because the cap was reached

        capacity *= _ITEM_READ_GROWTH
        if max_items is not None:
            capacity = min(capacity, max_items)


def _get_backend(backend: Optional[str]):
    """
    Resolve a backend name to its module.

    ``backend=None`` picks the first backend that loaded, preferring
    'ceds64' -- it splits waveforms at recording gaps and can return
    WaveMark/RealMark payloads, neither of which 'sonpy' does.
    """
    if backend is None:
        for mod in _BACKENDS.values():
            if mod is not None:
                return mod
        # Unreachable: the import above raises when nothing is available.
        raise ImportError("No Spike2 interface backend is available.")

    if backend not in _BACKENDS:
        raise ValueError(
            f"Unsupported backend {backend!r}. "
            "Expected 'ceds64' or 'sonpy'.")

    mod = _BACKENDS[backend]
    if mod is None:
        raise ImportError(
            f"The {backend!r} backend is unavailable: "
            f"{_BACKEND_ERRORS[backend]}") from _BACKEND_EXC.get(backend)
    return mod



try:
    from matplotlib import pyplot as plt
except ImportError:
    plt = None

if TYPE_CHECKING:
    # Imported for type checking only so matplotlib stays an optional
    # runtime dependency.
    from matplotlib.axes import Axes

# A filesystem path accepted throughout the public API.
StrPath = Union[str, os.PathLike[str]]


def read_file(file_path: StrPath,
              backend: Optional[Literal["ceds64", "sonpy"]] = None) -> "File":
    """
    Preferred entry point for working with this module.

    Parameters
    ----------
    backend : 'ceds64' | 'sonpy' | None
        Which low-level driver to read through. The default (None) uses
        the first one available, preferring 'ceds64'.
    """
    return File(file_path,backend=backend)


class File():
    """
    Attributes
    ----------
    fhand : int
        Integer file handle used by the DLL.
    version : int
    app_id : tuple
    file_size : int
    comments : list of str
    start_datetime : datetime or None
    time_base : float
    n_ticks : float
    n_seconds : float
    """

    def __init__(self, file_path: StrPath, open_mode: int = 1,
                 backend: Optional[Literal["ceds64", "sonpy"]] = None) -> None:
        """

        Parameters
        ----------
        open_mode :
            1  = read-only
            0  = read/write
            -1 = try r/w then r-o.
        backend :
            'ceds64', 'sonpy', or None to use the first one available
            (preferring 'ceds64').

        """

        self.ffi = _get_backend(backend)

        #Path verification
        #-----------------------------------------------
        if not os.path.exists(file_path):
            #This may occur if the file is not raw on Windows and is being
            #escaped
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_path)
            
            
        root, full_filename = os.path.split(file_path)
        name_no_ext, file_ext = os.path.splitext(full_filename)
        
        if file_ext == ".s2rx":
            # ASSUMPTION: Assuming smr is the only valid option?
            # No - smrx is also an option
            file_path = os.path.join(root, name_no_ext + ".smrx")
            if not os.path.isfile(file_path):
                file_path = os.path.join(root, name_no_ext + ".smr")
                if not os.path.isfile(file_path):
                    raise FileNotFoundError("s2rx file is not a valid SON file")
                
        s2rx_path = os.path.join(root, name_no_ext + ".s2rx")
        if os.path.isfile(s2rx_path):
            self.meta_file = S2rxFile(s2rx_path)
        else:
            self.meta_file = None
        
        self.fhand = self.ffi.open(file_path, mode=open_mode)
        if self.fhand < 0:
            file_path2 = repr(str(file_path))
            raise RuntimeError(
                f"Failed to open '{file_path2}', error code {self.fhand}")
    
        #print("[2] version...",flush=True)
        self.version = self.ffi.version(self.fhand)
        #print(f"    {self.version}",flush=True)
    
        #print("[3] app_id...",flush=True)
        self.app_id = self.ffi.app_id(self.fhand)
        #print(f"    {self.app_id}",flush=True)
        

        #print("[4] file_size...",flush=True)
        self.file_size = self.ffi.file_size(self.fhand)
        #print(f"    {self.file_size}",flush=True)
    
        #print("[5] file_comments...",flush=True)
        comments = []
        for i in range(1, 9):
            #print(f"    comment {i}...",flush=True)
            next_comment = self.ffi.file_comment(self.fhand, i)
            if next_comment:
                comments.append(next_comment)
        self.comments = comments
        #print(f"    {self.comments}",flush=True)

        #print("[6] max_time...",flush=True)
        self.n_ticks = float(self.ffi.max_time(self.fhand))
        #print(f"    {self.n_ticks}",flush=True)
    
        #print("[7] time_date...",flush=True)
        temp = self.ffi.time_date(self.fhand)
        #print(f"    {temp}",flush=True)
        if all(x == 0 for x in temp):
            self.start_datetime = None
        else:
            # self.ffi.time_date returns a fixed 7-element tuple in the order
            # (hundredths, seconds, minutes, hours, day, month, year). Index
            # explicitly into it to build datetime(year, month, day, hour,
            # minute, second); the sub-second "hundredths" field (temp[0]) is
            # dropped. (datetime() rejects an unpacked variable-length
            # iterable, so explicit indexing also stays type-checkable once
            # self.ffi is typed.)
            self.start_datetime = datetime(
                temp[6], temp[5], temp[4], temp[3], temp[2], temp[1])
        #print(f"    {self.start_datetime}",flush=True)
    
        #print("[8] time_base...")
        self.time_base = self.ffi.time_base(self.fhand)
        #print(f"    {self.time_base}")
    
        self.n_seconds = self.n_ticks * self.time_base
        #print(f"    n_seconds = {self.n_seconds}")
    
        #print("[9] max_channels...")
        n_chans_max = self.ffi.max_channels(self.fhand)
        #print(f"    {n_chans_max}")

        
    
        CT = self.ffi.ChanType
        chan_info = []
        chan_info.append(['id', 'idx', 'name', 'type'])
    
        self.waveforms = []
        self.event_falls = []
        self.event_rises = []
        self.event_both = []
        self.markers = []
        self.wave_markers = []
        self.real_markers = []
        self.text_markers = []
        self.all_chan_objects = []
        self.chan_types = []
        self.chan_names = []
    
        #print("[10] channel loop...")
        for i in range(1, n_chans_max + 1):
            #print(f"    chan {i}: chan_type...", end="", flush=True)
            chan_type = self.ffi.chan_type(self.fhand, i)
            #print(f" {chan_type}", flush=True)
    
            if chan_type == CT.OFF:
                continue
    
            if chan_type == CT.ADC or chan_type == CT.REAL_WAVE:
                # Both are waveforms; they differ only in how the samples
                # are stored (scaled int16 vs float32). ADC handles both.
                t = ADC(self.fhand, i, self,
                        is_real_wave=(chan_type == CT.REAL_WAVE))
                self.waveforms.append(t)
                n = len(self.waveforms)
            elif chan_type == CT.EVENT_FALL:
                t = EventRiseOrFall(self.fhand, i, self, is_rise=False)
                self.event_falls.append(t)
                n = len(self.event_falls)
            elif chan_type == CT.EVENT_RISE:
                t = EventRiseOrFall(self.fhand, i, self, is_rise=True)
                self.event_rises.append(t)
                n = len(self.event_rises)
            elif chan_type == CT.EVENT_BOTH:
                t = EventBoth(self.fhand, i, self)
                self.event_both.append(t)
                n = len(self.event_both)
            elif chan_type == CT.MARKER:
                t = Marker(self.fhand, i, self)
                self.markers.append(t)
                n = len(self.markers)
            elif chan_type == CT.ADC_MARK:
                t = WaveMark(self.fhand, i, self)
                self.wave_markers.append(t)
                n = len(self.wave_markers)
            elif chan_type == CT.REAL_MARK:
                t = RealMark(self.fhand, i, self)
                self.real_markers.append(t)
                n = len(self.real_markers)
            elif chan_type == CT.TEXT_MARK:
                t = TextMark(self.fhand, i, self)
                self.text_markers.append(t)
                n = len(self.text_markers)
            else:
                raise ValueError(f'Unexpected channel type: {chan_type}')
    
            chan_info.append([i, n-1, t.name, chan_type])
            self.all_chan_objects.append(t)
            self.chan_types.append(chan_type)
            self.chan_names.append(t.name)
    
        self.chan_info = chan_info

    def close(self) -> None:
        """Close the underlying SON file. Safe to call more than once."""
        if self.fhand is not None:
            self.ffi.close(self.fhand)
            self.fhand = None

    def __enter__(self) -> "File":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # Returning None means exceptions propagate normally.
        self.close()

    # Deliberately no __del__: it would leave releasing a native file
    # handle up to the garbage collector, and at interpreter shutdown the
    # DLL may already be torn down by the time it ran. Use `with` (or
    # close() explicitly) when you need a file released at a known point.


    def get_channels(self, names: Union[str, list[str]], case_sensitive: bool = False,
                     partial_match: Union[str, bool] = 'anywhere',
                     missing: str = 'error') -> Union["Channel", list[Optional["Channel"]]]:
        """
        Retrieve channel objects by name.
    
        Parameters
        ----------
        names : str or list of str
            One or more channel names to search for.
        case_sensitive : bool, default False
            If False, 'EEG' matches 'eeg', 'Eeg', etc.
        partial_match : 'anywhere' | 'start' | False, default 'anywhere'
            'anywhere' - search term may appear anywhere in the name
            'start'    - name must begin with the search term
            False      - full exact match required
        missing : 'error' | 'warning', default 'error'
            Behaviour when a requested channel name is not found.
    
        Returns
        -------
        list
            Channel objects corresponding to each entry in names.
            Unmatched entries are None when missing='warning'.
    
        Examples
        --------
        >>> chans = f.get_channels('EEG')
        >>> chans = f.get_channels(['EEG_01', 'EMG_01'],
        ...                        case_sensitive=True, partial_match=False)
        >>> chans = f.get_channels(['EEG_01', 'BAD'], missing='warning')
        """
        if isinstance(names, str):
            unpack = True
            names = [names]
        else:
            unpack = False
    
        if case_sensitive:
            compare_names = self.chan_names
        else:
            compare_names = [n.lower() for n in self.chan_names]
    
        results = []
        
        for name in names:
            search = name if case_sensitive else name.lower()
    
            match_idx = None
    
            if partial_match == 'anywhere':
                for j, cn in enumerate(compare_names):
                    if search in cn:
                        match_idx = j
                        break
            elif partial_match == 'start':
                for j, cn in enumerate(compare_names):
                    if cn.startswith(search):
                        match_idx = j
                        break
            else:
                for j, cn in enumerate(compare_names):
                    if cn == search:
                        match_idx = j
                        break
    
            if match_idx is None:
                if missing == 'error':
                    raise ValueError(f'No channel found matching "{name}".')
                else:
                    warnings.warn(f'No channel found matching "{name}".')
                    results.append(None)
            else:
                results.append(self.all_chan_objects[match_idx])
    
        if unpack:
            results = results[0]
    
        return results

    def __repr__(self) -> str:
        return utils.print_object(self)


class Channel():
    """
    Base class for all channel types.

    Attributes
    ----------
    fhand : int
        DLL file handle.
    chan_id : int
        1-based channel number.
    parent : File
    n_ticks : int
    name : str
    units : str
    comment : str
    chan_div : int
    fs : float
    max_time : float
    chan_offset : float
    scale : float
    y_range : list
    """

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        self.fhand: int = fhand
        self.chan_id: int = chan_id
        self.parent: "File" = parent
        self.ffi = parent.ffi

        # The DLL reports -1 for a channel that holds no data; a channel
        # spanning no time is clearer as 0 than as a negative duration.
        self.n_ticks: int = max(int(self.ffi.chan_max_time(fhand, chan_id)), 0)
        self.name: str = self.ffi.chan_title(fhand, chan_id)
        self.units: str = self.ffi.chan_units(fhand, chan_id).strip()
        self.comment: str = self.ffi.chan_comment(fhand, chan_id)

        self.chan_div: int = self.ffi.chan_divide(fhand, chan_id)
        time_base: float = parent.time_base

        # SampleRateInHz = 1.0 / (chan_div * time_base)
        self.fs: float
        try:
            self.fs = 1.0 / (self.chan_div * time_base)
        except ZeroDivisionError:
            self.fs = float('nan')

        self.max_time: float = parent.n_seconds

        self.chan_offset = self.ffi.chan_offset(fhand, chan_id)
        self.scale = self.ffi.chan_scale(fhand, chan_id)

        y1, y2 = self.ffi.chan_y_range(fhand, chan_id)
        self.y_range = [y1, y2]

    def _check_open(self) -> None:
        """
        Guard the read methods against a closed file.

        Each channel holds its own copy of the file handle, so once the
        parent File is closed that copy is stale. Catch it here rather
        than handing a dangling handle to the native library.
        """
        if self.parent.fhand is None:
            raise ValueError(
                f"the file for channel {self.name!r} is closed")

    def _resolve_time_range(self, time_range: Optional[tuple[float, float]],
                            out_of_range: str) -> tuple[int, int]:
        """
        Resolve a seconds time_range to a half-open tick range [t1, t2).

        time_range is given in file time, so it is validated against the
        file's duration and then narrowed to this channel's own extent.
        That way asking for the whole file works on a channel that stops
        recording early, which is the common case.

        ``time_range=None`` means the whole channel and never raises.
        """
        if time_range is None:
            t1_secs, t2_secs = 0.0, self.parent.n_seconds
        else:
            t1_secs, t2_secs = time_range
            if t1_secs < 0:
                raise ValueError('Invalid time range: t1 too early')
            if t1_secs > t2_secs:
                raise ValueError('Invalid time range: t1 > t2')
            if t2_secs > self.parent.n_seconds:
                t2_secs = _resolve_over_range(
                    out_of_range,
                    f'Invalid time range: t2 ({t2_secs:g} s) is past the '
                    f'end of the file ({self.parent.n_seconds:g} s)',
                    self.parent.n_seconds)

        time_base = self.parent.time_base
        t1 = int(round(t1_secs / time_base))
        # +1 because the DLL end is non-inclusive
        t2 = int(round(t2_secs / time_base)) + 1

        # Narrow to where this channel actually has data.
        return max(t1, 0), min(t2, self.n_ticks + 1)

    def __repr__(self) -> str:
        return utils.print_object(self)


class Unused():

    def __init__(self):
        self.name = 'unused'


@dataclass
class WaveformSegment:
    """
    One contiguous block of waveform data.
 
    A channel with no gaps produces a single segment.
    Gaps/pauses produce multiple segments.
 
    Attributes
    ----------
    data : np.ndarray
        Waveform samples (int16, float32, or float64 depending on
        return_format).
    first_sample : int
        0-based index of the first sample in this segment, counted on the
        channel's sample grid (see ADC.n_ticks). For a gapped channel the
        indices of later segments therefore skip the paused region.
    last_sample : int
        0-based grid index of the last sample in this segment.
    start_time : float
        Time in seconds of the first sample.
    n_samples : int
        Number of samples in this segment.
    time : np.ndarray or None
        Time array (seconds or datetime64) if requested, else None.
    start_tick : int
        Time in file ticks of the first sample. This is the authoritative
        value; start_time and time are derived from it.
    """
    data: np.ndarray
    first_sample: int
    last_sample: int
    start_time: float
    n_samples: int
    time: Optional[np.ndarray] = None
    start_tick: int = 0

    def plot(self) -> None:
        if plt is None:
            raise ImportError(
                "matplotlib is required for plotting. "
                "Install it with: pip install matplotlib"
            )
            
        if self.time is None:
            plt.plot(self.data)
        else:
            plt.plot(self.time,self.data)
    
    def __repr__(self) -> str:
        return utils.print_object(self)

class ADC(Channel):
    """
    Waveform channel — both Adc (scaled int16) and RealWave (float32).

    Parameters
    ----------
    fhand : int
        DLL file handle.
    chan_id : int
        1-based channel number.
    parent : File
    is_real_wave : bool
        True for a RealWave channel. Its samples are stored as float32
        already in user units, so the scale/offset conversion applied to
        Adc data is skipped and 'int16' is not an available return_format.

    Attributes
    ----------
    first_tick : int
        Tick of the channel's first sample. Samples sit at
        first_tick + k*chan_div.
    n_ticks : int
        Number of sample grid slots spanned. See the note in __init__.
    """

    def __init__(self, fhand: int, chan_id: int, parent: "File",
                 is_real_wave: bool = False) -> None:
        super().__init__(fhand, chan_id, parent)

        self.is_real_wave: bool = is_real_wave

        # Samples sit at ticks first_tick + k*chan_div. A waveform channel
        # does not necessarily start at tick 0: Spike2 staggers the ADC
        # channels across the sampling multiplexer (so they are offset from
        # each other by a few ticks), and a channel can also start well into
        # the recording. Measure the offset rather than assuming it.
        # Segments after a pause stay on this same grid.
        first_tick = self.ffi.chan_first_time(fhand, chan_id)
        if first_tick >= 0:
            self.first_tick: int = int(first_tick)
            self.last_tick: int = int(self.ffi.chan_max_time(fhand, chan_id))
            # Grid slots spanned, NOT samples stored -- a channel with
            # pauses holds fewer samples than this. sample_range indexes
            # against this; for the true count sum the returned segments.
            self.n_ticks = ((self.last_tick - self.first_tick)
                            // self.chan_div) + 1
        else:
            # Channel declared but empty.
            self.first_tick = 0
            self.last_tick = -1
            self.n_ticks = 0


    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 sample_range: Optional[tuple[int, int]] = None,
                 return_format: str = 'double',
                 time_format: str = 'numeric',
                 out_of_range: str = 'error') -> list["WaveformSegment"]:
        """
        Read waveform data, automatically handling gaps/pauses.

        With neither time_range nor sample_range the entire channel is
        returned; that is the intended way to ask for everything, and it
        never raises.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds, measured in file time and
            inclusive of both ends. A start before the channel's first
            sample is fine -- there is simply no data there.
        sample_range : (int, int), optional
            Start and end sample (1-based, inclusive - matches MATLAB),
            indexed against the channel's sample grid (see n_ticks).
        return_format : str, default 'double'
            - 'int16'  (Adc channels only)
            - 'single' or 'float32'
            - 'double' or 'float64'.
        time_format : str, default 'numeric'
            'none'     - no time array returned.
            'numeric'  - time in seconds (float64).
            'datetime' - absolute datetime if file has a valid start
                         datetime, otherwise seconds as float.
        out_of_range : str, default 'error'
            What to do when time_range/sample_range reaches past the end
            of the available data.
            'error'   - raise ValueError.
            'warning' - warn, then return what is available.
            'clamp'   - silently return what is available.

        Returns
        -------
        list of WaveformSegment
            One segment per contiguous block.  A channel with no gaps
            returns a single-element list; an empty channel returns [].
        """

        self._check_open()

        if self.n_ticks == 0:
            return []

        if time_range is not None and sample_range is not None:
            raise ValueError(
                'Specify time_range or sample_range, not both.')

        if self.is_real_wave and return_format == 'int16':
            # Better to say so than to hand back floats from a call that
            # asked for int16.
            raise ValueError(
                f"Channel {self.name!r} is a RealWave channel; its samples "
                "are stored as float32, so return_format='int16' is not "
                "available. Use 'single' or 'double'.")

        tb = self.parent.time_base

        # ----------------------------------------------------------
        # Resolve the request to a half-open tick range [t_from, t_upto)
        # ----------------------------------------------------------
        if time_range is not None:
            t1, t2 = time_range
            if t1 < 0:
                raise ValueError('Invalid time range: t1 too early')
            if t1 > t2:
                raise ValueError('Invalid time range: t1 > t2')
            # time_range is in file time, so it is validated against the
            # file's duration rather than this channel's extent.
            if t2 > self.parent.n_seconds:
                t2 = _resolve_over_range(
                    out_of_range,
                    f'Invalid time range: t2 ({t2:g} s) is past the end of '
                    f'the file ({self.parent.n_seconds:g} s)',
                    self.parent.n_seconds)
            t_from = int(round(t1 / tb))
            t_upto = int(round(t2 / tb)) + 1

        elif sample_range is not None:
            # Input is 1-based inclusive, convert to 0-based
            s1 = sample_range[0] - 1
            s2 = sample_range[1] - 1
            if s1 < 0:
                raise ValueError('Invalid sample range: s1 too early')
            if s1 > s2:
                raise ValueError('Invalid sample range: s1 > s2')
            if s2 > self.n_ticks - 1:
                s2 = _resolve_over_range(
                    out_of_range,
                    f'Invalid sample range: s2 ({sample_range[1]}) is past '
                    f'the end of the channel ({self.n_ticks} samples)',
                    self.n_ticks - 1)
            t_from = self.first_tick + s1 * self.chan_div
            t_upto = self.first_tick + s2 * self.chan_div + 1

        else:
            t_from = self.first_tick
            t_upto = self.last_tick + 1

        # Narrow to where the channel actually holds data. Asking from
        # t=0 for a channel that starts later is legitimate, not an error.
        t_from = max(t_from, self.first_tick)
        t_upto = min(t_upto, self.last_tick + 1)

        # ----------------------------------------------------------
        # Read loop - handles gaps/pauses
        # ----------------------------------------------------------
        # Waveforms can have pauses. The DLL returns data only up to
        # the next gap; if the start falls in a gap it advances to the
        # next sample. Loop until the whole range has been retrieved.
        # ----------------------------------------------------------
        segments = []
        cursor = t_from

        while cursor < t_upto:
            seg = self._read_segment(cursor, t_upto,
                                     return_format, time_format)
            if seg.n_samples == 0:
                break

            segments.append(seg)
            # Advance past the last sample actually returned. Working in
            # ticks (rather than re-deriving a sample index) guarantees
            # forward progress, so a malformed gap cannot loop forever.
            cursor = (seg.start_tick
                      + (seg.n_samples - 1) * self.chan_div + 1)

        return segments

    # ------------------------------------------------------------------
    # Private helper — single contiguous read
    # ------------------------------------------------------------------
    def _read_segment(self, t_from: int, t_upto: int,
                      return_format: str, time_format: str) -> "WaveformSegment":
        """
        One call to the DLL over the half-open tick range [t_from, t_upto).
        Returns data up to the next gap (or the end of the range).
        """
        empty = WaveformSegment(
            data=np.empty(0),
            first_sample=0,
            last_sample=0,
            start_time=0.0,
            n_samples=0,
            start_tick=0,
        )

        # Most samples the range can hold, used to size the read buffer.
        n_max = int((t_upto - 1 - t_from) // self.chan_div) + 1
        if n_max <= 0:
            return empty

        if self.is_real_wave:
            # Stored as float32 already in user units.
            n_read, data, start_tick = self.ffi.read_wave_f(
                self.fhand, self.chan_id, n_max, t_from, t_upto)
        else:
            n_read, data, start_tick = self.ffi.read_wave_s(
                self.fhand, self.chan_id, n_max, t_from, t_upto)

        if n_read <= 0:
            return empty

        start_tick = int(start_tick)
        tb = self.parent.time_base
        # Segments stay on the channel's sample grid, including across a
        # pause, so this division is exact.
        first_sample = (start_tick - self.first_tick) // self.chan_div
        last_sample = first_sample + n_read - 1
        start_time = start_tick * tb

        # ----------------------------------------------------------
        # Data conversion
        # Adc:      user_value = int16_value * (scale / 6553.6) + offset
        # RealWave: samples are already in user units
        # ----------------------------------------------------------
        if self.is_real_wave:
            if return_format in ('single', 'float32'):
                pass  # already float32
            else:  # 'double' / 'float64'
                data = data.astype(np.float64)
        elif return_format == 'int16':
            pass  # keep as-is
        elif return_format in ('single', 'float32'):
            data = data.astype(np.float32) * (self.scale / 6553.6) \
                   + self.chan_offset
        else:  # 'double' / 'float64'
            data = data.astype(np.float64) * (self.scale / 6553.6) \
                   + self.chan_offset

        # ----------------------------------------------------------
        # Time array — derived from ticks, never from a sample index,
        # so a channel that starts off tick 0 stays correctly aligned
        # with the event and marker channels beside it.
        # ----------------------------------------------------------
        if time_format == 'none':
            time = None
        else:
            sample_ticks = (start_tick
                            + np.arange(n_read, dtype=np.int64) * self.chan_div)
            time_secs = sample_ticks * tb

            if time_format == 'datetime':
                start_dt = self.parent.start_datetime
                if start_dt is not None:
                    # Return array of datetime objects via numpy
                    origin = np.datetime64(start_dt, 'us')
                    offsets = (time_secs * 1e6).astype('timedelta64[us]')
                    time = origin + offsets
                else:
                    # No valid start datetime — return seconds
                    time = time_secs
            else:
                # 'numeric' — seconds as float64
                time = time_secs

        return WaveformSegment(
            data=data,
            first_sample=first_sample,
            last_sample=last_sample,
            start_time=start_time,
            n_samples=n_read,
            time=time,
            start_tick=start_tick,
        )


    def __repr__(self) -> str:
        return utils.print_object(self)




"""
Event channel classes — Python equivalents of:
    ced.channel.event_rise_or_fall
    ced.channel.event_both

Drop these into main.py, replacing the existing stub classes.
"""

# ======================================================================
# Return types
# ======================================================================

@dataclass
class EventTimesResult:
    """
    Result from:
        EventRiseOrFall.get_times().
    """
    times: np.ndarray          # event times in seconds
    n_events: int
    hit_event_max: bool = False   # True if a max_events cap truncated the read

    def plot(self, ax: "Axes | None" = None, **kwargs: Any) -> "Axes":
        if plt is None:
            raise ImportError("matplotlib required for plotting")
        if ax is None:
            ax = plt.gca()
        ax.vlines(self.times, 0, 1, **kwargs)
        return ax

    def __repr__(self) -> str:
        return utils.print_object(self)


@dataclass
class LevelTimesResult:
    """
    Result from:
        EventBoth.get_times(return_format='times').
    """
    times: np.ndarray       # transition times in seconds
    start_level: int        # 0=low, 1=high at the start
    n_events: int
    hit_event_max: bool     # True if max_events was reached
    start_time: float 
    stop_time: float
    
    def plot(self, ax: "Axes | None" = None, **kwargs: Any) -> "Axes":
        if plt is None:
            raise ImportError("matplotlib required for plotting")
        if ax is None:
            ax = plt.gca()
            
        #0 - at start level
        #- at end, draw to end time (requires holding on to max time from parent)
        
        #all times have two points
        #- same x
        #- different y
        
        
        #    111111    111111
        #
        #00000    000000    0000000
        #
        #    1    3    5    7
        #    2    4    6    8
        #   
        
        
        
        x = np.empty(self.n_events*2 + 2)
        y = np.empty(self.n_events*2 + 2)
        
        x[0] = self.start_time
        x[1:-1:2] = self.times
        x[2::2] = self.times
        #Fix this - go to end time
        x[-1] = self.stop_time
        
        y[0] = self.start_level
        y[1::4] = self.start_level
        if self.start_level == 0:
            next_level = 1
        else:
            next_level = 0
        y[2::4] = next_level
        y[3::4] = next_level
        y[4::4] = self.start_level
        
        #Where does this end?
        y[-1] = y[-2]
    
        ax.plot(x, y, **kwargs)
        return ax

    def __repr__(self) -> str:
        return utils.print_object(self)


# ======================================================================
# Channel classes
# ======================================================================

class EventRiseOrFall(Channel):
    """
    EventFall or EventRise channel.

    Attributes
    ----------
    type : str
        'rise' or 'fall'
    ideal_rate : float
        Expected sustained maximum event rate (Hz).
    """

    def __init__(self, fhand: int, chan_id: int, parent: "File", is_rise: bool) -> None:
        super().__init__(fhand, chan_id, parent)

        self.fs = 1.0 / parent.time_base
        self.max_time = self.n_ticks / self.fs
        self.type: str = "rise" if is_rise else "fall"
        self.ideal_rate: float = self.ffi.ideal_rate(fhand, chan_id)

    def get_times(self, time_range: Optional[tuple[float, float]] = None,
                  time_format: str = 'numeric',
                  max_events: Optional[int] = None,
                  out_of_range: str = 'error') -> "EventTimesResult":
        """
        Read event times from the channel.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds, in file time. Default is the
            entire channel, which never raises.
        time_format : str, default 'numeric'
            'numeric'  — times in seconds as float64.
            'datetime' — absolute datetime if file has a valid start
                         datetime, otherwise seconds.
        max_events : int, optional
            Cap on the number of events returned. The default (None) reads
            the channel out in full; set this only to bound memory, and
            check ``hit_event_max`` on the result if you do.
        out_of_range : str, default 'error'
            What to do when time_range reaches past the end of the file:
            'error' raises, 'warning' warns then clamps, 'clamp' is silent.

        Returns
        -------
        EventTimesResult
        """
        self._check_open()

        t1, t2 = self._resolve_time_range(time_range, out_of_range)

        (n_read, raw_times), hit_max = _read_all(
            lambda n: self.ffi.read_events(self.fhand, self.chan_id,
                                           n, t1, t2),
            max_events)

        if n_read < 0:
            raise RuntimeError(f'Error reading events, code {n_read}')

        # Convert ticks → seconds
        times = raw_times.astype(np.float64) / self.fs

        if time_format == 'datetime':
            start_dt = self.parent.start_datetime
            if start_dt is not None:
                origin = np.datetime64(start_dt, 'us')
                offsets = (times * 1e6).astype('timedelta64[us]')
                times = origin + offsets
            # else: leave as numeric seconds

        return EventTimesResult(times=times, n_events=n_read,
                                hit_event_max=hit_max)

    # Keep get_data as an alias for backward compat
    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 time_format: str = 'numeric',
                 max_events: Optional[int] = None,
                 out_of_range: str = 'error') -> "EventTimesResult":
        """Alias for get_times(), kept for backward compatibility."""
        return self.get_times(time_range=time_range,
                              time_format=time_format,
                              max_events=max_events,
                              out_of_range=out_of_range)

    def __repr__(self) -> str:
        return utils.print_object(self)

class EventBoth(Channel):
    """
    EventBoth (level / digital) channel.

    The signal starts high or low and toggles at each event time.

    Attributes
    ----------
    ideal_rate : float
        Expected sustained maximum event rate (Hz).
    """

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

        self.fs = 1.0 / parent.time_base
        
        #??? How does this compare to the max time of the parent?
        self.max_time = self.n_ticks / self.fs
        self.ideal_rate: float = self.ffi.ideal_rate(fhand, chan_id)

    def get_times(self, time_range: Optional[tuple[float, float]] = None,
                  max_events: Optional[int] = None,
                  out_of_range: str = 'error') -> "LevelTimesResult":
        """
        Read level/toggle data from the channel.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds, in file time. Default is the
            entire channel, which never raises.
        max_events : int, optional
            Cap on the number of transitions returned. The default (None)
            reads the channel out in full; set this only to bound memory,
            and check ``hit_event_max`` on the result if you do.
        out_of_range : str, default 'error'
            What to do when time_range reaches past the end of the file:
            'error' raises, 'warning' warns then clamps, 'clamp' is silent.

        Returns
        -------
        LevelTimesResult

        """
        self._check_open()

        if time_range is None:
            start_time = 0.0
            end_time = self.parent.n_seconds
        else:
            start_time = time_range[0]
            end_time = time_range[1]

        t1, t2 = self._resolve_time_range(time_range, out_of_range)

        (n_read, raw_times, start_level), hit_max = _read_all(
            lambda n: self.ffi.read_levels(self.fhand, self.chan_id,
                                           n, t1, t2),
            max_events)

        start_level = int(start_level)

        if n_read < 0:
            raise RuntimeError(f'Error reading levels, code {n_read}')

        # Convert ticks → seconds
        times = raw_times.astype(np.float64) / self.fs
        n_events = len(times)

        return LevelTimesResult(
            times=times,
            start_level=start_level,
            n_events=n_events,
            hit_event_max=hit_max,
            start_time=start_time,
            stop_time=end_time)


    # Keep get_data as an alias
    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 max_events: Optional[int] = None,
                 out_of_range: str = 'error') -> "LevelTimesResult":
        """Alias for get_times(), kept for backward compatibility."""
        return self.get_times(time_range=time_range, max_events=max_events,
                              out_of_range=out_of_range)

    def __repr__(self) -> str:
        return utils.print_object(self)

@dataclass
class MarkerResult:
    """
    Result from Marker.get_data().

    Attributes
    ----------
    times : np.ndarray
        Event times in seconds.
    c1, c2, c3, c4 : np.ndarray or list of str
        The four marker code channels. Character arrays if to_char=True.
    n_events : int
    """
    times: np.ndarray
    c1: Union[np.ndarray, list[str]]
    c2: Union[np.ndarray, list[str]]
    c3: Union[np.ndarray, list[str]]
    c4: Union[np.ndarray, list[str]]
    n_events: int
    hit_event_max: bool = False   # True if a max_events cap truncated the read

    def __repr__(self) -> str:
        return utils.print_object(self)

    def plot(self, label_code: Optional[int] = 1, ax: "Axes | None" = None,
             text_offset: float = 0.02, **kwargs: Any) -> "Axes":
        """
        Plot vertical lines at each marker time, optionally labeled.
    
        Parameters
        ----------
        label_code : int or None, default 1
            Which code channel to use as labels (1–4), or None to skip.
        ax : matplotlib Axes, optional
        text_offset : float, default 0.02
            Vertical offset for labels, in axes fraction.
        **kwargs
            Passed to ax.axvline() (e.g. color, linestyle, alpha).
        """
        if plt is None:
            raise ImportError("matplotlib required for plotting")
        if ax is None:
            ax = plt.gca()
    
        kwargs.setdefault('alpha', 0.5)
        kwargs.setdefault('linewidth', 0.8)
    
        codes = {1: self.c1, 2: self.c2, 3: self.c3, 4: self.c4}
        labels = codes.get(label_code) if label_code is not None else None
    
        for i, t in enumerate(self.times):
            ax.axvline(t, **kwargs)
            if labels is not None:
                label = str(labels[i])
                ax.text(t, text_offset, label,
                        transform=ax.get_xaxis_transform(),
                        ha='center', va='bottom', fontsize=8, rotation=90)

        return ax

class Marker(Channel):
    """
    Marker channel (e.g. Keyboard markers).

    Each marker has a 64-bit timestamp and four 8-bit codes.
    """

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

        self.fs = 1.0 / parent.time_base
        self.max_time = self.n_ticks / self.fs

    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 max_events: Optional[int] = None,
                 to_char: Optional[bool] = None,
                 out_of_range: str = 'error') -> "MarkerResult":
        """
        Read marker data from the channel.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds, in file time. Default is the
            entire channel, which never raises.
        max_events : int, optional
            Cap on the number of markers returned. The default (None)
            reads the channel out in full; set this only to bound memory,
            and check ``hit_event_max`` on the result if you do.
        to_char : bool, optional
            Convert code bytes to characters. Defaults to True if the
            channel name is 'Keyboard', False otherwise.
        out_of_range : str, default 'error'
            What to do when time_range reaches past the end of the file:
            'error' raises, 'warning' warns then clamps, 'clamp' is silent.

        Returns
        -------
        MarkerResult
        """

        self._check_open()

        if to_char is None:
            to_char = (self.name == "Keyboard")

        t1, t2 = self._resolve_time_range(time_range, out_of_range)

        (n_read, markers), hit_max = _read_all(
            lambda n: self.ffi.read_markers(self.fhand, self.chan_id,
                                            n, t1, t2),
            max_events)

        if n_read < 0:
            raise RuntimeError(f'Error reading markers, code {n_read}')

        if n_read == 0:
            return MarkerResult(
                times=np.empty(0),
                c1=np.empty(0), c2=np.empty(0),
                c3=np.empty(0), c4=np.empty(0),
                n_events=0,
                hit_event_max=hit_max,
            )

        # Collapse into flat arrays
        times = np.array([m.time for m in markers], dtype=np.float64) / self.fs
        c1 = np.array([m.code1 for m in markers], dtype=np.uint8)
        c2 = np.array([m.code2 for m in markers], dtype=np.uint8)
        c3 = np.array([m.code3 for m in markers], dtype=np.uint8)
        c4 = np.array([m.code4 for m in markers], dtype=np.uint8)

        if to_char:
            c1 = np.array([chr(c) for c in c1])
            c2 = np.array([chr(c) for c in c2])
            c3 = np.array([chr(c) for c in c3])
            c4 = np.array([chr(c) for c in c4])

        return MarkerResult(
            times=times, c1=c1, c2=c2, c3=c3, c4=c4,
            n_events=n_read, hit_event_max=hit_max,
        )
    
    def __repr__(self) -> str:
        return utils.print_object(self)


@dataclass
class ExtMarkResult:
    """
    Result from WaveMark / RealMark / TextMark get_data().

    Attributes
    ----------
    markers : list
        CEDWaveMark, CEDRealMark or CEDTextMark records, depending on the
        channel. Each carries a tick timestamp, four codes, and a payload
        in ``.data`` (int16 snippet, float array, or text).
    n_events : int
        Number of markers returned.
    hit_event_max : bool
        True if a max_events cap truncated the read.
    """
    markers: list[CEDExtMark]
    n_events: int
    hit_event_max: bool = False

    def __repr__(self) -> str:
        return utils.print_object(self)


class ExtMark(Channel):
    """
    Shared behaviour for the extended-marker channels.

    WaveMark (AdcMark), RealMark and TextMark all hold markers with an
    attached payload and differ only in the payload type, so the read
    path is identical for all three.
    """

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

        # Report this channel's own extent rather than the file's, which
        # is what Channel would otherwise leave here.
        self.max_time = self.n_ticks * parent.time_base

    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 max_events: Optional[int] = None,
                 out_of_range: str = 'error') -> "ExtMarkResult":
        """
        Read extended markers from the channel.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds, in file time. Default is the
            entire channel, which never raises.
        max_events : int, optional
            Cap on the number of markers returned. The default (None)
            reads the channel out in full; set this only to bound memory,
            and check ``hit_event_max`` on the result if you do.
        out_of_range : str, default 'error'
            What to do when time_range reaches past the end of the file:
            'error' raises, 'warning' warns then clamps, 'clamp' is silent.

        Returns
        -------
        ExtMarkResult
        """
        self._check_open()

        t_from, t_upto = self._resolve_time_range(time_range, out_of_range)

        (n_read, markers), hit_max = _read_all(
            lambda n: self.ffi.read_ext_marks(self.fhand, self.chan_id,
                                              n, t_from, t_upto),
            max_events)

        if n_read < 0:
            raise RuntimeError(
                f'Error reading extended markers, code {n_read}')

        return ExtMarkResult(markers=markers, n_events=n_read,
                             hit_event_max=hit_max)


class WaveMark(ExtMark):
    """
    AdcMark channel — each marker carries an int16 waveform snippet.

    Note ``fs`` here is the sample rate *within* a snippet (derived from
    chan_div), not the rate at which markers occur.
    """


class RealMark(ExtMark):
    """RealMark channel — each marker carries an array of floats."""

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

        # chan_div is 0 for non-sampled channels in .smrx files, which
        # would leave the inherited fs as nan. These markers are timed on
        # the file clock, so use that.
        self.fs = 1.0 / parent.time_base


class TextMark(ExtMark):
    """TextMark channel — each marker carries a text string."""

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

        # TextMark uses the file time base directly for fs
        self.fs = 1.0 / parent.time_base