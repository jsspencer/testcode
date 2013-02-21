'''
testcode2.validation
--------------------

Classes and functions for comparing data.

:copyright: (c) 2012 James Spencer.
:license: modified BSD; see LICENSE for more details.
'''

import testcode2.compatibility as compat

class Tolerance:
    '''Store absolute and relative tolerances

Given floats are regarded as equal if they are within these tolerances.'''
    def __init__(self, absolute=None, relative=None):
        self.absolute = absolute
        self.relative = relative
    def validate(self, test_val, benchmark_val, key=''):
        '''Compare test and benchmark values to within the tolerances.'''
        passed = True
        msg = 'values are within tolerance.'
        try:
            # Check float is not NaN (which we can't compare).
            if compat.isnan(test_val) or compat.isnan(benchmark_val):
                passed = False
                msg = 'cannot compare NaNs.'
            else:
                # Check if values are within tolerances.
                diff = test_val - benchmark_val
                if self.absolute:
                    err = abs(diff)
                    passed = err < self.absolute
                    if not passed:
                        msg = ('absolute error %.2e greater than %.2e.' %
                                (err, self.absolute))
                if self.relative:
                    if benchmark_val == 0 and diff == 0:
                        err = 0
                    elif benchmark_val == 0:
                        err = float("Inf")
                    else:
                        err = abs(diff/benchmark_val)
                    passed = err < self.relative
                    if not passed:
                        msg = ('relative error %.2e greater than %.2e.' %
                                (err, self.relative))
        except TypeError:
            if test_val != benchmark_val:
                # require test and benchmark values to be equal (within python's
                # definition of equality).
                passed = False
                msg = 'values are different.'
        if key:
            msg = '%s: %s' % (key, msg)
        return (passed, msg)

def compare_data(benchmark, test, default_tolerance, tolerances,
        ignore_fields=None):
    '''Compare two data dictionaries.'''
    if ignore_fields:
        for field in ignore_fields:
            benchmark.pop([field])
            test.pop([field])
    nitems = lambda data_dict: [len(val) for (key, val)
                                                in sorted(data_dict.items())]
    if sorted(benchmark.keys()) != sorted(test.keys()) or \
            nitems(benchmark) != nitems(test):
        status = -1
        msg = 'Different sets of data extracted from benchmark and test.'
    else:
        status = 0
        msg = []
        # Test keys are same.
        # Compare each field (unless we're ignoring it).
        for key in benchmark.keys():
            if key in tolerances.keys():
                tol = tolerances[key]
            else:
                tol = default_tolerance
            for ind in range(len(benchmark[key])):
                (key_passed, err) = tol.validate(
                        test[key][ind], benchmark[key][ind], key)
                if not key_passed:
                    status += 1
                if not key_passed and err:
                    msg.append(err)
        msg = '\n'.join(msg)
    return (status, msg)
