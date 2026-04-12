"""
Example file for testing SonPy, the Python API for the CED SON library
Copyright (C) CED 2020, all rights reserved

Warning: requires matplotlib.pyplot and tkinter

Retrieves all of the data in a user specified file.
"""

import numpy as np
import matplotlib.pyplot as plt
from math import floor

import tkinter as tk
import tkinter.filedialog   # Sometimes an erorr is reported if this function is not explicitly included

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

# Data storage and function finder
MyData = []
DataReadFunctions = {
    sp.DataType.Adc:        sp.SonFile.ReadInts,
    sp.DataType.EventFall:  sp.SonFile.ReadEvents,
    sp.DataType.EventRise:  sp.SonFile.ReadEvents,
    sp.DataType.EventBoth:  sp.SonFile.ReadEvents,
    sp.DataType.Marker:     sp.SonFile.ReadMarkers,
    sp.DataType.AdcMark:    sp.SonFile.ReadWaveMarks,
    sp.DataType.RealMark:   sp.SonFile.ReadRealMarks,
    sp.DataType.TextMark:   sp.SonFile.ReadTextMarks,
    sp.DataType.RealWave:   sp.SonFile.ReadFloats
}

# Loop through channels retrieving data
for i in range(MyFile.MaxChannels()):
    if MyFile.ChannelType(i) != sp.DataType.Off:
        MyData.append(DataReadFunctions[MyFile.ChannelType(i)](MyFile, i, int(MyFile.ChannelMaxTime(i)/MyFile.ChannelDivide(i)), 0, MyFile.ChannelMaxTime(i)))

# Attempt to print data - Only try this if your file is VERY small!
#print(MyData)
