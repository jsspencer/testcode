'''testcode2, a framework for regression testing numerical programs.'''

import os
import shutil
import subprocess
import sys

import testcode2.dir_lock as dir_lock
import testcode2.exceptions as exceptions
import testcode2.queues  as queues
import testcode2.compatibility as compat

DIR_LOCK = dir_lock.DirLock()
FILESTEM = dict(
                 test = 'test.out',
                 error = 'test.err',
                 benchmark = 'benchmark.out',
               )

class TestProgram:
    '''Store and access information about the program being tested.'''
    def __init__(self, exe, run_cmd_template, test_id, launch_parallel=None,
                       submit_template=None, ignore_fields=None, data_tag=None,
                       extract_cmd=None, verifier_cmd=None, make=None,
                       vcs=None):

        # Running
        self.exe = exe
        self.launch_parallel = launch_parallel
        self.run_cmd_template = run_cmd_template
        self.submit_template = submit_template
        self.test_id = test_id

        # Analysis
        if ignore_fields:
            self.ignore_fields = ignore_fields
        else:
            self.ignore_fields = []
        self.data_tag = data_tag
        self.extract_cmd = extract_cmd
        self.verifier_cmd = verifier_cmd

        # Building
        self.make = make

        # Info
        self.vcs = vcs

    def run_cmd(self, input_file, args, nprocs):
        '''Create run command.'''
        output_file = testcode_filename(FILESTEM['test'], self.test_id,
                                        input_file, args)
        error_file = testcode_filename(FILESTEM['error'], self.test_id,
                                       input_file, args)
        cmd = self.run_cmd_template.replace('testcode.program', self.exe)
        if input_file:
            cmd = cmd.replace('testcode.input', input_file)
        if args:
            cmd = cmd.replace('testcode.args', args)
        cmd = cmd.replace('testcode.output', output_file)
        cmd = cmd.replace('testcode.error', error_file)
        if nprocs != 0 and self.launch_parallel:
            cmd = '%s -np %s %s' % (self.launch_parallel, nprocs, cmd)
        return cmd

