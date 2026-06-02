"""
test_ceds64.py — Simple test case for the ceds64 Python wrapper.

This script demonstrates creating a new .smrx file, writing waveform
and event data, reading it back, and verifying the results.

Prerequisites
-------------
- Windows with the CED ceds64int.dll available.
- The ceds64 package (ceds64.py + __init__.py) on your Python path.
- numpy installed.

Usage
-----
    python test_ceds64.py --dll-path "C:\\path\\to\\CEDS64ML"

If --dll-path is omitted, the script looks for the DLLs in the ceds64
package directory (i.e. place x64/ next to ceds64.py).
"""

fp = r"C:\Users\Jim\OneDrive - mcw.edu\Robilotto, Gabriella's files - Cystometry files\08272025_Cystometry_Cage 555_1R.smr"


import ced
import os

root = r"C:\repos\data\spike2_example_files\files"


#demo1 - ADC with multiple start/stops and one event rise
#---------------------------------------------------------
fp = os.path.join(root,"demo1.smr")

f = ced.read_file(fp)

w = f.waveforms[0]

data = w.get_data()

from matplotlib import pyplot as plt

plt.cla()
for d in data:
    d.plot()
    
    
s = f.event_rises[0]

data = s.get_data()

#Demo_Jim
#---------------------------------------------------
fp = os.path.join(root,"Demo_Jim.smrx")

f = ced.read_file(fp)

s = f.event_falls[0]
data = s.get_data()
data.plot()

s = f.event_both[0]
data = s.get_data()
data.plot()

"""

        return_format : str, default 'times'
            'times'           — raw transition times + start_level.
            'time_series1'    — (x, y) with one point per transition,
                                includes starting point.
            'time_series2'    — (x, y) with doubled points so that
                                plt.plot(x, y) draws a square wave.
            'switch_times'    — separate rise_times and fall_times.
            'starts_and_stops' — paired start/stop for high and low
                                 periods.

"""









    




#import faulthandler
#faulthandler.enable()

"""
fp = r'E:\repos\data\spike2_example_files\files\demo1.smr'
import ced

for i in range(105):
    print(f"--- run {i} ---",flush=True)
    f = ced.read_file(fp)
    print(f"  opened, fhand={f.fhand}",flush=True)
    f.close()
    print(f"  closed, fhand={f.fhand}",flush=True)
"""








import argparse
import os
import sys
import tempfile

import numpy as np

# ---------------------------------------------------------------------------
# Ensure the package is importable when running this file directly
# ---------------------------------------------------------------------------
#sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ceds64

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SAMPLE_RATE_HZ = 1000.0        # 1 kHz waveform
TIME_BASE = 1e-6               # 1 µs per tick (default for many CED files)
TICK_INTERVAL = int(1.0 / (SAMPLE_RATE_HZ * TIME_BASE))  # ticks per sample
NUM_SAMPLES = 5000             # 5 seconds of data


