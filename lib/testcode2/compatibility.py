'''Functions for compatibility with python <2.6.'''

### python 2.4 ###

# Import from the sets module if sets are not part of the language.
try:
    compat_set = set
except NameError:
    from sets import Set as compat_set

# Any and all don't exist in python <2.5. Define our own in pure python.
try:
    compat_all = all
except NameError:
    def compat_all(iterable):
        '''all(iterable) -> bool

Return True if bool(x) is True for all values x in the iterable.
'''
        for val in iterable:
            if not val:
                return False
        return True
try:
    compat_any = any
except NameError:
    def compat_any(iterable):
        '''any(iterable) -> bool

Return True if bool(x) is True for any x in the iterable.
'''
        for val in iterable:
            if val:
                return True

try:
    import functools
except ImportError:
    import testcode2._functools_dummy as functools

### python 2.5, python 2.5 ###

# math.isnan was introduced in python 2.6, so need a workaround for 2.4 and 2.5.
try:
    from math import isnan
except ImportError:
    def isnan(val):
        '''Return True if x is a NaN (not a number), and False otherwise.

:param float val: number.

Replacement for math.isnan for python <2.6.
This is not guaranteed to be portable, but does work under Linux.
'''
        return type(val) is float and val != val
