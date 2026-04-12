# -*- coding: utf-8 -*-
"""
Support functions used in other modules.

Several, but not all, of the functions here are defined so we have functions
that are the equivalent of the same-named functions in Matlab, e.g. gausswin

"""
from __future__ import division

import inspect


def print_object(obj):
    """
    Goal is to eventually mimic Matlab's default display behavior for objects

    Example output from Matlab

    morphology: [1x1 seg_worm.features.morphology]
       posture: [1x1 seg_worm.features.posture]
    locomotion: [1x1 seg_worm.features.locomotion]
          path: [1x1 seg_worm.features.path]
          info: [1x1 seg_worm.info]

    #TODO: For ndarrays we should implement size displays instead of length
    #TODO: The @property hack doesn't work for @property values from parent
    classes, I would need to look at __bases__
    """

    # TODO - have some way of indicating nested function and not doing fancy
    # print for nested objects ...

    MAX_WIDTH = 70

    dict_local = obj.__dict__

    key_names = [k for k in dict_local]

    try:
        # TODO: Also include __bases__
        names_of_prop_methods = [
            name for name, value in vars(
                obj.__class__).items() if isinstance(
                value, property)]
        prop_code_ok = True
    except:
        prop_code_ok = False

    is_prop = [False] * len(key_names)
    if prop_code_ok:
        is_prop += [True] * len(names_of_prop_methods)
        key_names += names_of_prop_methods

    key_lengths = [len(x) for x in key_names]

    if len(key_lengths) == 0:
        return ""

    max_key_length = max(key_lengths)
    key_padding = [max_key_length - x for x in key_lengths]

    max_leadin_length = max_key_length + 2
    max_value_length = MAX_WIDTH - max_leadin_length

    lead_strings = [' ' * x + y + ': ' for x, y in zip(key_padding, key_names)]

    # TODO: Alphabatize the results ????
    # Could pass in as a option
    # TODO: It might be better to test for built in types
    #   Class::Bio.Entrez.Parser.DictionaryElement
    #   => show actual dictionary, not what is above

    value_strings = []
    for key, is_prop_local in zip(key_names, is_prop):
        if is_prop_local:
            temp_str = '@property method'
        else:
            run_extra_code = False
            value = dict_local[key]
            if hasattr(value, '__dict__'):
                try:  # Not sure how to test for classes :/
                    class_name = value.__class__.__name__
                    module_name = inspect.getmodule(value).__name__
                    temp_str = 'Class::' + module_name + '.' + class_name
                except:
                    run_extra_code = True
            else:
                run_extra_code = True

            if run_extra_code:
                # TODO: Change length to shape if available
                if isinstance(value, list) and len(value) > max_value_length:
                    len_value = len(value)
                    temp_str = 'Type::List, Len %d' % len_value
                else:
                    # Perhaps we want str instead?
                    # Changed from repr to str because things Python was not
                    # happy with lists of numpy arrays
                    temp_str = str(value)
                    if len(temp_str) > max_value_length:
                        #type_str = str(type(value))
                        #type_str = type_str[7:-2]
                        try:
                            len_value = len(value)
                        except:
                            len_value = 1
                        temp_str = str.format(
                            'Type::{}, Len: {}', type(value).__name__, len_value)

        value_strings.append(temp_str)

    final_str = ''
    for cur_lead_str, cur_value in zip(lead_strings, value_strings):
        final_str += (cur_lead_str + cur_value + '\n')

    return final_str




    
    