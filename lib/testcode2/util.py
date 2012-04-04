'''Utility functions.'''

import os.path
import re
import sys

import testcode2.compatibility as compat
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
    # We shouldn't change the data from this point: convert entries to tuples.
    for (key, val) in data.items():
        data[key] = tuple(val)
    return data

def dict_table_string(table_string):
    '''Read a data table from a string into a dictionary.

The first row and any subsequent rows containing no numbers are assumed to form
headers of a subtable, and so form the keys for the subsequent subtable.

Values, where possible, are converted to floats.

e.g. a  b  c  a  ->   {'a':(1,4,7,8), 'b':(2,5), 'c':(3,6)}
     1  2  3  7
     4  5  6  8
and
     a  b  c   ->   {'a':(1,4,7), 'b':(2,5,8), 'c':(3,6), 'd':(9), 'e':(6)}
     1  2  3
     4  5  6
     a  b  d  e
     7  8  9  6
'''
    data = [i.split() for i in table_string.splitlines()]
    # Convert to numbers where appropriate
    data = [[try_floatify(val) for val in dline] for dline in data]
    data_dict = {}
    for dline in data:
        # Test if all items are strings; if so start a new subtable.
        # We actually test if all items are not floats, as python 3 can return
        # a bytes variable from subprocess whereas (e.g.) python 2.4 returns a
        #  str.  Testing for this is problematic as the bytes type does not
        # exist in python 2.4.  Fortunately we have converted all items to
        # floats if possible, so can just test for the inverse condition...
        if compat.compat_all(type(val) is not float for val in dline):
            # header of new subtable
            head = dline
            for val in head:
                if val not in data_dict:
                    data_dict[val] = []
        else:
            for (ind, val) in enumerate(dline):
                # Add data to appropriate key.
                # Note that this handles the case where the same column heading
                # occurs multiple times in the same subtable and does not
                # overwrite the previous column with the same heading.
                data_dict[head[ind]].append(val)
    # We shouldn't change the data from this point: convert entries to tuples.
    for (key, val) in data_dict.items():
        data_dict[key] = tuple(val)
    return data_dict

def print_success(passed, msg, verbose):
    '''Print output from comparing test job to benchmark.'''
    if verbose:
        if passed:
            print('Passed.')
        else:
            print('**FAILED**.')
        if msg:
            print(msg)
    else:
        if passed:
            sys.stdout.write('.')
        else:
            sys.stdout.write('F')
        sys.stdout.flush()
