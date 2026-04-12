"""
Example file for testing SonPy, the Python API for the CED SON library
Copyright (C) CED 2020, all rights reserved

Warning: requires matplotlib.pyplot and tkinter

Opens a user specified file in read only mode and plots some of
the data in it to showcase the features available in SpyKE.
"""

import numpy as np
import matplotlib.pyplot as plt
from math import floor

import tkinter as tk
import tkinter.filedialog   # Sometimes an error is reported if this function is not explicitly included

from sonpy import lib as sp

# Get file path
root = tk.Tk()
root.withdraw()

FilePath = tk.filedialog.askopenfilename()
print(FilePath)

# Open file
MyFile = sp.SonFile(FilePath, True)

if MyFile.GetOpenError() != 0:
    print('Error opening file:',sp.GetErrorString(MyFile.GetOpenError()))
    quit()

# Find first Waveform channel
WaveChan = -1

for i in range(MyFile.MaxChannels()):
    if MyFile.ChannelType(i) == sp.DataType.Adc:
        WaveChan = i
        break

if WaveChan == -1:
    # Find first RealWave channel
    for i in range(MyFile.MaxChannels()):
        if MyFile.ChannelType(i) == sp.DataType.RealWave:
            WaveChan = i
            break

if WaveChan == -1:
    print('No Waveform or Realwave channels available to plot. Exiting...')
    quit()

# Get number of seconds to read
dMaxTime = MyFile.ChannelMaxTime(WaveChan)*MyFile.GetTimeBase()

nSeconds = 0.
bInputNumber = False
while not bInputNumber:
    strInput = input('Enter (decimal) number of seconds of data to read, no greater than '+str(dMaxTime)+': ')
    try:
        dSeconds = float(strInput)
        if dSeconds < dMaxTime:
            bInputNumber = True
    except:
        pass

# Prepare for plotting
dPeriod = MyFile.ChannelDivide(WaveChan)*MyFile.GetTimeBase()
nPoints = floor(dSeconds/dPeriod)
xPoints = np.arange(0, nPoints*dPeriod, dPeriod)

# Read data
WaveData =  MyFile.ReadFloats(WaveChan, nPoints, 0)

if len(WaveData) == 1 and WaveData[0] < 0:
    print('Error reading data:',sp.GetErrorString(int(WaveData[0])))
    quit()
elif len(WaveData) == 0:
    print('No data read')
    quit()
elif len(WaveData) != nPoints:
    print('Bad number of points read, expected',str(nPoints),'but got',str(len(WaveData)))
    quit()

# Plot channel
fig, ax = plt.subplots()
ax.plot(xPoints, WaveData)
ax.set(xlabel='Time (s)', ylabel=MyFile.GetChannelUnits(WaveChan), title='Channel '+str(WaveChan+1)+' ('+MyFile.GetChannelTitle(WaveChan)+')')
plt.show()
