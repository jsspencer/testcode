'''testcode2, a framework for regression testing numerical programs.'''

import glob
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
import testcode2.validation as validation

DIR_LOCK = dir_lock.DirLock()
FILESTEM = dict(
                 test = 'test.out',
                 error = 'test.err',
                 benchmark = 'benchmark.out',
               )

class TestProgram:
    '''Store and access information about the program being tested.'''
    def __init__(self, name, exe, test_id, benchmark, **kwargs):

        # Set sane defaults (mostly null) for keyword arguments.

        self.name = name

        # Running
        self.exe = exe
        self.test_id = test_id
        self.run_cmd_template = ('tc.program tc.args tc.input > '
                                                    'tc.output 2> tc.error')
        self.launch_parallel = 'mpirun'
        self.submit_template = None

        # dummy job with default settings (e.g tolerance)
        self.default_test_settings = None

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

        # Set values passed in as keyword options.
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
        if nprocs > 0 and self.launch_parallel:
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
    def __init__(self, test_program, path, **kwargs):

        # program
        self.test_program = test_program

        # running
        self.path = path
        self.inputs_args = None
        self.output = None
        self.nprocs = 0
        self.override_nprocs = False

        # Analysis
        self.default_tolerance = None
        self.tolerances = {}
        self.status = dict(passed=0, ran=0)

        # Set values passed in as keyword options.
        for (attr, val) in kwargs.items():
            setattr(self, attr, val)

        # 'Decorate' functions which require a directory lock in order for file
        # access to be thread-safe.
        # As we use the in_dir decorator, which requires knowledge of the test
        # directory (a per-instance property), we cannot use the @decorator
        # syntactic sugar.  Fortunately we can still modify them at
        # initialisation time.  Thank you python for closures!
        self.start_job = DIR_LOCK.in_dir(self.path)(self._start_job)
        self.verify_job = DIR_LOCK.in_dir(self.path)(self._verify_job)

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
                job = self.start_job(test, cluster_queue, verbose)
                job.wait()
                # Analyse tests as they finish.
                if cluster_queue:
                    # Did all of them at once.
                    for (test_input, test_arg) in self.inputs_args:
                        self.verify_job(test_input, test_arg, verbose)
                else:
                    # Did one job at a time.
                    (test_input, test_arg) = self.inputs_args[ind]
                    if self.output:
                        shutil.move(self.output, test_files[ind])
                    self.verify_job(test_input, test_arg, verbose)
        except exceptions.RunError:
            err = sys.exc_info()[1]
            err = 'Test(s) in %s failed.\n%s' % (self.path, err)
            self._update_status(False)
            util.print_success(False, err, verbose)

    def _start_job(self, cmd, cluster_queue=None, verbose=True):
        '''Start test running.  Requires directory lock.

IMPORTANT: use self.start_job rather than self._start_job if using multiple
threads.

Decorated to start_job, which acquires directory lock and enters self.path
first, during initialisation.'''

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

    def _verify_job(self, input_file, args, verbose=True):
        '''Check job against benchmark.

Assume function is executed in self.path.

IMPORTANT: use self.verify_job rather than self._verify_job if using multiple
threads.

Decorated to verify_job, which acquires directory lock and enters self.path
first, during initialisation.'''
        if self.test_program.verify:
            (passed, msg) = self.verify_job_external(input_file, args, verbose)
        else:
            (bench_out, test_out) = self.extract_data(input_file, args, verbose)
            (status, msg) = validation.compare_data(bench_out, test_out,
                    self.default_tolerance, self.tolerances)
            if status < 0:
                # Print dictionaries separately.
                data_table = '\n'.join((
                            util.pretty_print_table(['benchmark'], [bench_out]),
                            util.pretty_print_table(['test     '], [test_out])))
            else:
                # Combine test and benchmark dictionaries.
                data_table = util.pretty_print_table( ['benchmark', 'test'],
                                                      [bench_out, test_out])
            passed = status == 0
            if msg.strip():
                # join data table with error message from
                # validation.compare_data.
                msg = '\n'.join((msg, data_table))
            else:
                msg = data_table

        self._update_status(passed)
        util.print_success(passed, msg, verbose)

        return (passed, msg)

    def verify_job_external(self, input_file, args, verbose=True):
        '''Run user-supplied verifier script.

Assume function is executed in self.path.'''
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
        output = verify_popen.communicate()[0].decode('utf-8')
        if verify_popen.returncode == 0:
            return (True, output)
        else:
            return (False, output)

    def extract_data(self, input_file, args, verbose=True):
        '''Extract data from output file.

Assume function is executed in self.path.'''
        tp_ptr = self.test_program
        if tp_ptr.data_tag:
            # Using internal data extraction function.
            data_files = [
                    util.testcode_filename(FILESTEM['test'],
                            tp_ptr.test_id, input_file, args),
                    util.testcode_filename(FILESTEM['benchmark'],
                            tp_ptr.benchmark, input_file, args),
                         ]
            outputs = [util.extract_tagged_data(tp_ptr.data_tag, dfile)
                    for dfile in data_files]
        else:
            # Using external data extraction script.
            # Get extraction commands.
            extract_cmds = self.test_program.extract_cmd(input_file, args)

            # Extract data.
            outputs = []
            for cmd in extract_cmds:
                try:
                    if verbose:
                        print('Analysing output using %s in %s.' %
                                (cmd, self.path))
                    extract_popen = subprocess.Popen(cmd, shell=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    extract_popen.wait()
                except OSError:
                    # slightly odd syntax in order to be compatible with python
                    # 2.5 and python 2.6/3
                    err = 'Analysing output failed: %s' % (sys.exc_info()[1],)
                    raise exceptions.RunError(err)
                # Convert data string from extract command to dictionary format.
                if extract_popen.returncode != 0:
                    err = extract_popen.communicate()[1].decode('utf-8')
                    err = 'Analysing output failed: %s' % (err)
                    raise exceptions.RunError(err)
                table_string = extract_popen.communicate()[0].decode('utf-8')
                outputs.append(util.dict_table_string(table_string))

        return tuple(outputs)

    def create_new_benchmarks(self, benchmark, copy_files_since=None,
            copy_files_path='testcode_data'):
        '''Copy the test files to benchmark files.'''

        oldcwd = os.getcwd()
        os.chdir(self.path)

        for (inp, arg) in self.inputs_args:
            test_file = util.testcode_filename(FILESTEM['test'],
                    self.test_program.test_id, inp, arg)
            bench_file = util.testcode_filename(FILESTEM['benchmark'],
                    benchmark, inp, arg)
            shutil.copy(test_file, bench_file)

        if copy_files_since:
            if not os.path.isdir(copy_files_path):
                os.mkdir(copy_files_path)
            if os.path.isdir(copy_files_path):
                for data_file in glob.glob('*'):
                    if (os.path.isfile(data_file) and
                            os.stat(data_file)[-2] >= copy_files_since):
                        bench_data_file = os.path.join(copy_files_path,
                                data_file)
                        # shutil.copy can't overwrite files so remove old ones
                        # with the same name.
                        if os.path.exists(bench_data_file):
                            os.unlink(bench_data_file)
                        shutil.copy(data_file, bench_data_file)

        os.chdir(oldcwd)

    def _update_status(self, passed):
        '''Update self.status with success of a test.'''
        self.status['ran'] += 1
        if passed:
            self.status['passed'] += 1
