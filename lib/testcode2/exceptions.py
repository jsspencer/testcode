'''Custom exceptions.  Initialise signal handler for the interrupt signal'''

import signal
import sys

def signal_handler(interrupt_signal, frame):
    '''Capture interupt signal and leave quietly.'''
    print('Signal: %s has been caught.  Bye!' % (interrupt_signal))
    sys.exit(1)


class RunError(Exception):
    '''Exception used for errors running test jobs.'''
    pass


class TestCodeError(Exception):
    '''Top level exception for testcode errors.'''
    pass

signal.signal(signal.SIGINT, signal_handler) # Listen out for Ctrl-C. 
