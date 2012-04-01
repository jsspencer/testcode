'''Utility functions.'''

import os.path
import re

import testcode2.exceptions as exceptions

def testcode_filename(stem, file_id, inp, args):
    '''Construct filename in testcode format.'''
    filename = '%s.%s' % (stem, file_id)
    if inp:
        filename = '%s.inp=%s' % (filename, inp)
    if args:
        args_string = args.replace(' ','_')
        filename = '%s.args=%s' % (filename, args_string)
    return filename

def try_floatify(val):
    '''Convert val to a float if possible.'''
    try:
        return float(val)
    except ValueError:
        return val

def extract_tagged_data(data_tag, filename):
    '''Extract data from lines marked by the data_tag in filename.'''
    if not os.path.exists(filename):
        err = 'Cannot extract data: file %s does not exist.' % (filename)
        raise exceptions.RunError(err)
    data_file = open(filename)
    # Data tag is the first non-space character in the line.
    # e.g. extract data from lines:
    # data_tag      Energy:    1.256743 a.u.
    data_tag_regex = re.compile('^ *%s' % (re.escape(data_tag)))
    data = {}
    for line in data_file.readlines():
        if data_tag_regex.match(line):
            # This is a line containing info to be tested.
            words = line.split()
            key = []
            # name of data is string after the data_tag and preceeding the
            # (numerical) data.  only use the first number in the line, with
            # the key taken from all proceeding information.
            for word in words[1:]:
                val = try_floatify(word)
                if val != word:
                    break
                else:
                    key.append(word)
            if key[-1] in ("=",':'):
                key.pop()
            key = '_'.join(key)
            if key[-1] in ("=",':'):
                key = key[:-1]
            if not key:
                key = 'data'
            if key in data:
                data[key].append(val)
            else:
                data[key] = [val]
    return [data]
