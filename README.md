# spike2io — Spike2 Files in Python

A Python library for loading [Spike2](https://ced.co.uk/products/spike2) `.smr` / `.smrx` files. It reads a file and exposes its channels as typed Python objects returning NumPy arrays.

Work on this code was supported by a grant from the NIH NIDDK ([grant: R21DK140694](https://reporter.nih.gov/project-details/11232104)).

---

## Why this library?

CED provides an official Python package, [sonpy](https://pypi.org/project/sonpy/), but on its own it has limitations:

- Narrow platform/version coverage — as of 1.9.12 the macOS and Linux wheels are built for CPython 3.14 only
- Poor data retrieval on macOS (returns lists instead of NumPy arrays)

`spike2io` provides a consistent, NumPy-based interface on top of *two* interchangeable backends, so you get the same API whichever one is available:

| Backend | What it uses | Platforms | Python |
|---------|--------------|-----------|--------|
| `ceds64` | Bundled CFFI extension + CED's SON64 DLLs | Windows x64 | 3.9 – 3.14 |
| `sonpy` | CED's own [sonpy](https://pypi.org/project/sonpy/) package | Windows / macOS / Linux | 3.9 – 3.14 on Windows, **3.14 only** on macOS/Linux |

The `ceds64` backend is bundled — on Windows there is nothing else to install. It is also the default when both are present, because it can return WaveMark/RealMark sample payloads, which sonpy cannot.

---

## Installation

```bash
pip install spike2io
```

**Windows (64-bit)** — the CED libraries ship with the package, so no other Python
dependency is needed. They do require Microsoft's
[Visual C++ 2012 Redistributable (x64)](https://www.microsoft.com/en-us/download/details.aspx?id=30679),
which many systems already have; install it if importing `ced` reports that the
`ceds64` backend failed to load.

**macOS / Linux** — reading goes through CED's `sonpy`, which currently publishes macOS/Linux wheels for CPython 3.14 only:

```bash
pip install spike2io[sonpy]
```

Optional plotting helpers (`.plot()` methods) need matplotlib:

```bash
pip install spike2io[plot]
```

**Requirements:** Python >= 3.9 on Windows, >= 3.14 on macOS/Linux. NumPy.

---

## Example Files

A repository of example `.smr` / `.smrx` files is available for testing:

<https://github.com/JimHokanson/spike2_example_files>

The examples below use files from that repository.

---

## Usage

### Reading a file

```python
import ced

f = ced.read_file("my_recording.smr")
# ... work with f ...
f.close()
```

Files can also be used as context managers, which closes them even if an error is raised:

```python
import ced

with ced.read_file("my_recording.smr") as f:
    w = f.waveforms[0]
    segments = w.get_data()
```

By default the first available backend is used, preferring `ceds64`. Pass `backend=` to force one:

```python
import ced

f = ced.read_file("my_recording.smr", backend="sonpy")
```

If you pass a `.s2rx` resource file, the matching `.smrx` / `.smr` recording is opened instead.

---

### Waveform channels

Waveform channels hold continuous analog signals (e.g. pressure, EMG, voltage). Both Spike2 waveform types appear here — `Adc` (scaled 16-bit) and `RealWave` (32-bit float).

```python
import ced
from matplotlib import pyplot as plt

with ced.read_file("Demo1.smr") as f:
    # First waveform channel (not necessarily channel number 1)
    w = f.waveforms[0]

    print(w.name)    # Data
    print(w.units)   # volt
    print(w.fs)      # 2000.0  — samples per second

    # get_data() returns a list of segments, one per contiguous
    # recording run. Demo1.smr was paused 5 times, so it has 6.
    segments = w.get_data()

    plt.figure()
    for seg in segments:
        seg.plot()          # convenience method: seg.time vs seg.data
    plt.ylabel(f"{w.name} ({w.units})")
    plt.xlabel("Time (s)")
    plt.show()
```

A recording with no pauses returns a single-element list. Each segment has:

| Attribute | Description |
|-----------|-------------|
| `seg.time` | NumPy array of sample times (seconds) |
| `seg.data` | NumPy array of sample values (physical units) |
| `seg.n_samples` | Number of samples in this segment |
| `seg.start_time` | Time in seconds of the first sample |
| `seg.start_tick` | Time in file ticks of the first sample |

Sample times come from the file's own clock, so channels stay aligned with each other and with event times. A channel does not necessarily start at time zero — Spike2 staggers waveform channels across the sampling multiplexer, and a channel can also start well into a recording. `Demo1.smr` above starts at 17.76225 s.

To read part of a channel, give either a time range (seconds, inclusive) or a sample range (1-based, inclusive):

```python
import ced

with ced.read_file("Demo1.smr") as f:
    w = f.waveforms[0]
    segments = w.get_data(time_range=(20.0, 25.0))
    segments = w.get_data(sample_range=(1, 1000))
```

`get_data()` with no arguments returns everything and never raises. A range reaching past the end of the file raises `ValueError`; pass `out_of_range='clamp'` (or `'warning'`) to return what exists instead.

Data is returned as float64 by default. Use `return_format='single'` for float32, or `'int16'` for the raw stored values of an `Adc` channel.

---

### Event channels

Spike2 distinguishes rising-edge, falling-edge, and both-edge (level) event channels. Which lists are populated depends on the file — `Demo_Jim.smrx` has two falling-edge channels and one both-edge channel, and no rising-edge channels.

```python
import ced

with ced.read_file("Demo_Jim.smrx") as f:
    print([c.name for c in f.event_falls])   # ['Stimulus', 'Response']
    print([c.name for c in f.event_both])    # ['Memory']

    fall = f.event_falls[0]
    d = fall.get_data()
    print(d.n_events)      # 752
    print(d.times[:3])     # [0.06286 0.85558 1.97999]  — seconds
    d.plot()               # event times as tick marks
```

Both-edge channels also report the signal level in force before the first transition:

```python
import ced

with ced.read_file("Demo_Jim.smrx") as f:
    both = f.event_both[0]
    d = both.get_data()

    print(d.n_events)      # 752
    print(d.start_level)   # 1  (0 = low, 1 = high)
    print(d.times[:3])     # transition times in seconds
    d.plot()               # square wave
```

`get_data()` accepts the same `time_range` and `out_of_range` arguments as waveform channels. `get_times()` is the same method under a clearer name.

---

### Marker channels

Marker channels carry a timestamp plus four 8-bit codes. The `Keyboard` channel records keys pressed during acquisition, and its codes are decoded to characters automatically.

```python
import ced

with ced.read_file("Demo_Jim.smrx") as f:
    mk = f.markers[0]
    d = mk.get_data()

    print(mk.name)         # Keyboard
    print(d.n_events)      # 38
    print(d.times[:3])     # marker times in seconds
    print("".join(d.c1[:5]))  # thisi

    d.plot()               # vertical lines, labelled with c1
```

Codes are available as `d.c1` through `d.c4`. Pass `to_char=False` to keep them as raw `uint8`.

---

### Listing all channels

```python
import ced

with ced.read_file("my_recording.smrx") as f:
    print("Waveform channels  :", len(f.waveforms))
    print("Event-rise channels:", len(f.event_rises))
    print("Event-fall channels:", len(f.event_falls))
    print("Event-both channels:", len(f.event_both))
    print("Marker channels    :", len(f.markers))

    for w in f.waveforms:
        print(f"  {w.name}  ({w.units})")
```

`f.all_chan_objects` holds every channel in file order, and `f.chan_info` is a table of `[id, index, name, type]` rows.

Channels can also be looked up by name:

```python
import ced

with ced.read_file("my_recording.smrx") as f:
    w = f.get_channels("nerve")                  # partial match, case-insensitive
    chans = f.get_channels(["nerve", "signal"])  # several at once
```

---

### Vertical cursor positions

Spike2 stores cursor positions in a `.s2rx` sidecar file next to the recording. When one is present it is parsed automatically and exposed as `f.meta_file`:

```python
import ced

with ced.read_file("Demo_Jim.smrx") as f:
    print(f.meta_file.get_vertical_cursor_positions())    # [115.68]
    print(f.meta_file.get_horizontal_cursor_positions())  # []
```

Positions are in seconds. A cursor that was never moved has no stored position and is omitted, so a file whose cursors are all untouched returns an empty list. `f.meta_file` is `None` when there is no `.s2rx` file.

---

## Low-Level API

`ced.ffi_ceds64` is a thin wrapper over the CED DLL, and `ced.ffi_sonpy` presents the same function names on top of sonpy. Use these if you need direct access to file, channel and marker primitives. Channel numbers are 1-based and times are in file ticks.

```python
from ced import ffi_ceds64 as ffi

fhand = ffi.open("Demo.smr")

print(ffi.chan_title(fhand, 1))   # Sinewave
print(ffi.chan_units(fhand, 1))   # Volts
print(ffi.chan_type(fhand, 1))    # 1        — ChanType.ADC
print(ffi.time_base(fhand))       # 9.999999999999999e-06  — seconds per tick

# n_read, int16 samples, tick of the first sample
n_read, data, t_first = ffi.read_wave_s(fhand, chan=1, n_max=5000, t_from=0)

ffi.close(fhand)
```

Both modules are documented inline; see their docstrings for the full set of calls. Note they are interchangeable only for reading — `edit_marker`, `write_ext_marks`, `extra_data` and the `mask_*` functions exist in `ffi_ceds64` only.

---

## Relationship to the MATLAB library

This package is the Python counterpart of [matlab_spike2](https://github.com/NeuralDataFormats/matlab_spike2). The high-level API mirrors the MATLAB interface:

| MATLAB | Python |
|--------|--------|
| `file = ced.file(path)` | `f = ced.read_file(path)` |
| `w = file.waveforms(1)` | `w = f.waveforms[0]` |
| `d = w.getData()` | `data = w.get_data()` |
| `plot(d(i).time, d(i).data)` | `seg.plot()` |

---

## Known Limitations

- **WaveMark / RealMark / TextMark** channels are read, but on the `sonpy` backend the numeric sample payload is unavailable — sonpy 1.9.12 exposes no attribute for it, so `.data` comes back empty. Timestamps and codes are correct on both backends.
- **MATLAB's `return_format` options** for both-edge event channels (`'time_series1'`, `'time_series2'`, `'switch_times'`, `'starts_and_stops'`) are not yet ported. Python returns transition times and a starting level, equivalent to MATLAB's default `'times'`.
- **Writing files** is available through the backend modules but is not covered by the high-level API.
- Some example files (`example1.smr`, `example2.smr`) cannot be opened by the bundled `ceds64` backend, which returns error −13. They read correctly with `backend="sonpy"`.
- There are limited error checks on low-level DLL return codes.

---

## License

MIT — see [LICENSE](LICENSE) for details.
