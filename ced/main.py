# -*- coding: utf-8 -*-
"""
Created on Sat May 23 07:06:27 2026

@author: Jim
"""

# Standard
import math
from dataclasses import dataclass
from datetime import datetime

# Third Party
import numpy as np

#Local
#--------------------------
from . import utils
from . import ffi



try:
    from matplotlib import pyplot as plt
except ImportError:
    plt = None


def read_file(file_path):
    """
    Preferred entry point for working with this module.
    """
    return File(file_path)


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

    def __init__(self, file_path):
        
        self.fhand = ffi.open(file_path, mode=1)
        if self.fhand < 0:
            raise RuntimeError(
                f"Failed to open '{file_path}', error code {self.fhand}")
    
        #print("[2] version...",flush=True)
        self.version = ffi.version(self.fhand)
        #print(f"    {self.version}",flush=True)
    
        #print("[3] app_id...",flush=True)
        self.app_id = ffi.app_id(self.fhand)
        #print(f"    {self.app_id}",flush=True)
        

        #print("[4] file_size...",flush=True)
        self.file_size = ffi.file_size(self.fhand)
        #print(f"    {self.file_size}",flush=True)
    
        #print("[5] file_comments...",flush=True)
        comments = []
        for i in range(1, 9):
            #print(f"    comment {i}...",flush=True)
            next_comment = ffi.file_comment(self.fhand, i)
            if next_comment:
                comments.append(next_comment)
        self.comments = comments
        #print(f"    {self.comments}",flush=True)

        #print("[6] max_time...",flush=True)
        self.n_ticks = float(ffi.max_time(self.fhand))
        #print(f"    {self.n_ticks}",flush=True)
    
        #print("[7] time_date...",flush=True)
        temp = ffi.time_date(self.fhand)
        #print(f"    {temp}",flush=True)
        if all(x == 0 for x in temp):
            self.start_datetime = None
        else:
            self.start_datetime = datetime(*reversed(temp))
        #print(f"    {self.start_datetime}",flush=True)
    
        #print("[8] time_base...")
        self.time_base = ffi.time_base(self.fhand)
        #print(f"    {self.time_base}")
    
        self.n_seconds = self.n_ticks * self.time_base
        #print(f"    n_seconds = {self.n_seconds}")
    
        #print("[9] max_channels...")
        n_chans_max = ffi.max_channels(self.fhand)
        #print(f"    {n_chans_max}")

        
    
        CT = ffi.ChanType
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
            chan_type = ffi.chan_type(self.fhand, i)
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

    def close(self):
        """Close the underlying SON file."""
        if self.fhand is not None:
            ffi.close(self.fhand)
            self.fhand = None

    """
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
    """
    
    def get_channels(self, names, case_sensitive=False, 
                     partial_match='anywhere', missing='error'):
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
            names = [names]
    
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
    
        return results

    def __repr__(self):
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

    def __init__(self, fhand, chan_id, parent):
        self.fhand = fhand
        self.chan_id = chan_id
        self.parent = parent

        self.n_ticks = ffi.chan_max_time(fhand, chan_id)
        self.name = ffi.chan_title(fhand, chan_id)
        self.units = ffi.chan_units(fhand, chan_id).strip()
        self.comment = ffi.chan_comment(fhand, chan_id)

        self.chan_div = ffi.chan_divide(fhand, chan_id)
        time_base = parent.time_base

        # SampleRateInHz = 1.0 / (chan_div * time_base)
        self.fs = 1.0 / (self.chan_div * time_base)

        self.max_time = parent.n_seconds

        self.chan_offset = ffi.chan_offset(fhand, chan_id)
        self.scale = ffi.chan_scale(fhand, chan_id)

        y1, y2 = ffi.chan_y_range(fhand, chan_id)
        self.y_range = [y1, y2]

    def __repr__(self):
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
    time: object = None
    
    def plot(self):
        if plt is None:
            raise ImportError(
                "matplotlib is required for plotting. "
                "Install it with: pip install matplotlib"
            )
            
        if self.time is None:
            plt.plot(self.data)
        else:
            plt.plot(self.time,self.data)
    
    def __repr__(self):
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

    def __init__(self, fhand, chan_id, parent):
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
            n_read, data, start_tick = ffi.read_wave_f(
                self.fhand, self.chan_id, n_samples, s1_ticks, s2_ticks)
        else:
            n_read, data, start_tick = ffi.read_wave_s(
                self.fhand, self.chan_id, n_samples, s1_ticks, s2_ticks)

        start_sample = int(start_tick / self.chan_div)
        start_time = start_sample / self.fs

        return n_read, data, start_sample, start_time
        """
    
    def get_data(self, time_range=None, sample_range=None,
                     return_format='double', time_format='numeric'):
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
    def _read_segment(self, s1, s2, n_samples, return_format, time_format):
        """
        One call to the DLL.  Returns data up to the next gap (or end).
        """
        # Convert samples → ticks
        s1_ticks = s1 * self.chan_div
        s2_ticks = s2 * self.chan_div + 1  # +1: DLL end is non-inclusive
 
        #print(f"  >> read_wave_s(fhand={self.fhand}, chan={self.chan_id}, "
        #  f"n_samples={n_samples}, s1_ticks={s1_ticks}, s2_ticks={s2_ticks})",
        #  flush=True)
 
        n_read, data, start_tick = ffi.read_wave_s(
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


class EventRiseOrFall(Channel):

    def __init__(self, fhand, chan_id, parent, is_rise):
        super().__init__(fhand, chan_id, parent)
        self.is_rise = is_rise

    def get_data(self, time_range=None, max_events=1_000_000):
        """
        Read event times.

        Returns
        -------
        n_read : int
        times : np.ndarray (int64, ticks)
        """

        
        """
            arguments
                obj ced.channel.adc
                in.n_init (1,1) {mustBeNumeric} = 1e4
                in.growth_rate (1,1) {mustBeNumeric} = 2
                in.time_range (:,:) {h__sizeCheck(in.time_range)} = []
                in.sample_range (:,:) {h__sizeCheck(in.sample_range)} = []
                in.time_format {mustBeMember(in.time_format,{'none','numeric','datetime'})} = 'numeric'
                in.return_format {mustBeMember(in.return_format,{'int16','single','double','data_object'})} = 'double'    
            end

            if in.return_format == "data_object" && isempty(which('sci.time_series.data'))
                in.return_format = 'double';
            end

            n_samples = obj.n_ticks;
        """
        
        if time_range is not None:
            t_from = ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return ffi.read_events(
            self.fhand, self.chan_id, max_events, t_from, t_to)


class EventBoth(Channel):

    def __init__(self, fhand, chan_id, parent):
        super().__init__(fhand, chan_id, parent)

    def get_data(self, time_range=None, max_events=1_000_000):        
        
        
        """
        Read level data.

        Returns
        -------
        n_read : int
        times : np.ndarray (int64, ticks)
        level : int
            Level of the first returned point (1=high, 0=low).
        """
        if time_range is not None:
            t_from = ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return ffi.read_levels(
            self.fhand, self.chan_id, max_events, t_from, t_to)


class Marker(Channel):

    def __init__(self, fhand, chan_id, parent):
        super().__init__(fhand, chan_id, parent)

    def get_data(self, time_range=None, max_events=1_000_000):
        """
        Read markers.

        Returns
        -------
        n_read : int
        markers : list of ffi.CEDMarker
        """
        if time_range is not None:
            t_from = ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return ffi.read_markers(
            self.fhand, self.chan_id, max_events, t_from, t_to)


class WaveMark(Channel):

    def __init__(self, fhand, chan_id, parent):
        super().__init__(fhand, chan_id, parent)

    def get_data(self, time_range=None, max_events=1_000_000):
        """
        Read wavemarks (AdcMark extended markers).

        Returns
        -------
        n_read : int
        markers : list of ffi.CEDWaveMark
        """
        if time_range is not None:
            t_from = ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return ffi.read_ext_marks(
            self.fhand, self.chan_id, max_events, t_from, t_to)


class RealMark(Channel):

    def __init__(self, fhand, chan_id, parent):
        super().__init__(fhand, chan_id, parent)

    def get_data(self, time_range=None, max_events=1_000_000):
        """
        Read real markers (RealMark extended markers).

        Returns
        -------
        n_read : int
        markers : list of ffi.CEDRealMark
        """
        if time_range is not None:
            t_from = ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return ffi.read_ext_marks(
            self.fhand, self.chan_id, max_events, t_from, t_to)


class TextMark(Channel):

    def __init__(self, fhand, chan_id, parent):
        super().__init__(fhand, chan_id, parent)

        # TextMark uses the file time base directly for fs
        self.fs = 1.0 / parent.time_base
        self.max_time = self.n_ticks / self.fs

    def get_data(self, time_range=None, max_events=1_000_000):
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
        markers : list of ffi.CEDTextMark
        """
        if time_range is not None:
            t_from = ffi.secs_to_ticks(self.fhand, time_range[0])
            t_to = ffi.secs_to_ticks(self.fhand, time_range[1])
        else:
            t_from = 0
            t_to = -1

        return ffi.read_ext_marks(
            self.fhand, self.chan_id, max_events, t_from, t_to)