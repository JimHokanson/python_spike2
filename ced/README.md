# ceds64 — Python wrapper for CED's SON64 library

A Python (ctypes) port of the **CEDS64ML** MATLAB interface provided by
Cambridge Electronic Design (CED). It wraps the same native `ceds64int.dll`
to read and write Spike2 `.smr` / `.smrx` files.

## Requirements

- **Windows** (the DLL is Windows-only)
- **Python 3.9+**
- **numpy**
- The `ceds64int.dll`, `son64.dll`, and supporting DLLs from CED's CEDS64ML
  distribution. Place the `x64/` (and/or `x86/`) directory next to `ceds64.py`,
  or pass the path explicitly to `load_lib()`.

## Quick Start

```python
import ceds64

# 1. Load the DLL (point to your CEDS64ML folder)
ceds64.load_lib(r"C:\Tools\CEDS64ML")

# 2. Open a file
fhand = ceds64.open(r"C:\Data\recording.smr")

# 3. Inspect channels
for ch in range(1, ceds64.max_channels(fhand) + 1):
    ct = ceds64.chan_type(fhand, ch)
    if ct != ceds64.ChanType.OFF:
        print(f"Ch {ch}: {ct.name}  '{ceds64.chan_title(fhand, ch)}'")

# 4. Read waveform data
n, data, t0 = ceds64.read_wave_f(fhand, chan=1, n_max=100000, t_from=0)

# 5. Read events
n_ev, times = ceds64.read_events(fhand, chan=2, n_max=10000, t_from=0)

# 6. Close
ceds64.close(fhand)
```

## MATLAB → Python Mapping

