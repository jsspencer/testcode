'''testcode2, a framework for regression testing numerical programs.'''

import os
import pipes
import shutil
import subprocess
import sys

import testcode2.dir_lock as dir_lock
import testcode2.exceptions as exceptions
import testcode2.queues  as queues
import testcode2.compatibility as compat
import testcode2.util as util

DIR_LOCK = dir_lock.DirLock()
FILESTEM = dict(
                 test = 'test.out',
                 error = 'test.err',
                 benchmark = 'benchmark.out',
               )

class TestProgram:
    '''Store and access information about the program being tested.'''
    def __init__(self, exe, test_id, benchmark, **kwargs):

        # Set null defaults for keyword arguments.

        # Running
        self.exe = exe
        self.test_id = test_id
        self.run_cmd_template = 'tc.program tc.args tc.input > tc.output 2> tc.error'
        self.launch_parallel = None
        self.submit_template = None

        # Analysis
        self.benchmark = benchmark
        self.ignore_fields = []
        self.data_tag = None
        self.extract_cmd_template = 'tc.extract tc.args tc.file'
        self.extract_program = None
        self.extract_args = ''
        self.verify = False

        # Info
        self.vcs = None

        for (attr, val) in kwargs.items():
            setattr(self, attr, val)

    def run_cmd(self, input_file, args, nprocs=0):
        '''Create run command.'''
        output_file = util.testcode_filename(FILESTEM['test'], self.test_id,
                input_file, args)
        error_file = util.testcode_filename(FILESTEM['error'], self.test_id,
                input_file, args)

        # Need to escape filenames for passing them to the shell.
        exe = pipes.quote(self.exe)
        output_file = pipes.quote(output_file)
        error_file = pipes.quote(error_file)

        cmd = self.run_cmd_template.replace('tc.program', exe)
        if type(input_file) is str:
            input_file = pipes.quote(input_file)
            cmd = cmd.replace('tc.input', input_file)
        else:
            cmd = cmd.replace('tc.input', '')
        if type(args) is str:
            cmd = cmd.replace('tc.args', args)
        else:
            cmd = cmd.replace('tc.args', '')
        cmd = cmd.replace('tc.output', output_file)
        cmd = cmd.replace('tc.error', error_file)
        if nprocs != 0 and self.launch_parallel:
            cmd = '%s -np %s %s' % (self.launch_parallel, nprocs, cmd)
        return cmd

    def extract_cmd(self, input_file, args):
        '''Create extraction command(s).'''
        test_file = util.testcode_filename(FILESTEM['test'], self.test_id,
                input_file, args)
        bench_file = util.testcode_filename(FILESTEM['benchmark'],
                self.benchmark, input_file, args)
        cmd = self.extract_cmd_template
        cmd = cmd.replace('tc.extract', pipes.quote(self.extract_program))
        cmd = cmd.replace('tc.args', self.extract_args)
        if self.verify:
            # Single command to compare benchmark and test outputs.
            cmd = cmd.replace('tc.test', pipes.quote(test_file))
            cmd = cmd.replace('tc.bench', pipes.quote(bench_file))
            return (cmd,)
        else:
            # Need to return commands to extract data from the test and
            # benchmark outputs.
            test_cmd = cmd.replace('tc.file', pipes.quote(test_file))
            bench_cmd = cmd.replace('tc.file', pipes.quote(bench_file))
            return (bench_cmd, test_cmd)

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
            test_files = []
            bench_files = []
            for (test_input, test_arg) in self.inputs_args:
                if (test_input and 
                        not os.path.exists(os.path.join(self.path,test_input))):
                    err = 'Input file does not exist: %s' % (test_input,)
                    raise exceptions.RunError(err)
                test_cmds.append(self.test_program.run_cmd(test_input, test_arg,
                                                           self.nprocs))
                test_files.append(util.testcode_filename(FILESTEM['test'],
                        self.test_program.test_id, test_input, test_arg))
                bench_files.append(util.testcode_filename(FILESTEM['benchmark'],
                    self.test_program.test_id, test_input, test_arg))

            # Run tests one-at-a-time locally or submit job in single submit
            # file to a queueing system.
            if cluster_queue:
                if self.output:
                    for (ind, test) in enumerate(test_cmds):
                        test_cmds[ind] = '%s; mv %s %s' % (test_cmds[ind],
                                pipes.quote(self.output),
                                pipes.quote(test_files[ind]))
                test_cmds = ['\n'.join(test_cmds)]
            for (ind, test) in enumerate(test_cmds):
                job = self.start_job(test) #, cluster_queue, verbose)
                job.wait()
                # Analyse tests as they finish.
                if cluster_queue:
                    # Did all of them at once.
                    for (test_input, test_arg) in self.inputs_args:
                        (passed, msg) = self.verify_job(verbose)
                        self.print_job_success(verbose, passed, msg)
                else:
                    # Did one job at a time.
                    (test_input, test_arg) = self.inputs_args[ind]
                    if self.output:
                        shutil.move(self.output, test_files[ind])
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

    def _verify_job_external(self, input_file, args, verbose=True):
        '''Run user-supplied verifier script.  Requires directory lock.

IMPORTANT: use self.verify_external rather than self._verify_job_external if
using multiple threads.

Decorated as verify_job_external to acquire directory lock and enter self.path
during initialisation.'''
        verify_cmd = self.test_program.extract_cmd(input_file, args)[0]
        try:
            if verbose:
                print('Analysing test using %s in %s.' %
                        (verify_cmd, self.path))
            verify_popen = subprocess.Popen(verify_cmd, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            verify_popen.wait()
        except OSError:
            # slightly odd syntax in order to be compatible with python 2.5
            # and python 2.6/3
            err = 'Execution of test failed: %s' % (sys.exc_info()[1],)
            raise exceptions.RunError(err)
        output = verify_popen.communicate()[0]
        if verify_popen.returncode == 0:
            return (True, output)
        else:
            return (False, output)

    def _extract_data(self, input_file, args, verbose=True):
        '''Extract data from output file.  Requires directory lock.

IMPORTANT: use self.extract_data rather than self._extract_data if using
multiple threads.

Decorated as extract_data to acquire directory lock and enter self.path during
initialisation.'''

        # Get extraction commands.
        extract_cmds = self.test_program.extract_cmd(input_file, args)

        # Extract data.
        outputs = []
        for cmd in extract_cmds:
            try:
                if verbose:
                    print('Analysing output using %s in %s.' % (cmd, self.path))
                extract_popen = subprocess.Popen(cmd, shell=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                extract_popen.wait()
            except OSError:
                # slightly odd syntax in order to be compatible with python 2.5
                # and python 2.6/3
                err = 'Execution of test failed: %s' % (sys.exc_info()[1],)
                raise exceptions.RunError(err)
            outputs.append(extract_popen.communicate()[0])
        return outputs

    def print_job_success(self, passed, verbose, msg):
        '''Print output from comparing test job to benchmark.'''
        pass
