'''
testcode2.validation
--------------------

Classes and functions for comparing data.

:copyright: (c) 2012 James Spencer.
:license: modified BSD; see LICENSE for more details.
'''

import sys

import testcode2.ansi as ansi
import testcode2.compatibility as compat
import testcode2.exceptions as exceptions

class Status:
    '''Enum-esque object for storing whether an object passed a comparison.

bools: iterable of boolean objects.  If all booleans are True (False) then the
       status is set to pass (fail) and if only some booleans are True, the
       status is set to warning (partial pass).
status: existing status to use.  bools is ignored if status is supplied.
name: name of status (unknown, skipped, passed, partial, failed) to use.
      Setting name overrides bools and status.
'''
    def __init__(self, bools=None, status=None, name=None):
        (self._unknown, self._skipped) = (-2, -1)
        (self._passed, self._partial, self._failed) = (0, 1, 2)
        if name is not None:
            setattr(self, 'status', getattr(self, '_'+name))
        elif status is not None:
            self.status = status
        elif bools:
            if compat.compat_all(bools):
                self.status = self._passed
            elif compat.compat_any(bools):
                self.status = self._partial
            else:
                self.status = self._failed
        else:
            self.status = self._unknown
    def unknown(self):
        '''Return true if stored status is unknown.'''
        return self.status == self._unknown
    def skipped(self):
        '''Return true if stored status is skipped.'''
        return self.status == self._skipped
    def passed(self):
        '''Return true if stored status is passed.'''
        return self.status == self._passed
    def warning(self):
        '''Return true if stored status is a partial pass.'''
        return self.status == self._partial
    def failed(self):
        '''Return true if stored status is failed.'''
        return self.status == self._failed
    def print_status(self, msg=None, verbose=1, vspace=True):
        '''Print status.

msg: optional message to print out after status.
verbose: 0: suppress all output except for . (for pass), U (for unknown),
            W (for warning/partial pass) and F (for fail) without a newline.
         1: print 'Passed', 'Unknown', 'WARNING' or '**FAILED**'.
         2: as for 1 plus print msg (if supplied).
         3: as for 2 plus print a blank line.
vspace: print out extra new line afterwards if verbose > 1.
'''
        if verbose > 0:
            if self.status == self._unknown:
                print('Unknown.')
            elif self.status == self._passed:
                print('Passed.')
            elif self.status == self._skipped:
                print('%s.' % ansi.ansi_format('SKIPPED', 'blue'))
            elif self.status == self._partial:
                print('%s.' % ansi.ansi_format('WARNING', 'blue'))
            else:
                print('%s.' % ansi.ansi_format('**FAILED**', 'red', 'normal', 'bold'))
            if msg and verbose > 1:
                print(msg)
            if vspace and verbose >  1:
                print('')
        else:
            if self.status == self._unknown:
                sys.stdout.write('U')
            elif self.status == self._skipped:
                sys.stdout.write('S')
            elif self.status == self._passed:
                sys.stdout.write('.')
            elif self.status == self._partial:
                sys.stdout.write('W')
            else:
                sys.stdout.write('F')
            sys.stdout.flush()
    def __add__(self, other):
        '''Add two status objects.

Return the maximum level (ie most "failed") status.'''
        return Status(status=max(self.status, other.status))

