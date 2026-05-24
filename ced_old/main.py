#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar 23 20:10:05 2026

@author: jim
"""




"""
https://github.com/MartinHeroux/spike2py
- requires .mat exported files
https://github.com/NeuralEnsemble/python-neo/blob/master/neo/rawio/spike2rawio.py
- uses old undocumented format (I think it is undocumented)
NM, see this:
https://github.com/alejoe91/python-neo/blob/master/neo/rawio/cedrawio.py
- seems not fully fleshed out
https://github.com/physiopy/phys2bids/blob/master/phys2bids/io.py
- useful starter code


"""

#Standard
#-------------------
import math
from datetime import datetime


#Third
#--------------------------
from sonpy import lib as sp


#Local
#--------------------------
from . import utils


def read_file(file_path):
    """
    This is the preferred entry point for working with this module.
    """
    return File(file_path)


class File():
    
    """
    Attributes
    ----------
    h
    version
    app_id
    file_size
    comments
    start_datetime
    
    
    """
    def __init__(self,file_path):
        
        read_only = True
        self.h = sp.SonFile(file_path,read_only)
        self.version = self.h.GetVersion()
        self.app_id = self.h.GetAppID()
        self.file_size = self.h.FileSize()
        
        comments = []
        
        for i in range(8):
            next_comment = self.h.GetFileComment(i)
            if next_comment:
                comments.append(next_comment)
            
        self.comments = comments
        
        self.n_ticks = float(self.h.MaxTime())
        
        
        #DateTime
        #--------------------------------------------------------
        temp = self.h.GetTimeDate()
        if all(x == 0 for x in temp):
            self.start_datetime = None
        else:
            #temp is apparently backwards, time ... dd, mm, yyyy
            self.start_datetime = datetime(*reversed(temp))
            
            
        self.time_base = self.h.GetTimeBase()
        
        self.n_seconds = self.n_ticks*self.time_base
        
        n_chans_max = self.h.MaxChannels()
        
        
        #Processing of the channels
        #--------------------------------------------------------
        
        objs = [None] * n_chans_max
        chan_name = [None] * n_chans_max
        
        # Note, not all channels are actually used. It appears from
        # the documentation that the "generic" loading approach
        # is to iterate through all (i.e., can't skip to specific
        # channels that are in use)
        
        data_type = sp.DataType
        chan_info = []
        self.chan_type_all = [data_type] * n_chans_max
        
        self.waveforms = []
        self.event_falls = []
        self.event_rises = []
        self.event_both = []
        self.markers = []
        self.wave_markers = []
        self.real_markers = []
        self.text_markers = []
        self.all_chan_objects = []
        
        self.chan_types = []
        self.chan_names = []
        
        for i in range(n_chans_max):
            chan_type = self.h.ChannelType(i)
            
            if chan_type == data_type.Off:
                t = Unused()
            elif chan_type == data_type.Adc:
                #ADC - Waveform
                t = ADC(self.h,i,self)
                self.waveforms.append(t)
            elif chan_type == data_type.EventFall:
                is_rise = False
                t = EventRiseOrFall(self.h,i,self,is_rise)
                self.event_falls.append(t)
            elif chan_type == data_type.EventRise:
                is_rise = True
                t = EventRiseOrFall(self.h,i,self,is_rise)
                self.event_rises.append(t)
            elif chan_type == data_type.EventBoth:
                t = EventBoth(self.h,i,self)
                self.event_both.append(t)
            elif chan_type == data_type.Marker:
                t = Marker(self.h,i,self)
                self.markers.append(t)
            elif chan_type == data_type.AdcMark:
                t = WaveMark(self.h,i,self)
                self.wave_markers.append(t)
            elif chan_type == data_type.RealMark:
                t = RealMark(self.h,i,self)
                self.real_markers.append(t)
            elif chan_type == data_type.TextMark:
                t = TextMark(self.h,i,self)
                self.text_markers.append(t)
            else:
                raise ValueError(f'Unexpected channel type: {self.chan_type_all[i]}')
                
            if chan_type != data_type.Off:
                chan_info.append([i,t.name,chan_type])
                self.all_chan_objects.append(t)
                self.chan_types.append(chan_type)
                self.chan_names.append(t.name)
                            
        self.chan_info = chan_info
        
        
            
            
        """
        %Filtering to used only channels
            %---------------------------------------------
            chan_id = (1:n_chans_max)';
            mask = chan_type_numeric ~= 0;
            chan_name = chan_name(mask);
            chan_type_numeric = chan_type_numeric(mask);
            chan_id = chan_id(mask);
            chan_type = obj.TYPE_NAME_MAP(chan_type_numeric)';
            objs = objs(mask);
            obj.t = table(chan_name,chan_type,chan_id);
            obj.chan_type_numeric = chan_type_numeric;
            obj.chan_names = chan_name;
            obj.chan_type_string = chan_type;
        """
        
    def __repr__(self):
        return utils.print_object(self)

class Channel():
    
    """
    parent ced.file
    h ced.son.file_handle
    h2
    chan_id
    n_ticks
    max_time

    name
    units
    comment

    fs
    offset
    scale

    %Time divisor from main clock to this clock
    chan_div
    y_range
    """
    
    def __init__(self,h,chan_id,parent):
        self.h = h
        self.chan_id = chan_id
        self.parent = parent
        
        self.n_ticks = h.ChannelMaxTime(chan_id)
        self.name = h.GetChannelTitle(chan_id)
        self.units = h.GetChannelUnits(chan_id)
        self.units = self.units.strip()
        self.comment = h.GetChannelComment(chan_id)
        
        
        #Comment, Offset, Scale, Title, Units, YRange
        
        self.chan_div = h.ChannelDivide(chan_id)
        time_base = parent.time_base
        
        #From documentation:
        #   SampleRateInHz =                     1.0
        #                 ---------------------------------------
        #              (CEDS64ChanDiv(fhand, 1)*CEDS64TimeBase(fhand));

        self.fs = 1/(self.chan_div*time_base)
        
        self.max_time = parent.n_seconds #obj.n_ticks/obj.fs;
        
        self.chan_offset = h.GetChannelOffset(chan_id)
        
        self.scale = h.GetChannelScale(chan_id)
        
        [y1,y2] = h.GetChannelYRange(chan_id)
        
        self.y_range = [y1,y2]    
        
     
    # Recursion error with parent
    #def __getitem__(self, key):
    #    return self.__dict__[key]

    def __repr__(self):
        return utils.print_object(self)
    
class Unused():
    
    def __init__(self):
        self.name = 'unused'

class ADC(Channel):        
    
    """
    h - handle to lib object
    chan_id - 0 to 30? 
    parent - File
    """

    def __init__(self,h,chan_id,parent):
        Channel.__init__(self, h, chan_id, parent)

        
        #Is this only true for waveform?
        #Floor? ceil? round?
        self.n_ticks = math.ceil(parent.n_ticks/self.chan_div)
        
    def get_data(self,time_range=None,sample_range=None):
        """
        
        Parameters
        ----------
        time_range : TYPE, optional
            DESCRIPTION. The default is None.
        sample_range : TYPE, optional
            DESCRIPTION. The default is None.
            
            
            
            
            
            

        Returns
        -------
        None.

        """
        
        """
            arguments
                obj ced.channel.adc
                in.n_init (1,1) {mustBeNumeric} = 1e4
                in.growth_rate (1,1) {mustBeNumeric} = 2
                in.time_range (:,:) {h__sizeCheck(in.time_range)} = []
                in.sample_range (:,:) {h__sizeCheck(in.sample_range)} = []
                in.time_format {mustBeMember(in.time_format,{'none','numeric','datetime'})} = 'numeric'
                in.return_format {mustBeMember(in.return_format,{'int16','single','double','data_object'})} = 'double'    
            end

            if in.return_format == "data_object" && isempty(which('sci.time_series.data'))
                in.return_format = 'double';
            end

            n_samples = obj.n_ticks;
        """
        
        #Work out the time/sample range
        #----------------------------
        if time_range is not None:
            pass
        elif sample_range is not None:
            pass
        else:
            s1 = 0;
            s2 = self.n_ticks-1;
            
            
        
        
        
        """
        function s = h__DataRetrieval(obj,s1,s2,in,n_samples)

        %Conversion from samples to ticks
        s1_in = s1*obj.chan_div;
        s2_in = s2*obj.chan_div;
        
        %Request may not be inclusive
        s2_in = s2_in + 1;
        
        %Data call
        %-------------------------
        %Request is in ticks, which is not samples
        %thus the scaling above by chan_div
        %
        %Output is of type int16
        [n_read,data,start_tick] = CEDS64ReadWaveS(obj.h2,obj.chan_id,...
            n_samples,s1_in,s2_in);
        
        %- Not using this ... see below for why
        %- Leaving this in place for testing if desired
        % [n_read,data,start_time] = CEDS64ReadWaveF(obj.h2,obj.chan_id,...
        %     n_samples,s1,s2);
        
        %Note, ints generally cause bugs in MATLAB so let's convert to double
        %
        %   ASSUMES: we don't have super large data > 9e15 elements
        start_sample = double(start_tick/obj.chan_div) + 1;
        last_sample = double(start_sample + length(data)-1);
        start_time = start_sample/obj.fs;
        dt = double(1/obj.fs);
        n_samples_out = length(data);
        """
        
        import pdb
        pdb.set_trace()
        
        pass


class EventRiseOrFall():

    def __init__(self,h,chan_id,parent):
        Channel.__init__(self, h, chan_id, parent)

class EventBoth():

    def __init__(self,h,chan_id,parent):
        Channel.__init__(self, h, chan_id, parent)

class Marker():

    def __init__(self,h,chan_id,parent):
        Channel.__init__(self, h, chan_id, parent)

class WaveMark():

    def __init__(self,h,chan_id,parent):
        Channel.__init__(self, h, chan_id, parent)

class RealMark():

    def __init__(self,h,chan_id,parent):
        Channel.__init__(self, h, chan_id, parent)
        
class TextMark():

    def __init__(self,h,chan_id,parent):
        Channel.__init__(self, h, chan_id, parent)
        
        self.fs = 1/parent.time_base
        self.max_time = self.n_ticks/self.fs
        
    def get_data(self):
        """
                arguments
                obj ced.channel.text_mark
                in.return_format {mustBeMember(in.return_format,{'table'})} = 'table';
                in.max_events (1,1) {mustBeNumeric} = 1e6
                in.time_range (1,2) {mustBeNumeric} = [0 obj.max_time]
                in.n_init (1,1) {mustBeNumeric} = 1000
                in.growth_rate (1,1) {mustBeNumeric} = 2
            end
            
            sample_range = round(in.time_range*obj.fs);
            %Bounds check ...
            if sample_range(1) < 0 
                error('error, invalid time requested')
            end
            if sample_range(2) > obj.n_ticks
                error('error, invalid time requested')
            end
        """
        
        import pdb
        pdb.set_trace()
        pass
        
        
        
        