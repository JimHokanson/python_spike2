# -*- coding: utf-8 -*-
"""
Created on Fri May 22 21:57:10 2026

@author: Jim

Requires:
    - cffi (pip install cffi)
    - A C compiler (MSVC via Visual Studio Build Tools)
    - x64/ceds64int.h, x64/ceds64int.lib, x64/ceds64int.dll
"""

import cffi

ffi = cffi.FFI()

ffi.cdef("""

    typedef struct S64Marker {
        long long m_Time;
        unsigned char m_Code1;
        unsigned char m_Code2;
        unsigned char m_Code3;
        unsigned char m_Code4;
    } S64Marker;

    /* Basic file functions */
    int S64FileCount(void);
    int S64CloseAll(void);
    int S64Create(const char *FileName, int nChans, int nBig);
    int S64Open(const char *FileName, int nFlag);
    int S64IsOpen(int nFid);
    int S64Close(int nFid);
    int S64Empty(int nFid);

    /* File properties */
    int S64GetFileComment(int nFid, int nInd, char *Comment, int nGetSize);
    int S64SetFileComment(int nFid, int nInd, const char *Comment);
    int S64GetFreeChan(int nFid);
    int S64MaxChans(int nFid);
    double S64GetTimeBase(int nFid);
    int S64SetTimeBase(int nFid, double dSecPerTick);
    long long S64SecsToTicks(int nFid, double dSec);
    double S64TicksToSecs(int nFid, long long tSec);
    int S64GetVersion(int nFid);
    long long S64FileSize(int nFid);
    long long S64MaxTime(int nFid);
    int S64TimeDate(int nFid, long long *pTDGet,
                    const long long *pTDSet, int iMode);
    int S64AppID(int nFid, int *pTDGet, const int *pTDSet, int iMode);
    int S64GetExtraData(int nFid, void *pData,
                        unsigned int nBytes, unsigned int nOffset);
    int S64SetExtraData(int nFid, const void *pData,
                        unsigned int nBytes, unsigned int nOffset);

    /* Channel properties */
    int S64ChanType(int nFid, int nChan);
    long long S64ChanDivide(int nFid, int nChan);
    double S64GetIdealRate(int nFid, int nChan);
    double S64SetIdealRate(int nFid, int nChan, double dRate);
    int S64GetChanComment(int nFid, int nChan, char *Comment, int nGetSize);
    int S64SetChanComment(int nFid, int nChan, const char *Comment);
    int S64GetChanTitle(int nFid, int nChan, char *Title, int nGetSize);
    int S64SetChanTitle(int nFid, int nChan, const char *Title);
    int S64GetChanScale(int nFid, int nChan, double *dScale);
    int S64SetChanScale(int nFid, int nChan, double dScale);
    int S64GetChanOffset(int nFid, int nChan, double *dOffset);
    int S64SetChanOffset(int nFid, int nChan, double dOffset);
    int S64GetChanUnits(int nFid, int nChan, char *Units, int nGetSize);
    int S64SetChanUnits(int nFid, int nChan, const char *Units);
    long long S64ChanMaxTime(int nFid, int nChan);
    int S64ChanDelete(int nFid, int nChan);
    int S64ChanUndelete(int nFid, int nChan);
    int S64GetChanYRange(int nFid, int nChan, double *dLow, double *dHigh);
    int S64SetChanYRange(int nFid, int nChan, double dLow, double dHigh);
    int S64ItemSize(int nFid, int nChan);
    long long S64PrevNTime(int nFid, int nChan, long long tFrom,
                           long long tTo, int n, int nMask, int nAsWave);
    int S64GetExtMarkInfo(int nFid, int nChan, int *nRows, int *nCols);

    /* Channel creation */
    int S64SetEventChan(int nFid, int nChan, double dRate, int iType);
    int S64SetWaveChan(int nFid, int nChan, long long tDiv,
                       int nType, double dRate);
    int S64SetMarkerChan(int nFid, int nChan, double dRate, int nkind);
    int S64SetLevelChan(int nFid, int nChan, double dRate);
    int S64SetInitLevel(int nFid, int nChan, int nLevel);
    int S64SetTextMarkChan(int nFid, int nChan, double dRate, int nMax);
    int S64SetExtMarkChan(int nFid, int nChan, double dRate, int nType,
                          int nRows, int nCols, long long tDiv);

    /* Event read/write */
    int S64WriteEvents(int nFid, int nChan,
                       const long long *pData, int nCount);
    int S64ReadEvents(int nFid, int nChan, long long *pData, int nMax,
                      long long tFrom, long long tTo, int nMask);

    /* Marker read/write */
    int S64WriteMarkers(int nFid, int nChan,
                        const S64Marker *pData, int count);
    int S64ReadMarkers(int nFid, int nChan, S64Marker *pData, int nMax,
                       long long tFrom, long long tUpto, int nMask);
    int S64EditMarker(int nFid, int nChan, long long t,
                      const S64Marker *pM);

    /* Level read/write */
    int S64WriteLevels(int nFid, int nChan,
                       const long long *pData, int nCount);
    int S64ReadLevels(int nFid, int nChan, long long *pData, int nMax,
                      long long tFrom, long long tTo, int *nLevel);

    /* Extended marker read/write */
    int S64Write1TextMark(int nFid, int nChan, const S64Marker *pData,
                          const char *text, int nSize);
    int S64Write1RealMark(int nFid, int nChan, const S64Marker *pData,
                          const float *real, int nSize);
    int S64Write1WaveMark(int nFid, int nChan, const S64Marker *pData,
                          const short *wave, int nSize);
    int S64Read1TextMark(int nFid, int nChan, S64Marker *pData, char *text,
                         long long tFrom, long long tUpto, int nMask);
    int S64Read1RealMark(int nFid, int nChan, S64Marker *pData, float *real,
                         long long tFrom, long long tUpto, int nMask);
    int S64Read1WaveMark(int nFid, int nChan, S64Marker *pData, short *wave,
                         long long tFrom, long long tUpto, int nMask);

    /* Waveform read/write */
    long long S64WriteWaveS(int nFid, int nChan, const short *pData,
                            int count, long long tFrom);
    long long S64WriteWaveF(int nFid, int nChan, const float *pData,
                            int count, long long tFrom);
    long long S64WriteWave64(int nFid, int nChan, const double *pData,
                             int count, long long tFrom);
    int S64ReadWaveS(int nFid, int nChan, short *pData, int nMax,
                     long long tFrom, long long tUpto,
                     long long *tFirst, int nMask);
    int S64ReadWaveF(int nFid, int nChan, float *pData, int nMax,
                     long long tFrom, long long tUpto,
                     long long *tFirst, int nMask);
    int S64ReadWave64(int nFid, int nChan, double *pData, int nMax,
                      long long tFrom, long long tUpto,
                      long long *tFirst, int nMask);

    /* Marker masks */
    int S64GetMaskCodes(int nMask, int *iCode, int *nMode);
    int S64SetMaskCodes(int nMask, const int *nCode);
    int S64SetMaskMode(int nMask, int nMode);
    int S64GetMaskMode(int nMask);
    int S64SetMaskCol(int nMask, int nCol);
    int S64GetMaskCol(int nMask);
    int S64ResetMask(int nMask);
    int S64ResetAllMasks(void);

""")

# --------------------------------------------------------------------------
# set_source: the *actual* C code compiled into the extension.
# We pre-define MATINT_API so the header's __declspec works in import mode.
# --------------------------------------------------------------------------
ffi.set_source(
    "_ceds64_cffi",
    r"""
    #define MATINT_API __declspec(dllimport)
    #include "ceds64int.h"
    """,
    libraries=["ceds64int"],
    library_dirs=["x64"],
    include_dirs=["x64"],
)

if __name__ == "__main__":
    ffi.compile(verbose=True)
    print("\nDone. _ceds64_cffi extension built successfully.")