class Tolerance:
    '''Store absolute and relative tolerances

Given are regarded as equal if they are within these tolerances.

absolute: threshold for absolute difference between two numbers.
relative: threshold for relative difference between two numbers.
strict: if true, then require numbers to be within both thresholds.
'''
    def __init__(self, absolute=None, relative=None, strict=True):
        self.absolute = absolute
        self.relative = relative
        if not self.absolute and not self.relative:
            err = 'Neither absolute nor relative tolerance given.'
            raise exceptions.TestCodeError(err)
        self.strict = strict
    def __repr__(self):
        return (self.absolute, self.relative, self.strict).__repr__()
    def validate(self, test_val, benchmark_val, key=''):
        '''Compare test and benchmark values to within the tolerances.'''
        status = Status([True])
        msg = ['values are within tolerance.']
        compare = '(Test: %s.  Benchmark: %s.)' % (test_val, benchmark_val)
        try:
            # Check float is not NaN (which we can't compare).
            if compat.isnan(test_val) or compat.isnan(benchmark_val):
                status = Status([False])
                msg = ['cannot compare NaNs.']
            else:
                # Check if values are within tolerances.
                (status_absolute, msg_absolute) = \
                        self.validate_absolute(benchmark_val, test_val)
                (status_relative, msg_relative) = \
                        self.validate_relative(benchmark_val, test_val)
                if self.absolute and self.relative and not self.strict:
                    # Require only one of thresholds to be met.
                    status = Status([status_relative.passed(),
                                     status_absolute.passed()])
                else:
                    # Only have one or other of thresholds (require active one
                    # to be met) or have both and strict mode is on (require
                    # both to be met).
                    status = status_relative + status_absolute
                err_stat = ''
                if status.warning():
                    err_stat = 'Warning: '
                elif status.failed():
                    err_stat = 'ERROR: '
                msg = []
                if self.absolute and msg_absolute:
                    msg.append('%s%s %s' % (err_stat, msg_absolute, compare))
                if self.relative and msg_relative:
                    msg.append('%s%s %s' % (err_stat, msg_relative, compare))
        except TypeError:
            if test_val != benchmark_val:
                # require test and benchmark values to be equal (within python's
                # definition of equality).
                status = Status([False])
                msg = ['values are different. ' + compare]
        if key and msg:
            msg.insert(0, key)
            msg = '\n    '.join(msg)
        else:
            msg = '\n'.join(msg)
        return (status, msg)

    def validate_absolute(self, benchmark_val, test_val):
        '''Compare test and benchmark values to the absolute tolerance.'''
        if self.absolute:
            diff = test_val - benchmark_val
            err = abs(diff)
            passed = err < self.absolute
            msg = ''
            if not passed:
                msg = ('absolute error %.2e greater than %.2e.' %
                    (err, self.absolute))
        else:
            passed = True
            msg = 'No absolute tolerance set.  Passing without checking.'
        return (Status([passed]), msg)

    def validate_relative(self, benchmark_val, test_val):
        '''Compare test and benchmark values to the relative tolerance.'''
        if self.relative:
            diff = test_val - benchmark_val
            if benchmark_val == 0 and diff == 0:
                err = 0
            elif benchmark_val == 0:
                err = float("Inf")
            else:
                err = abs(diff/benchmark_val)
            passed = err < self.relative
            msg = ''
            if not passed:
                msg = ('relative error %.2e greater than %.2e.' %
                        (err, self.relative))
        else:
            passed = True
            msg = 'No relative tolerance set.  Passing without checking.'
        return (Status([passed]), msg)


def compare_data(benchmark, test, default_tolerance, tolerances,
        ignore_fields=None):
    '''Compare two data dictionaries.'''
    ignored_params = compat.compat_set(ignore_fields or tuple())
    bench_params = compat.compat_set(benchmark) - ignored_params
    test_params = compat.compat_set(test) - ignored_params
    comparable = (bench_params == test_params)
    status = Status()
    msg = []
    
    if not comparable:
        status = Status([False])
        bench_only = bench_params - test_params
        test_only = test_params - bench_params
        msg.append('Different sets of data extracted from benchmark and test.')
        if bench_only:
            msg.append("    Data only in benchmark: %s." % ", ".join(bench_only))
        if test_only:
            msg.append("    Data only in test: %s." % ", ".join(test_only))

    for param in (bench_params & test_params):
        tol = tolerances.get(param, default_tolerance)
        for bench_value, test_value in zip(benchmark[param], test[param]):
            key_status, err = tol.validate(bench_value, test_value, param)
            status += key_status
            if not key_status.passed() and err:
                msg.append(err)

    return (comparable, status, "\n".join(msg))
