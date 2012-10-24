'''
testcode2
---------

A framework for regression testing numerical programs.

:copyright: (c) 2012 James Spencer.
:license: modified BSD; see LICENSE for more details.
'''

import glob
import os
import pipes
import shutil
import subprocess
import sys

try:
    import yaml
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False

import testcode2.dir_lock as dir_lock
import testcode2.exceptions as exceptions
import testcode2.queues  as queues
import testcode2.compatibility as compat
import testcode2.util as util
import testcode2.validation as validation

DIR_LOCK = dir_lock.DirLock()

# Do not change!  Bad things will happen...
_FILESTEM_TUPLE = (
                    ('test', 'test.out'),
                    ('error', 'test.err'),
                    ('benchmark', 'benchmark.out'),
                  )
# We can change FILESTEM if needed.
# However, this should only be done to compare two sets of test output or two
# sets of benchmarks.
# Bad things will happen if tests are run without the default FILESTEM!
FILESTEM = dict( _FILESTEM_TUPLE )

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
        self.launch_parallel = 'mpirun -np tc.nprocs'
        self.submit_template = None
        self.submit_pattern = 'testcode.run_cmd'

        # dummy job with default settings (e.g tolerance)
        self.default_test_settings = None

        # Analysis
        self.benchmark = benchmark
        self.ignore_fields = []
        self.data_tag = None
        self.extract_cmd_template = 'tc.extract tc.args tc.file'
        self.extract_program = None
        self.extract_args = ''
        self.extract_fmt = 'table'
        self.verify = False

        # Info
        self.vcs = None

        # Set values passed in as keyword options.
        for (attr, val) in kwargs.items():
            setattr(self, attr, val)

        # If using an external verification program, then set the default
        # extract command template.
        if self.verify and 'extract_cmd_template' not in kwargs:
            self.extract_cmd_template = 'tc.extract tc.args tc.test tc.bench'

        # Can we actually extract the data?
        if self.extract_fmt == 'yaml' and not _HAVE_YAML:
            err = 'YAML data format cannot be used: PyYAML is not installed.'
            raise exceptions.TestCodeError(err)

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
            cmd = '%s %s' % (self.launch_parallel, cmd)
        cmd = cmd.replace('tc.nprocs', str(nprocs))
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
        self.min_nprocs = 0
        self.max_nprocs = compat.maxint

        # Analysis
        self.default_tolerance = None
        self.tolerances = {}

        # Set values passed in as keyword options.
        for (attr, val) in kwargs.items():
            setattr(self, attr, val)

        if not self.inputs_args:
            self.inputs_args = [('', '')]

        self.status = dict( (inp_arg, [False, False])
                                            for inp_arg in self.inputs_args )

        # 'Decorate' functions which require a directory lock in order for file
        # access to be thread-safe.
        # As we use the in_dir decorator, which requires knowledge of the test
        # directory (a per-instance property), we cannot use the @decorator
        # syntactic sugar.  Fortunately we can still modify them at
        # initialisation time.  Thank you python for closures!
        self.start_job = DIR_LOCK.in_dir(self.path)(self._start_job)
        self.move_output_to_test_output = DIR_LOCK.in_dir(self.path)(
                                               self._move_output_to_test_output)
        self.move_old_output_files = DIR_LOCK.in_dir(self.path)(
                                               self._move_old_output_files)
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

            # Move files matching output pattern out of the way.
            self.move_old_output_files(verbose)

            # Run tests one-at-a-time locally or submit job in single submit
            # file to a queueing system.
            if cluster_queue:
                if self.output:
                    for (ind, test) in enumerate(test_cmds):
                        # Don't quote self.output if it contains any wildcards
                        # (assume the user set it up correctly!)
                        out = self.output
                        if not compat.compat_any(wild in self.output for wild in
                                ['*', '?', '[', '{']):
                            out = pipes.quote(self.output)
                        test_cmds[ind] = '%s; mv %s %s' % (test_cmds[ind],
                                out, pipes.quote(test_files[ind]))
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
                        self.move_output_to_test_output(test_files[ind])
                    self.verify_job(test_input, test_arg, verbose)
        except exceptions.RunError:
            err = sys.exc_info()[1]
            err = 'Test(s) in %s failed.\n%s' % (self.path, err)
            self._update_status(False, (test_input, test_arg))
            util.print_success(False, err, verbose)

    def _start_job(self, cmd, cluster_queue=None, verbose=True):
        '''Start test running.  Requires directory lock.

IMPORTANT: use self.start_job rather than self._start_job if using multiple
threads.

Decorated to start_job, which acquires directory lock and enters self.path
first, during initialisation.'''

        if cluster_queue:
            tp_ptr = self.test_program
            submit_file = '%s.%s' % (os.path.basename(tp_ptr.submit_template),
                                                                tp_ptr.test_id)
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
                print('Running test using %s in %s\n' % (cmd, self.path))
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

    def _move_output_to_test_output(self, test_files_out):
        '''Move output to the testcode output file.  Requires directory lock.

This is used when a program writes to standard output rather than to STDOUT.

IMPORTANT: use self.move_output_to_test_output rather than
self._move_output_to_test_output if using multiple threads.

Decorated to move_output_to_test_output, which acquires the directory lock and
enters self.path.
'''
        # self.output might be a glob which works with e.g.
        #   mv self.output test_files[ind]
        # if self.output matches only one file.  Reproduce that
        # here so that running tests through the queueing system
        # and running tests locally have the same behaviour.
        out_files = glob.glob(self.output)
        if len(out_files) == 1:
            shutil.move(out_files[0], test_files_out)
        else:
            err = ('Output pattern (%s) matches %s files (%s).'
                     % (self.output, len(out_files), out_files))
            raise exceptions.RunError(err)

    def _move_old_output_files(self, verbose):
        '''Move output to the testcode output file.  Requires directory lock.

This is used when a program writes to standard output rather than to STDOUT.

IMPORTANT: use self.move_oold_output_files rather than
self._move_old_output_files if using multiple threads.

Decorated to move_old_output_files, which acquires the directory lock and
enters self.path.
'''
        if self.output:
            old_out_files = glob.glob(self.output)
            if old_out_files:
                out_dir = 'test.prev.output.%s' % (self.test_program.test_id)
                if verbose:
                    print('WARNING: found existing files matching output '
                          'pattern: %s.' % self.output)
                    print('WARNING: moving existing output files (%s) to %s.\n'
                          % (', '.join(old_out_files), out_dir))
                if not os.path.exists(out_dir):
                    os.mkdir(out_dir)
                for out_file in old_out_files:
                    shutil.move(out_file, out_dir)

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

        self._update_status(passed, (input_file, args))
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
                    util.testcode_filename(FILESTEM['benchmark'],
                            tp_ptr.benchmark, input_file, args),
                    util.testcode_filename(FILESTEM['test'],
                            tp_ptr.test_id, input_file, args),
                         ]
            if verbose:
                print('Analysing output using data_tag %s in %s on files %s.' %
                        (tp_ptr.data_tag, self.path, ' and '.join(data_files)))
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
                data_string = extract_popen.communicate()[0].decode('utf-8')
                if self.test_program.extract_fmt == 'table':
                    outputs.append(util.dict_table_string(data_string))
                elif self.test_program.extract_fmt == 'yaml':
                    outputs.append(yaml.safe_load(data_string))
                    # convert values to be in a tuple so the format matches
                    # that from dict_table_string.
                    for (key, val) in outputs[-1].items():
                        if isinstance(val, list):
                            outputs[-1][key] = tuple(val)
                        else:
                            outputs[-1][key] = tuple((val,))

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

    def _update_status(self, passed, inp_arg):
        '''Update self.status with success of a test.'''
        self.status[inp_arg][0] = True
        if passed:
            self.status[inp_arg][1] = True

    def get_status(self):
        '''Get number of passed and number of ran tasks.'''
        nran = sum(task[0] for task in self.status.values())
        npassed = sum(task[1] for task in self.status.values())
        return (npassed, nran)
