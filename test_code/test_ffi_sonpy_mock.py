"""
Mock-based test of ffi_sonpy.py translation logic.
A fake `sonpy` module mimics the documented 1.9.5/1.9.12 API so we can verify
the shim's handle registry, 1-based->0-based channel shift, and return shapes
WITHOUT the real CED binary.
"""
import sys, types, enum
import numpy as np

# ---- Build a fake `sonpy` module -----------------------------------------
fake = types.ModuleType("sonpy")

class DataType(enum.Enum):
    Off=0; Adc=1; EventFall=2; EventRise=3; EventBoth=4
    Marker=5; AdcMark=6; RealMark=7; TextMark=8; RealWave=9
fake.DataType = DataType

class DigMark:
    def __init__(self, tick=0, c1=0, c2=0, c3=0, c4=0):
        self.Tick=tick; self.Code1=c1; self.Code2=c2; self.Code3=c3; self.Code4=c4
fake.DigMark = DigMark

class WaveMarker:
    def __init__(self, mark, data): self._m=mark; self.Data=data
    def GetMark(self): return self._m
class TextMarker:
    def __init__(self, mark, text): self._m=mark; self.Text=text
    def GetMark(self): return self._m
fake.WaveMarker=WaveMarker; fake.TextMarker=TextMarker
fake.MaxTime64 = lambda: 10**15

# A fake 2-channel file: ch0 = Adc waveform, ch1 = Marker.
class SonFile:
    def __init__(self, name, *a):
        self.name=name; self._err=0
        self._divide=10; self._tb=1e-6
        # 0-based channel layout
        self._types={0:DataType.Adc, 1:DataType.Marker}
        self._wave=np.arange(100, dtype=np.int16)   # ch0 samples
        self._marks=[DigMark(5,65,0,0,0), DigMark(25,66,0,0,0)]  # ch1
    def GetOpenError(self): return self._err
    def CanWrite(self): return False
    def Commit(self): pass
    def GetTimeBase(self): return self._tb
    def MaxTime(self): return 1000
    def MaxChannels(self): return 32
    def ChannelType(self, ch): return self._types.get(ch, DataType.Off)
    def ChannelDivide(self, ch): return self._divide if ch==0 else 0
    def ChannelMaxTime(self, ch): return 990
    def GetChannelTitle(self, ch): return f"title{ch}"      # ch is 0-based!
    def GetChannelUnits(self, ch): return "mV"
    def GetChannelComment(self, ch): return "cmt"
    def GetChannelScale(self, ch): return 2.0
    def GetChannelOffset(self, ch): return 0.5
    def GetChannelYRange(self, ch): return (-5.0, 5.0)
    def GetIdealRate(self, ch): return 1000.0
    def FirstTime(self, ch, tfrom, tupto): return 0   # first sample at tick 0
    def ReadInts(self, ch, nmax, tfrom, tupto):
        assert ch==0, f"expected 0-based ch0, got {ch}"
        return self._wave[:nmax]
    def ReadEvents(self, ch, nmax, tfrom, tupto): return np.array([5,25],dtype=np.int64)
    def ReadMarkers(self, ch, nmax, tfrom, tupto):
        assert ch==1, f"expected 0-based ch1, got {ch}"
        return list(self._marks)
    def GetExMarkInfo(self, ch): return [20, 3, 4]   # [rows, cols, pre]

fake.SonFile = SonFile
sys.modules["sonpy"] = fake

# ---- Import the shim under test ------------------------------------------
sys.path.insert(0, "/mnt/user-data/outputs")
import ffi_sonpy as ffi

def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    assert cond, label

print("=== open / handle registry ===")
h = ffi.open("demo.smrx")
check("open returns positive int handle", isinstance(h, int) and h > 0)
check("file_count == 1", ffi.file_count() == 1)

print("=== metadata + 1-based->0-based channel shift ===")
check("max_channels", ffi.max_channels(h) == 32)
# main.py asks for channel 1 (1-based) -> should hit fake ch0
check("chan_type(1) -> ADC", ffi.chan_type(h, 1) == ffi.ChanType.ADC)
check("chan_type(2) -> MARKER", ffi.chan_type(h, 2) == ffi.ChanType.MARKER)
check("chan_title(1) reads fake ch0", ffi.chan_title(h, 1) == "title0")
check("chan_title(2) reads fake ch1", ffi.chan_title(h, 2) == "title1")
check("chan_scale", ffi.chan_scale(h, 1) == 2.0)
check("chan_y_range", ffi.chan_y_range(h, 1) == (-5.0, 5.0))

print("=== waveform read (shape + first tick + scaling stays raw) ===")
n, data, t0 = ffi.read_wave_s(h, 1, 50, 0)
check("n_read == 50", n == 50)
check("dtype int16 (raw, unscaled)", data.dtype == np.int16)
check("first sample value raw 0", data[0] == 0)
check("t_first == 0 (from FirstTime)", t0 == 0)

print("=== events ===")
n, ev = ffi.read_events(h, 1, 100, 0)
check("events length 2", n == 2 and list(ev) == [5, 25])

print("=== markers (1-based ch2 -> fake ch1) ===")
n, marks = ffi.read_markers(h, 2, 100, 0)
check("2 markers", n == 2)
check("CEDMarker type", isinstance(marks[0], ffi.CEDMarker))
check("marker time/code", marks[0].time == 5 and marks[0].code1 == 65)

print("=== get_ext_mark_info reorder [rows,cols,pre] -> (pre,rows,cols) ===")
pre, rows, cols = ffi.get_ext_mark_info(h, 1)
check("pre==4", pre == 4)
check("rows==20", rows == 20)
check("cols==3", cols == 3)

print("=== secs_to_ticks via timebase ===")
check("secs_to_ticks scalar", ffi.secs_to_ticks(h, 1e-3) == 1000)
check("secs_to_ticks array", list(ffi.secs_to_ticks(h, np.array([1e-3, 2e-3]))) == [1000, 2000])

print("=== close ===")
rc = ffi.close(h)
check("close returns 0", rc == 0)
check("file_count == 0 after close", ffi.file_count() == 0)

print("\nALL MOCK TESTS PASSED ✓")
