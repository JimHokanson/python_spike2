# spike2io — Spike2 Files in Python

A Python wrapper for loading [Spike2](https://ced.co.uk/products/spike2) `.smr` / `.smrx` files. It wraps the low-level CED DLL (`ceds64int.dll`) to provide a clean, Pythonic interface on top of the two available APIs:

- **`ced`** — high-level, object-oriented interface (recommended for most users)
- **`ceds64`** — low-level DLL wrapper with direct access to CED primitives

> **Note:** This library currently relies on drivers from [spike2matson](https://ced.co.uk/upgrades/spike2matson), a Windows-only MATLAB library provided by CED. **Windows only.**

Work on this code was supported by a grant from the NIH NIDDK ([grant: R21DK140694](https://reporter.nih.gov/project-details/11232104)).

---

## Why this library?

CED provides an official Python package, [sonpy](https://pypi.org/project/sonpy/), but it has several limitations:

- Limited Python version support
- Broken behavior on Windows (may be addressed in future releases)
- Poor data retrieval on macOS (returns lists instead of NumPy arrays)

`spike2io` addresses these issues while supporting Python 3.9+ on Windows.

---

## Installation

```bash
pip install spike2io
```

**Requirements:**

- Windows (64-bit)
- Python >= 3.9
- NumPy

---

## Example Files

A repository of example `.smr` / `.smrx` files is available for testing:

<https://github.com/JimHokanson/spike2_example_files>

---

## Usage — High-Level API (`ced`)

The `ced` module is the recommended interface. It reads a file and exposes its channels as typed Python objects.

### Basic: Read a file

```python
import ced

f = ced.read_file("my_recording.smr")
```

---

### Waveform (ADC) channels

Waveform channels hold continuous analog signals (e.g. pressure, EMG, voltage).

```python
import ced
from matplotlib import pyplot as plt

f = ced.read_file("demo1.smr")

# Access the first waveform channel (not necessarily channel index 1)
w = f.waveforms[0]

print(w.name)   # channel title, e.g. "Pressure"
print(w.units)  # physical units, e.g. "cmH2O"

# get_data() returns a list of segments (one per recording gap/pause)
segments = w.get_data()

plt.figure()
for seg in segments:
    seg.plot()          # convenience method: plots seg.time vs seg.data
plt.ylabel(f"{w.name} ({w.units})")
plt.xlabel("Time (s)")
plt.show()
```

If the recording has no gaps, `segments` will contain exactly one element. Each segment object has:

| Attribute | Description |
|-----------|-------------|
| `seg.time` | NumPy array of sample times (seconds) |
| `seg.data` | NumPy array of sample values (physical units) |

---

### Event channels

Spike2 distinguishes between rising-edge, falling-edge, and both-edge event channels.

```python
import ced

f = ced.read_file("Demo_Jim.smrx")

# Rising-edge events
rise_ch = f.event_rises[0]
rise_data = rise_ch.get_data()
rise_data.plot()   # plots event times as tick marks

# Falling-edge events
fall_ch = f.event_falls[0]
fall_data = fall_ch.get_data()
fall_data.plot()

# Both-edge events (rise AND fall captured)
both_ch = f.event_both[0]
both_data = both_ch.get_data()
both_data.plot()
```

#### Event data return formats

JAH Note: This may be incorrect ...

`get_data()` on an event channel accepts an optional `return_format` argument:

```python
# Default: raw transition times + starting level
data = both_ch.get_data(return_format='times')

# (x, y) arrays with one point per transition — includes starting point
data = both_ch.get_data(return_format='time_series1')

# (x, y) arrays with doubled points for a clean square-wave plot
data = both_ch.get_data(return_format='time_series2')
plt.plot(data.x, data.y)

# Separate rise_times and fall_times arrays
data = both_ch.get_data(return_format='switch_times')
print(data.rise_times)
print(data.fall_times)

# Paired (start, stop) intervals for high and low periods
data = both_ch.get_data(return_format='starts_and_stops')
```

---

### Listing all channels

```python
import ced

f = ced.read_file("my_recording.smrx")

print("Waveform channels :", len(f.waveforms))
print("Event-rise channels:", len(f.event_rises))
print("Event-fall channels:", len(f.event_falls))
print("Event-both channels:", len(f.event_both))

for w in f.waveforms:
    print(f"  {w.name}  ({w.units})")
```

---

### Closing a file explicitly

Files are closed automatically, but you can close them manually if needed (e.g. in a loop over many files):

```python
import ced

f = ced.read_file("my_recording.smr")
# ... work with f ...
f.close()
```

### Vertical cursor timing

TODO

---

JAH Note: Things beyond here were automatically created and I have not verified them.

## Usage — Low-Level API (`ceds64`)

The `ceds64` module gives direct access to the CED DLL. Use this if you need fine-grained control over channels, time bases, or want to create/write files.

### Reading back waveform and event data

```python
import ceds64
import numpy as np

ceds64.load_lib()

fhand = ceds64.open("my_recording.smrx")

# --- Channel metadata ---
n_chans = ceds64.max_channels(fhand)
for ch in range(1, n_chans + 1):
    ct = ceds64.chan_type(fhand, ch)
    if ct == ceds64.ChanType.OFF:
        continue
    print(f"Ch {ch}: {ct.name}  title='{ceds64.chan_title(fhand, ch)}'  "
          f"units='{ceds64.chan_units(fhand, ch)}'")

# --- Read waveform samples (int16) ---
n_read, data_i16, t_first = ceds64.read_wave_s(fhand, chan=1, n_max=5000, t_from=0)
print(f"Read {n_read} samples, first tick={t_first}")

# --- Read waveform samples (float, scaled to physical units) ---
n_read, data_f, t_first = ceds64.read_wave_f(fhand, chan=1, n_max=5000, t_from=0)
print(data_f[:10])

# --- Read events ---
n_ev, ev_times = ceds64.read_events(fhand, chan=2, n_max=1000, t_from=0)
tb = ceds64.time_base(fhand)
for i, t in enumerate(ev_times):
    print(f"  Event {i}: {t} ticks = {t * tb:.4f} s")

ceds64.close(fhand)
```

---

### Creating a new file and writing data

```python
import ceds64
import numpy as np
import tempfile, os

ceds64.load_lib()

# Create a temporary .smrx file
tmp = tempfile.NamedTemporaryFile(suffix=".smrx", delete=False)
tmp.close()
fp = tmp.name

TIME_BASE   = 1e-6        # 1 µs per tick
SAMPLE_RATE = 1000.0      # 1 kHz
TICK_INTERVAL = int(1.0 / (SAMPLE_RATE * TIME_BASE))
N_SAMPLES   = 5000        # 5 seconds

fhand = ceds64.create(fp, n_chans=32, file_type=2)
ceds64.time_base(fhand, TIME_BASE)

# --- Waveform channel ---
ceds64.set_wave_chan(fhand, 1, TICK_INTERVAL, chan_type_code=1, rate=SAMPLE_RATE)
ceds64.chan_title(fhand, 1, "Pressure")
ceds64.chan_units(fhand, 1, "cmH2O")
ceds64.chan_scale(fhand, 1, 1.0)
ceds64.chan_offset(fhand, 1, 0.0)

t = np.arange(N_SAMPLES) / SAMPLE_RATE
sine = (np.sin(2 * np.pi * 5.0 * t) * 3000).astype(np.int16)
next_tick = ceds64.write_wave(fhand, 1, sine, 0)
print(f"Wrote waveform, next write tick: {next_tick}")

# --- Event channel ---
ceds64.set_event_chan(fhand, 2, rate=10.0, event_type=3)   # EventRise
ceds64.chan_title(fhand, 2, "Triggers")

event_ticks = np.array([int(i / TIME_BASE) for i in range(1, 6)], dtype=np.int64)
ceds64.write_events(fhand, 2, event_ticks)
print(f"Wrote {len(event_ticks)} events")

ceds64.close(fhand)
print(f"File saved to: {fp}")
```

---

### File info helpers

```python
import ceds64

ceds64.load_lib()
fhand = ceds64.open("my_recording.smrx")

print("Version   :", ceds64.version(fhand))
print("Max chans :", ceds64.max_channels(fhand))
print("Max time  :", ceds64.max_time(fhand), "ticks")
print("File size :", ceds64.file_size(fhand), "bytes")
print("Time base :", ceds64.time_base(fhand), "s/tick")
print("Open files:", ceds64.file_count())

ceds64.close(fhand)
```

---

## Relationship to the MATLAB library

This package is the Python counterpart of [matlab_spike2](https://github.com/NeuralDataFormats/matlab_spike2). The high-level `ced` API mirrors the MATLAB interface:

| MATLAB | Python |
|--------|--------|
| `file = ced.file(path)` | `f = ced.read_file(path)` |
| `w = file.waveforms(1)` | `w = f.waveforms[0]` |
| `d = w.getData()` | `data = w.get_data()` |
| `plot(d(i).time, d(i).data)` | `seg.plot()` |

---

## Known Limitations

- **Windows only** — the underlying CED DLL is Windows-specific.
- The `sonpy` dependency issues described above are tracked; once resolved, a cross-platform backend may be added.
- There are currently limited error checks on low-level DLL return codes.

---

## License

MIT — see [LICENSE](LICENSE) for details.
