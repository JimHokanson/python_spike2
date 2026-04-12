"""
Example file for testing SonPy, the Python API for the CED SON library
Copyright (C) CED 2020, all rights reserved

Creates a new 64-bit file called "TestFile.smrx" and writes some data to it.
"""

import numpy as np
from sonpy import lib as sp

# Create a new file called TestFile
# The extension dictates the architecture: smrx for 64-bit, anything else becomes 32-bit
MyFile = sp.SonFile('TestFile.smrx')  

if MyFile.GetOpenError() != 0:  # Report any error from file creation
    print('Error',MyFile.GetOpenError(),'encountered trying to create file, exiting...')
    exit()

if not MyFile.is64file() or MyFile.is32file():  # Check file has correct architecture
    print('File is wrong architecture should be 64-bit. Exiting...')
    exit()

if not MyFile.CanWrite():   # Check file is writable
    print('File is read only. Exiting...')
    exit()

MyFile.SetFileComment(0, 'This is an example file for testing SonPy') # Set a global file comment

# Some constants to be used for channel setup
CurChan = 0
UsedChans = 0
Scale = 65535/20
Offset = 0
ChanLow = 0
ChanHigh = 5
tFrom = 0
tUpto = sp.MaxTime64()         # The maximum allowed time in a 64-bit SON file
dTimeBase = 1e-6               # s
x86BufSec = 2.
EventRate = 1/(dTimeBase*1e3)  # Hz, period is 1000 greater than the timebase
SubDvd = 1                     # How many ticks between attached items in WaveMarks
nPre = 4                       # Pre-trigger offset of items in WaveMarks
nEvents = 10
Multiplier = 25                # For spacing
nRows = 20                     # For DataList and extended markers
nCols = 3                      # For extended markers

# Some text constants for names
WaveTitle = 'Waveform'
RiseTitle = 'EvtRise'
FallTitle = 'EvtFall'
BothTitle = 'EvtBoth'
MarkTitle = 'Marker'
WMrkTitle = 'AdcMark'
TMrkTitle = 'TextMark'
ChanUnits = 'V'

# Some arrays of data to be written
aData = np.arange(0, nRows/2)
bData = np.arange(nRows/2, 0, -1)
DataList = np.concatenate([aData, bData])

AdcData = np.array(DataList, dtype=np.short)

FallData = np.arange(0, 2*nEvents*Multiplier, 2*Multiplier, dtype=np.int64)
RiseData = np.arange(Multiplier, 2*nEvents*Multiplier, 2*Multiplier, dtype=np.int64)
BothData = np.empty((RiseData.size + FallData.size), dtype=np.int64)
BothData[0::2] = FallData
BothData[1::2] = RiseData

MarkData = np.empty(nEvents, dtype=sp.DigMark)
for i in range(nEvents):
    MarkData[i] = sp.DigMark((2*i+1)*Multiplier, i)

WMrkData = np.zeros(nEvents, dtype=sp.WaveMarker)
TMrkData = np.empty(nEvents, dtype=sp.TextMarker)
Texts = ['Lorem','ipsum','dolor','sit','amet,','🗿','consectetur','adipiscing','elit,','⛄']
for i in range(nEvents):
    WMrkData[i] = sp.WaveMarker(nRows, nCols, MarkData[i])
    TMrkData[i] = sp.TextMarker(Texts[i], MarkData[i])
    for j in range(nRows):
        for k in range(nCols):
            WMrkData[i][j, k] = int(DataList[(i+j+k*5) % nRows] * (k+1))


MyFile.SetTimeBase(dTimeBase)  # Set timebase

# Test a Waveform channel
MyFile.SetWaveChannel(CurChan, 1*Multiplier, sp.DataType.Adc)
MyFile.SetChannelTitle(CurChan, WaveTitle)
MyFile.SetChannelUnits(CurChan, ChanUnits)
MyFile.SetChannelScale(CurChan, Scale)
MyFile.SetChannelOffset(CurChan, Offset)
MyFile.SetChannelYRange(CurChan, ChanLow, ChanHigh)

tNext = MyFile.WriteInts(CurChan, AdcData, tFrom)
MyFile.WriteInts(CurChan, AdcData, tNext)
print('Reading the ints that we just saved:')
print(MyFile.ReadInts(CurChan, 2*nRows, 0))
print()

# RealWave channels work in a very similar manner to Waveform channels.
# You can read either Waveform or RealWave channels as floating point or integer data,
# depending on the data of the array you pass in.
print('Reading the floats that we just saved:')
print(MyFile.ReadFloats(CurChan, 2*nRows, 0))
print()

# Test an EventFall
CurChan += 1
MyFile.SetEventChannel(CurChan, EventRate)
MyFile.SetChannelTitle(CurChan, FallTitle)

MyFile.WriteEvents(CurChan, FallData)
print('Reading the events that we just saved:')
print(MyFile.ReadEvents(CurChan, nEvents, tFrom, tUpto))
print()

# Test a Marker channel
CurChan += 1
MyFile.SetMarkerChannel(CurChan, EventRate)
MyFile.SetChannelTitle(CurChan, MarkTitle)

MyFile.WriteMarkers(CurChan, MarkData)
print('Reading the markers that we just saved:')
print(MyFile.ReadMarkers(CurChan, nEvents, tFrom, tUpto))
print()

# Test a WaveMark channel
CurChan +=1 
MyFile.SetWaveMarkChannel(CurChan, EventRate, nRows, nCols, -1, SubDvd, nPre)
MyFile.SetChannelTitle(CurChan, WMrkTitle)
MyFile.SetChannelUnits(CurChan, ChanUnits)
MyFile.SetChannelScale(CurChan, Scale/3)
MyFile.SetChannelOffset(CurChan, Offset)
MyFile.SetChannelYRange(CurChan, ChanLow, ChanHigh)

MyFile.WriteWaveMarks(CurChan, WMrkData)
print('Reading the wave marks that we just saved:')
print(MyFile.ReadWaveMarks(CurChan, nEvents, tFrom, tUpto))
print()

# The differences between WaveMark and RealMark are again, subtle. In addition
# to the fact that you don't need to set a scale or offset, you also cannot set
# a variable number of columns (traces) of data. For more details on the
# specifics of these channel types see the Spike2 documentation.


# Test a TextMark channel
CurChan += 1
MyFile.SetTextMarkChannel(CurChan, EventRate, max(len(s) for s in Texts)+1)
MyFile.SetChannelTitle(CurChan, TMrkTitle)

MyFile.WriteTextMarks(CurChan, TMrkData)
print('Reading the text marks that we just saved:')
print(MyFile.ReadTextMarks(CurChan, nEvents, tFrom, tUpto))
print()

# Saves the file and releases the resources owned by the object
del MyFile

# Test opening an existing file (in read only mode)
#MyFile = sp.SonFile('TestFile.smrx', True)

# The file is saved again and its resources released when object is destroyed