| MATLAB Function          | Python Function                 | Notes                                    |
|--------------------------|---------------------------------|------------------------------------------|
| `CEDS64LoadLib(path)`    | `ceds64.load_lib(path)`        | Call once at startup                     |
| `CEDS64Open(f, mode)`    | `ceds64.open(f, mode)`         | Returns int handle                       |
| `CEDS64Close(fh)`        | `ceds64.close(fh)`             |                                          |
| `CEDS64CloseAll()`       | `ceds64.close_all()`           |                                          |
| `CEDS64Create(f,n,t)`    | `ceds64.create(f,n,t)`         |                                          |
| `CEDS64FileCount()`      | `ceds64.file_count()`          |                                          |
| `CEDS64IsOpen(fh)`       | `ceds64.is_open(fh)`           |                                          |
| `CEDS64EmptyFile(fh)`    | `ceds64.empty_file(fh)`        |                                          |
| `CEDS64TimeBase(fh,tb)`  | `ceds64.time_base(fh,tb)`      | Get/set; pass `tb` to set               |
| `CEDS64MaxTime(fh)`      | `ceds64.max_time(fh)`          |                                          |
| `CEDS64MaxChan(fh)`      | `ceds64.max_channels(fh)`      |                                          |
| `CEDS64FileSize(fh)`     | `ceds64.file_size(fh)`         |                                          |
| `CEDS64Version(fh)`      | `ceds64.version(fh)`           |                                          |
| `CEDS64SecsToTicks(fh,s)`| `ceds64.secs_to_ticks(fh,s)`   |                                          |
| `CEDS64TicksToSecs(fh,t)`| `ceds64.ticks_to_secs(fh,t)`   |                                          |
| `CEDS64GetFreeChan(fh)`  | `ceds64.get_free_chan(fh)`      |                                          |
| `CEDS64FileComment(...)`  | `ceds64.file_comment(...)`     | Get/set                                 |
| `CEDS64TimeDate(fh)`     | `ceds64.time_date(fh)`         | Returns tuple                            |
| `CEDS64AppID(fh)`        | `ceds64.app_id(fh)`            | Returns tuple                            |
| `CEDS64ChanType(fh,ch)`  | `ceds64.chan_type(fh,ch)`       | Returns `ChanType` enum                 |
| `CEDS64ChanDiv(fh,ch)`   | `ceds64.chan_divide(fh,ch)`     |                                          |
| `CEDS64IdealRate(fh,c,r)` | `ceds64.ideal_rate(fh,c,r)`   |                                          |
| `CEDS64ChanTitle(fh,c,t)` | `ceds64.chan_title(fh,c,t)`   | Get/set                                 |
| `CEDS64ChanComment(...)` | `ceds64.chan_comment(...)`      | Get/set                                 |
| `CEDS64ChanUnits(fh,c,u)` | `ceds64.chan_units(fh,c,u)`   | Get/set                                 |
| `CEDS64ChanScale(fh,c,s)` | `ceds64.chan_scale(fh,c,s)`   | Get/set                                 |
| `CEDS64ChanOffset(fh,c,o)`| `ceds64.chan_offset(fh,c,o)`  | Get/set                                 |
| `CEDS64ChanMaxTime(fh,c)` | `ceds64.chan_max_time(fh,c)`  |                                          |
| `CEDS64ChanYRange(...)`   | `ceds64.chan_y_range(...)`     | Get/set                                 |
| `CEDS64ChanDelete(fh,c)` | `ceds64.chan_delete(fh,c)`     |                                          |
| `CEDS64ChanUndelete(fh,c)`| `ceds64.chan_undelete(fh,c)`  |                                          |
| `CEDS64GetExtMarkInfo(.)` | `ceds64.get_ext_mark_info(.)` | Returns (pre, rows, cols)                |
| `CEDS64PrevNTime(...)`    | `ceds64.prev_n_time(...)`     |                                          |
| `CEDS64SetWaveChan(...)` | `ceds64.set_wave_chan(...)`     | type 1=Adc, 9=RealWave                  |
| `CEDS64SetEventChan(.)`  | `ceds64.set_event_chan(.)`      | type 2=Fall, 3=Rise                      |
| `CEDS64SetMarkerChan(.)` | `ceds64.set_marker_chan(.)`     |                                          |
| `CEDS64SetLevelChan(.)`  | `ceds64.set_level_chan(.)`      |                                          |
| `CEDS64SetInitLevel(.)`  | `ceds64.set_init_level(.)`     |                                          |
| `CEDS64SetTextMarkChan(.)`| `ceds64.set_text_mark_chan(.)` |                                          |
| `CEDS64SetExtMarkChan(.)`| `ceds64.set_ext_mark_chan(.)`  |                                          |
| `CEDS64WriteWave(...)`   | `ceds64.write_wave(...)`       | Auto-detects int16 vs float32            |
| `CEDS64ReadWaveF(...)`   | `ceds64.read_wave_f(...)`      | Returns (n, np.array, t0)                |
| `CEDS64ReadWaveS(...)`   | `ceds64.read_wave_s(...)`      | Returns (n, np.array, t0)                |
| `CEDS64WriteEvents(...)` | `ceds64.write_events(...)`     | Accepts np.int64 array                   |
| `CEDS64ReadEvents(...)`  | `ceds64.read_events(...)`      | Returns (n, np.int64 array)              |
| `CEDS64WriteLevels(...)` | `ceds64.write_levels(...)`     |                                          |
| `CEDS64ReadLevels(...)`  | `ceds64.read_levels(...)`      | Returns (n, array, level)                |
| `CEDS64WriteMarkers(.)`  | `ceds64.write_markers(.)`      | List of `CEDMarker`                      |
| `CEDS64ReadMarkers(.)`   | `ceds64.read_markers(.)`       | Returns list of `CEDMarker`              |
| `CEDS64EditMarker(.)`    | `ceds64.edit_marker(.)`        |                                          |
| `CEDS64WriteExtMarks(.)` | `ceds64.write_ext_marks(.)`    | List of Text/Real/WaveMark               |
| `CEDS64ReadExtMarks(.)`  | `ceds64.read_ext_marks(.)`     | Returns list of ext markers              |
| `CEDS64MaskReset(m)`     | `ceds64.mask_reset(m)`         | `None` resets all                        |
| `CEDS64MaskMode(m,v)`    | `ceds64.mask_mode(m,v)`        | Get/set                                 |
| `CEDS64MaskCol(m,v)`     | `ceds64.mask_col(m,v)`         | Get/set                                 |
| `CEDS64MaskCodes(m,c)`   | `ceds64.mask_codes(m,c)`       | Get/set 256×4 array                      |
| `CEDS64ExtraData(...)`   | `ceds64.extra_data(...)`       |                                          |

## Data Classes

| MATLAB Class   | Python Class      | Description                      |
|----------------|-------------------|----------------------------------|
| `CEDMarker`    | `ceds64.CEDMarker`   | Time + 4 codes                |
| `CEDTextMark`  | `ceds64.CEDTextMark` | Marker + text string          |
| `CEDRealMark`  | `ceds64.CEDRealMark` | Marker + float32 matrix       |
| `CEDWaveMark`  | `ceds64.CEDWaveMark` | Marker + int16 waveform matrix|

## License

GPL-3.0, matching the original CEDS64ML from Cambridge Electronic Design.