def main(dll_path: str | None = None):
    # ── 1. Load the DLL ──────────────────────────────────────────────────
    print("[1] Loading CED library...")
    ceds64.load_lib()
    print(f"    Files currently open: {ceds64.file_count()}")

    # ── 2. Create a temporary .smrx file ─────────────────────────────────
    tmp = tempfile.NamedTemporaryFile(suffix=".smrx", delete=False)
    tmp.close()
    filepath = tmp.name
    print(f"\n[2] Creating test file: {filepath}")

    fhand = ceds64.create(filepath, n_chans=32, file_type=2)
    if fhand < 0:
        print(f"    ERROR: create() returned {fhand}")
        return
    print(f"    File handle: {fhand}")

    # Set the time base
    ceds64.time_base(fhand, TIME_BASE)
    tb = ceds64.time_base(fhand)
    print(f"    Time base: {tb:.2e} s/tick")

    # ── 3. Set up a waveform channel (channel 1, Adc / int16) ────────────
    print("\n[3] Creating waveform channel (ch 1, Adc, 1 kHz)...")
    ret = ceds64.set_wave_chan(fhand, 1, TICK_INTERVAL, chan_type_code=1, rate=SAMPLE_RATE_HZ)
    print(f"    set_wave_chan returned: {ret}")
    ceds64.chan_title(fhand, 1, "Sine_1kHz")
    ceds64.chan_units(fhand, 1, "mV")
    ceds64.chan_scale(fhand, 1, 1.0)
    ceds64.chan_offset(fhand, 1, 0.0)

    # ── 4. Write a 5 Hz sine wave ────────────────────────────────────────
    print("\n[4] Writing 5-second sine wave...")
    t = np.arange(NUM_SAMPLES) / SAMPLE_RATE_HZ
    sine_wave = (np.sin(2 * np.pi * 5.0 * t) * 3000).astype(np.int16)  # ~±3000 ADC counts
    next_time = ceds64.write_wave(fhand, 1, sine_wave, 0)
    print(f"    Wrote {NUM_SAMPLES} samples, next write time: {next_time} ticks")

    # ── 5. Set up an event channel (channel 2, EventRise) ────────────────
    print("\n[5] Creating event channel (ch 2, EventRise)...")
    ret = ceds64.set_event_chan(fhand, 2, rate=10.0, event_type=3)
    print(f"    set_event_chan returned: {ret}")
    ceds64.chan_title(fhand, 2, "Triggers")

    # Write 10 events, one per second
    event_times = np.array([int(i / TIME_BASE) for i in range(1, 6)], dtype=np.int64)
    ret = ceds64.write_events(fhand, 2, event_times)
    print(f"    Wrote {len(event_times)} events, return: {ret}")

    # ── 6. Query file/channel info ───────────────────────────────────────
    print("\n[6] Querying file info...")
    print(f"    Version:      {ceds64.version(fhand)}")
    print(f"    Max channels: {ceds64.max_channels(fhand)}")
    print(f"    Max time:     {ceds64.max_time(fhand)} ticks")
    print(f"    File size:    {ceds64.file_size(fhand)} bytes")

    print("\n    Channel info:")
    for ch in range(1, 4):
        ct = ceds64.chan_type(fhand, ch)
        if ct == ceds64.ChanType.OFF:
            continue
        title = ceds64.chan_title(fhand, ch)
        units = ceds64.chan_units(fhand, ch)
        print(f"      Ch {ch}: type={ct.name}, title='{title}', units='{units}'")

    # ── 7. Read waveform data back ───────────────────────────────────────
    print("\n[7] Reading waveform data back (first 20 samples)...")
    n_read, data, t_first = ceds64.read_wave_s(fhand, 1, n_max=20, t_from=0)
    print(f"    Read {n_read} samples, first time: {t_first} ticks")
    print(f"    Data (int16): {data}")

    # Also read as float
    n_read_f, data_f, t_first_f = ceds64.read_wave_f(fhand, 1, n_max=20, t_from=0)
    print(f"    Data (float): {data_f[:10]}...")

    # ── 8. Read events back ──────────────────────────────────────────────
    print("\n[8] Reading events back...")
    n_ev, ev_times = ceds64.read_events(fhand, 2, n_max=100, t_from=0)
    print(f"    Read {n_ev} events")
    for i, et in enumerate(ev_times):
        print(f"      Event {i}: {et} ticks = {ceds64.ticks_to_secs(fhand, et):.4f} s")

    # ── 9. Verify round-trip ─────────────────────────────────────────────
    print("\n[9] Verification...")
    match_wave = np.array_equal(data, sine_wave[:n_read])
    match_events = np.array_equal(ev_times, event_times)
    print(f"    Waveform round-trip OK: {match_wave}")
    print(f"    Events round-trip OK:   {match_events}")

    # ── 10. Clean up ─────────────────────────────────────────────────────
    print("\n[10] Closing file...")
    ceds64.close(fhand)
    print(f"     Files still open: {ceds64.file_count()}")

    # Optionally remove temp file
    # os.unlink(filepath)
    print(f"\n     Test file kept at: {filepath}")
    print("\nAll done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the ceds64 Python wrapper.")
    parser.add_argument(
        "--dll-path",
        default=None,
        help="Path to the CEDS64ML directory containing x64/ and x86/ subdirectories.",
    )
    args = parser.parse_args()
    main(args.dll_path)
