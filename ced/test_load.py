# -*- coding: utf-8 -*-
"""
Created on Fri May 22 21:25:25 2026

@author: Jim
"""

import ceds64
import numpy as np

fp = r"C:\Users\Jim\OneDrive - mcw.edu\Robilotto, Gabriella's files - Cystometry files\08272025_Cystometry_Cage 555_1R.smr"

ceds64.load_lib()

fhand = ceds64.open(fp)

print("\n[6] Querying file info...")
print(f"    Version:      {ceds64.version(fhand)}")
print(f"    Max channels: {ceds64.max_channels(fhand)}")
print(f"    Max time:     {ceds64.max_time(fhand)} ticks")
print(f"    File size:    {ceds64.file_size(fhand)} bytes")

print("\n    Channel info:")
for ch in range(1, 32):
    ct = ceds64.chan_type(fhand, ch)
    if ct == ceds64.ChanType.OFF:
        continue
    title = ceds64.chan_title(fhand, ch)
    units = ceds64.chan_units(fhand, ch)
    print(f"      Ch {ch}: type={ct.name}, title='{title}', units='{units}'")

# ── 7. Read waveform data back ───────────────────────────────────────
print("\n[7] Reading waveform data back (first 20 samples)...")
n_read, data, t_first = ceds64.read_wave_s(fhand, 1, n_max=10000, t_from=0)
print(f"    Read {n_read} samples, first time: {t_first} ticks")
print(f"    Data (int16): {data}")

# Also read as float
n_read_f, data_f, t_first_f = ceds64.read_wave_f(fhand, 1, n_max=1000, t_from=0)
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