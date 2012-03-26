'''Threading lock initialisation and helper.'''

import os
from threading import Lock as threadingLock
import testcode2.compatibility as compat

class Lock:
    '''Helper class for working with threading locks.'''
    def __init__(self):
        self.lock = threadingLock()
    def with_lock(self, func):
        '''Decorate function to be executed whilst holding the lock.'''
        @compat.functools.wraps(func)
        def decorated_func(*args, **kwargs):
            '''Function decorated by Lock.with_lock.'''
            self.lock.acquire()
            try:
                return func(*args, **kwargs)
            finally:
                self.lock.release()
        return decorated_func
    def in_dir(self, ddir):
        '''Decorate function so it is executed in the given directory ddir.

The thread executing the function holds the lock whilst entering ddir and
executing the function.  This makes such actions thread-safe with respect to
the directory location but is not appropriate for computationally-demanding
functions.'''
        # Because we wish to use this as a decorator with arguments passed to
        # the decorator, we must return a wrapper function which in turn
        # returns the decorated function.  See the excellent explanation of
        # decorators at: http://stackoverflow.com/a/1594484
        def wrapper(func):
            '''Wrap func to hold lock whilst being executed in ddir.'''
            @compat.functools.wraps(func)
            @self.with_lock
            def decorated_func(*args, **kwargs):
                '''Function decorated by Lock.in_dir.'''
                cwd = os.getcwd()
                os.chdir(ddir)
                val = func(*args, **kwargs)
                os.chdir(cwd)
                return val
            return decorated_func
        return wrapper
