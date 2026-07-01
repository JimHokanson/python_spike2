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
import math
import os
import errno
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
from .son_types import CEDWaveMark, CEDRealMark, CEDTextMark
from .s2rx import S2rxFile


ffi1_found = False
if platform.system() == "Windows":
    #TODO: Check version of Python
    from . import ffi as ffi_ceds64
    ffi1_found = True
else:
    ffi_ceds64 = None

ffi2_found = False
if importlib.util.find_spec("sonpy") is not None:
    from . import ffi_sonpy
    ffi2_found = True
else:
    ffi_sonpy = None

if not ffi1_found and not ffi2_found:
    #TODO: Provide more details
    #Windows - you should be good to go - local libraries
    #Mac
    raise Exception('Spike2 interface library not found')



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


def read_file(file_path: StrPath, backend: Literal["ceds64", "sonpy"] = "ceds64") -> "File":
    """
    Preferred entry point for working with this module.
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

    def __init__(self, file_path: StrPath, open_mode: int = 1, backend: Literal["ceds64", "sonpy"] = "ceds64") -> None:
        """
        
        Parameters
        ----------
        open_mode :
            1  = read-only
            0  = read/write
            -1 = try r/w then r-o.
        
        """

        if backend == "ceds64":
            if ffi_ceds64 is None:
                raise ImportError("The 'ceds64' backend is not available.")
            self.ffi = ffi_ceds64

        elif backend == "sonpy":
            if ffi_sonpy is None:
                raise ImportError("The 'sonpy' backend is not available.")
            self.ffi = ffi_sonpy

        else:
            raise ValueError(
                f"Unsupported backend {backend!r}. "
                "Expected 'ceds64' or 'sonpy'."
            )
        
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
    
            if chan_type == CT.ADC:
                t = ADC(self.fhand, i, self)
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
        """Close the underlying SON file."""
        if self.fhand is not None:
            self.ffi.close(self.fhand)
            self.fhand = None

    """
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
    """
    
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
                    import warnings
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

        self.n_ticks: int = self.ffi.chan_max_time(fhand, chan_id)
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
        0-based index of the first sample in this segment.
    last_sample : int
        0-based index of the last sample in this segment.
    start_time : float
        Time in seconds of the first sample.
    n_samples : int
        Number of samples in this segment.
    time : np.ndarray or None
        Time array (seconds or datetime64) if requested, else None.
    """
    data: np.ndarray
    first_sample: int
    last_sample: int
    start_time: float
    n_samples: int
    time: Optional[np.ndarray] = None
    
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
    Waveform (Adc) channel.

    Parameters
    ----------
    fhand : int
        DLL file handle.
    chan_id : int
        1-based channel number.
    parent : File
    """

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)
        self.n_ticks = math.ceil(parent.n_ticks / self.chan_div)


        """
        # Work out tick range
        if time_range is not None:
            s1 = int(time_range[0] * self.fs)
            s2 = int(time_range[1] * self.fs)
        elif sample_range is not None:
            s1 = sample_range[0]
            s2 = sample_range[1]
        else:
            s1 = 0
            s2 = self.n_ticks - 1

        n_samples = s2 - s1 + 1

        # Convert samples → ticks
        s1_ticks = s1 * self.chan_div
        s2_ticks = s2 * self.chan_div + 1  # +1: request is non-inclusive

        if read_scaled:
            n_read, data, start_tick = self.ffi.read_wave_f(
                self.fhand, self.chan_id, n_samples, s1_ticks, s2_ticks)
        else:
            n_read, data, start_tick = self.ffi.read_wave_s(
                self.fhand, self.chan_id, n_samples, s1_ticks, s2_ticks)

        start_sample = int(start_tick / self.chan_div)
        start_time = start_sample / self.fs

        return n_read, data, start_sample, start_time
        """
    
    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 sample_range: Optional[tuple[int, int]] = None,
                 return_format: str = 'double',
                 time_format: str = 'numeric') -> list["WaveformSegment"]:
            """
            Read waveform data, automatically handling gaps/pauses.
     
            Parameters
            ----------
            time_range : (float, float), optional
                Start and end time in seconds.
            sample_range : (int, int), optional
                Start and end sample (1-based, inclusive — matches MATLAB).
            return_format : str, default 'double'
                - 'int16'
                - 'single' or 'float32'
                - 'double' or 'float64'.
            time_format : str, default 'numeric'
                'none'     — no time array returned.
                'numeric'  — time in seconds (float64).
                'datetime' — absolute datetime if file has a valid start
                             datetime, otherwise seconds as float.
     
            Returns
            -------
            list of WaveformSegment
                One segment per contiguous block.  A file with no gaps
                returns a single-element list.
            """
     
            n_samples = self.n_ticks
     
            # ----------------------------------------------------------
            # Resolve sample range (0-based, inclusive)
            # ----------------------------------------------------------
            if time_range is not None:
                s1 = round(time_range[0] * self.fs)
                if s1 < 0:
                    raise ValueError('Invalid time range: t1 too early')
                # -1 because the DLL end is non-inclusive
                s2 = round(time_range[1] * self.fs) - 1
                if s2 >= self.n_ticks:
                    raise ValueError('Invalid time range: t2 too late')
                if s1 > s2:
                    raise ValueError('Invalid time range: t1 > t2')
     
            elif sample_range is not None:
                # Input is 1-based inclusive, convert to 0-based
                s1 = sample_range[0] - 1
                s2 = sample_range[1] - 1
                if s1 < 0:
                    raise ValueError('Invalid sample range: s1 too early')
                if s2 >= self.n_ticks:
                    raise ValueError('Invalid sample range: s2 too late')
                if s1 > s2:
                    raise ValueError('Invalid sample range: s1 > s2')
            else:
                s1 = 0
                s2 = n_samples - 1
     
            # ----------------------------------------------------------
            # Read loop — handles gaps/pauses
            # ----------------------------------------------------------
            # Waveforms can have pauses. The DLL returns data only up to
            # the next gap. If our start falls in a gap it advances to
            # the next sample.  We loop until all requested data has
            # been retrieved.
            # ----------------------------------------------------------
            segments = []
     
            while True:
                seg = self._read_segment(s1, s2, n_samples,
                                         return_format, time_format)
                if seg.n_samples == 0:
                    break
     
                segments.append(seg)
                s1 = seg.last_sample + 1
                if s1 > s2:
                    break
     
            return segments
     
    # ------------------------------------------------------------------
    # Private helper — single contiguous read
    # ------------------------------------------------------------------
    def _read_segment(self, s1: int, s2: int, n_samples: int,
                      return_format: str, time_format: str) -> "WaveformSegment":
        """
        One call to the DLL.  Returns data up to the next gap (or end).
        """
        # Convert samples → ticks
        s1_ticks = s1 * self.chan_div
        s2_ticks = s2 * self.chan_div + 1  # +1: DLL end is non-inclusive
 
        #print(f"  >> read_wave_s(fhand={self.fhand}, chan={self.chan_id}, "
        #  f"n_samples={n_samples}, s1_ticks={s1_ticks}, s2_ticks={s2_ticks})",
        #  flush=True)
 
        n_read, data, start_tick = self.ffi.read_wave_s(
            self.fhand, self.chan_id, n_samples, s1_ticks, s2_ticks)
        
        
        #print(f"  << read_wave_s returned n_read={n_read}, "
        #f"start_tick={start_tick}, data.shape={data.shape}",
        #flush=True)
 
        if n_read <= 0:
            return WaveformSegment(
                data=np.empty(0),
                first_sample=0,
                last_sample=0,
                start_time=0.0,
                n_samples=0,
            )
 
        #We want round up behavior so thus the -(-a//b) hack
        first_sample = -int(-start_tick // self.chan_div) + 1
        last_sample = first_sample + n_read - 1
        start_time = first_sample / self.fs
 
        # ----------------------------------------------------------
        # Data conversion
        # user_value = int16_value * (scale / 6553.6) + offset
        # ----------------------------------------------------------
        if return_format == 'int16':
            pass  # keep as-is
        elif return_format in ('single', 'float32'):
            data = data.astype(np.float32) * (self.scale / 6553.6) \
                   + self.chan_offset
        else:  # 'double' / 'float64'
            data = data.astype(np.float64) * (self.scale / 6553.6) \
                   + self.chan_offset
 
        # ----------------------------------------------------------
        # Time array
        # ----------------------------------------------------------
        if time_format == 'none':
            time = None
        else:
            sample_indices = np.arange(first_sample,
                                       first_sample + n_read)
            time_secs = sample_indices / self.fs
 
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
                  max_events: int = 1_000_000) -> "EventTimesResult":
        """
        Read event times from the channel.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds. Default is entire channel.
        time_format : str, default 'numeric'
            'numeric'  — times in seconds as float64.
            'datetime' — absolute datetime if file has a valid start
                         datetime, otherwise seconds.
        max_events : int, default 1_000_000
            Maximum number of events to read.

        Returns
        -------
        EventTimesResult
        """
        if time_range is None:
            time_range = (0.0, self.max_time)

        # Convert seconds → ticks
        t1 = round(time_range[0] * self.fs)
        t2 = round(time_range[1] * self.fs)

        if t1 < 0:
            raise ValueError('Invalid time range: t1 too early')
        if t2 > self.n_ticks:
            raise ValueError('Invalid time range: t2 too late')

        # +1 because DLL end is non-inclusive
        t2 = t2 + 1

        n_read, raw_times = self.ffi.read_events(
            self.fhand, self.chan_id, max_events, t1, t2)

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

        return EventTimesResult(times=times, n_events=n_read)

    # Keep get_data as an alias for backward compat
    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 time_format: str = 'numeric',
                 max_events: int = 1_000_000) -> "EventTimesResult":
        """Alias for get_times(), kept for backward compatibility."""
        return self.get_times(time_range=time_range,
                              time_format=time_format,
                              max_events=max_events)

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
                  max_events: int = 1_000_000) -> "LevelTimesResult":
        """
        Read level/toggle data from the channel.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds. Default is entire channel.
        max_events : int, default 1_000_000
            Maximum number of events to read.

        Returns
        -------
        LevelTimesResult
        
        """
        if time_range is None:
            time_range = (0.0, self.max_time)
            start_time = 0
            end_time = self.parent.n_seconds
        else:
            start_time = time_range[0]
            end_time = time_range[1]

        t1 = round(time_range[0] * self.fs)
        t2 = round(time_range[1] * self.fs)

        file_time = self.parent.n_seconds
        last_file_sample = round(file_time * self.fs)

        if t1 < 0:
            raise ValueError('Invalid time range: t1 too early')
        if t2 > self.n_ticks:
            if t2 > last_file_sample:
                raise ValueError('Invalid time range: t2 too late')
            else:
                t2 = self.n_ticks

        # +1: DLL end is non-inclusive
        t2 = t2 + 1

        n_read, raw_times, start_level = self.ffi.read_levels(
            self.fhand, self.chan_id, max_events, t1, t2)

        start_level = int(start_level)

        if n_read < 0:
            raise RuntimeError(f'Error reading levels, code {n_read}')

        # Convert ticks → seconds
        times = raw_times.astype(np.float64) / self.fs
        n_events = len(times)

        hit_event_max = (n_events >= max_events)

        return LevelTimesResult(
            times=times,
            start_level=start_level,
            n_events=n_events,
            hit_event_max=hit_event_max,
            start_time=start_time,
            stop_time=end_time)


    # Keep get_data as an alias
    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 max_events: int = 1_000_000) -> "LevelTimesResult":
        """Alias for get_times(), kept for backward compatibility."""
        return self.get_times(time_range=time_range, max_events=max_events)

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
                 max_events: int = 1_000_000,
                 to_char: Optional[bool] = None) -> "MarkerResult":
        """
        Read marker data from the channel.

        Parameters
        ----------
        time_range : (float, float), optional
            Start and end time in seconds. Default is entire channel.
        max_events : int, default 1_000_000
            Maximum number of markers to read.
        to_char : bool, optional
            Convert code bytes to characters. Defaults to True if the
            channel name is 'Keyboard', False otherwise.


        Improvements
        ------------
        1. This implementation allocates at 1 million events which is most
        likely overkill. The MATLAB version starts at 1000 then grows as more
        comes in to eventually get to 1 million.

        Returns
        -------
        MarkerResult
        """
                
        if to_char is None:
            to_char = (self.name == "Keyboard")

        if time_range is None:
            time_range = (0.0, self.max_time)

        t1 = round(time_range[0] * self.fs)
        t2 = round(time_range[1] * self.fs)

        if t1 < 0:
            raise ValueError('Invalid time range: t1 too early')
        if t2 > self.n_ticks:
            raise ValueError('Invalid time range: t2 too late')

        # +1: DLL end is non-inclusive
        t2 = t2 + 1

        n_read, markers = self.ffi.read_markers(
            self.fhand, self.chan_id, max_events, t1, t2)

        if n_read < 0:
            raise RuntimeError(f'Error reading markers, code {n_read}')

        if n_read == 0:
            return MarkerResult(
                times=np.empty(0),
                c1=np.empty(0), c2=np.empty(0),
                c3=np.empty(0), c4=np.empty(0),
                n_events=0,
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
            n_events=n_read,
        )
    
    def __repr__(self) -> str:
        return utils.print_object(self)


class WaveMark(Channel):

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 max_events: int = 1_000_000) -> tuple[int, list[CEDWaveMark]]:
        """
        Read wavemarks (AdcMark extended markers).

        Returns
        -------
        n_read : int
        markers : list of CEDWaveMark
        """
        if time_range is not None:
            t_from = self.ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = self.ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return self.ffi.read_ext_marks(
            self.fhand, self.chan_id, max_events, t_from, t_to)


class RealMark(Channel):

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 max_events: int = 1_000_000) -> tuple[int, list[CEDRealMark]]:
        """
        Read real markers (RealMark extended markers).

        Returns
        -------
        n_read : int
        markers : list of CEDRealMark
        """
        if time_range is not None:
            t_from = self.ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = self.ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return self.ffi.read_ext_marks(
            self.fhand, self.chan_id, max_events, t_from, t_to)


class TextMark(Channel):

    def __init__(self, fhand: int, chan_id: int, parent: "File") -> None:
        super().__init__(fhand, chan_id, parent)

        # TextMark uses the file time base directly for fs
        self.fs = 1.0 / parent.time_base
        self.max_time = self.n_ticks / self.fs

    def get_data(self, time_range: Optional[tuple[float, float]] = None,
                 max_events: int = 1_000_000) -> tuple[int, list[CEDTextMark]]:
        """
        Read text markers.

        Parameters
        ----------
        time_range : (float, float), optional
            Time range in seconds. Defaults to entire channel.
        max_events : int
            Maximum number of markers to read.

        Returns
        -------
        n_read : int
        markers : list of CEDTextMark
        """
        if time_range is not None:
            t_from = self.ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = self.ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return self.ffi.read_ext_marks(
            self.fhand, self.chan_id, max_events, t_from, t_to)