# spike2io #

This code loads Spike2 files into Python. It is a wrapper around code provided by CED and is meant to provide a nicer interface. Unlike current CED code, it supports multiple versions of Python (but is Windows only).

Note, this library currently relies on drivers from [spike2matson](https://ced.co.uk/upgrades/spike2matson), a Windows only MATLAB library provided by CED.

CED also provides other drivers that target Python and a wider operating system base, but it has numerous issues that may or may not be fixed in the future. That library is called [sonpy](https://pypi.org/project/sonpy/). 

Issues with `sonpy` include:
- limited Python version support
- broken behavior on Windows (may be fixed soon)
- poor data retrieval on MacOS (returns lists instead of numpy arrays)

Unfortunately OS level drivers are not provided (only compiled `pyd` files). When these issues are fixed I will try and change the dependency code from the Windows only MATLAB version to the broader version. 

**Work on this code was supported by a grant from the NIH NIDDK ([grant: R21DK140694](https://reporter.nih.gov/project-details/11232104))**

# Installation Steps and Requirements #

`pip install spike2io`

Requirements:
- numpy
- Python >= 3.9
-  