class Test:
    '''Store and execute a test.'''
    def __init__(self, path):

        # program
        self.test_program = None

        # running
        self.path = path
        self.inputs_args = None
        self.output = None
        self.nprocs = 0

        # Analysis
        self.tolerance = None

        # 'Decorate' functions which require a directory lock in order for file
        # access to be thread-safe.
        # As we use the in_dir decorator, which requires knowledge of the test
        # directory (a per-instance property), we cannot use the @decorator
        # syntactic sugar.  Fortunately we can still modify them at
        # initialisation time.  Thank you python for closures!
        self.start_job = DIR_LOCK.in_dir(self.path)(self._start_job)
        self.extract_data = DIR_LOCK.in_dir(self.path)(self._extract_data)
        self.verify_job_external = DIR_LOCK.in_dir(self.path)(
                                               self._verify_job_external)

    def run_test(self, verbose=True, cluster_queue=None):
        '''Run all jobs in test.'''

        try:
            # Construct tests.
            test_cmds = []
            for (test_input, test_arg) in self.inputs_args:
                if (test_input and 
                        not os.path.exists(os.path.join(self.path,test_input))):
                    err = 'Input file does not exist: %s' % (test_input,)
                    raise exceptions.RunError(err)
                test_cmds.append(self.test_program.run_cmd(test_input, test_arg,
                                                           self.nprocs))

            # Run tests one-at-a-time locally or submit job in single submit
            # file to a queueing system.
            if cluster_queue:
                if self.output:
                    for (ind, test) in enumerate(test_cmds):
                        test_file = testcode_filename(FILESTEM['test'],
                                self.test_program.test_id,
                                *self.inputs_args[ind])
                        test_cmds[ind] = '%s; mv %s %s' % (test_cmds[ind],
                                self.output, test_file)
                test_cmds = ['\n'.join(test_cmds)]
            for (ind, test) in enumerate(test_cmds):
                print(test, cluster_queue, verbose)
                job = self.start_job(test) #, cluster_queue, verbose)
                job.wait()
                # Analyse tests as they finish.
                if cluster_queue:
                    # Did all of them at once.
                    for (test_input, test_arg) in self.inputs_args:
                        test_file = testcode_filename(FILESTEM['test'],
                                self.test_program.test_id, 
                                test_input, test_arg)
                        bench_file = testcode_filename(FILESTEM['benchmark'],
                                self.test_program.test_id, 
                                test_input, test_arg)
                        (passed, msg) = self.verify_job(verbose)
                        self.print_job_success(verbose, passed, msg)
                else:
                    # Did one job at a time.
                    (test_input, test_arg) = self.inputs_args[ind]
                    test_file = testcode_filename(FILESTEM['test'],
                            self.test_program.test_id, test_input, test_arg)
                    bench_file = testcode_filename(FILESTEM['benchmark'],
                        self.test_program.test_id, test_input, test_arg)
                    if self.output:
                        shutil.move(self.output, test_file)
                    (passed, msg) = self.verify_job(verbose)
                    self.print_job_success(verbose, passed, msg)
        except exceptions.RunError:
            err = sys.exc_info()[1]
            err = 'Test(s) in %s failed.\n%s' % (self.path, err)
            print(err) # TEMP
            self.print_job_success(verbose, False, err)

    def _start_job(self, cmd, cluster_queue=None, verbose=True):
        '''Start test running.  Requires directory lock.

IMPORTANT: use self.start_job rather than self._start_job if using multiple
threads.

Decorated to acquire directory lock and enter self.path during
initialisation.'''

        print('in dir: %s' % os.getcwd())

        if cluster_queue:
            tp_ptr = self.test_program
            submit_file = '%s.%s' % (tp_ptr.submit_template, tp_ptr.test_id)
            job = queues.ClusterQueueJob(submit_file, system=cluster_queue)
            job.create_submit_file(tp_ptr.submit_pattern, cmd, 
                                   tp_ptr.submit_template)
            if verbose:
                print('Submitting tests using %s (template submit file) in %s'
                           % (tp_ptr.submit_template, self.path))
            job.start_job()
        else:
            # Run locally via subprocess.
            if verbose:
                print('Running test using %s in %s' % (cmd, self.path))
            try:
                job = subprocess.Popen(cmd, shell=True)
            except OSError:
                # slightly odd syntax in order to be compatible with python 2.5
                # and python 2.6/3
                err = 'Execution of test failed: %s' % (sys.exc_info()[1],)
                raise exceptions.RunError(err)

        # Return either Popen object or ClusterQueueJob object.  Both have
        # a wait method which returns only once job has finished.
        return job

    def verify_job(self, verbose=True):
        '''Check job against benchmark.'''
        pass

    def _verify_job_external(self):
        '''Run user-supplied verifier script.  Requires directory lock.

IMPORTANT: use self.verify_external rather than self._verify_job_external if
using multiple threads.

Decorated as verify_job_external to acquire directory lock and enter self.path
during initialisation.'''
        pass

    def _extract_data(self, output):
        '''Extract data from output file.  Requires directory lock.

IMPORTANT: use self.extract_data rather than self._extract_data if using
multiple threads.

Decorated as extract_data to acquire directory lock and enter self.path during
initialisation.'''
        pass

    def print_job_success(self, passed, verbose, msg):
        '''Print output from comparing test job to benchmark.'''
        pass

def testcode_filename(stem, test_id, inp, args):
    '''Construct filename in testcode format.'''
    filename = '%s.%s' % (stem, test_id)
    if inp:
        filename = '%s.inp=%s' % (filename, inp)
    if args:
        args_string = args.replace(' ','_')
        filename = '%s.args=%s' % (filename, args_string)
    return filename
