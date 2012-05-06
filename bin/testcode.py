#!/usr/bin/env python

import glob
import optparse
import os
import subprocess
import sys
import threading
import time

try:
    import testcode2
except ImportError:
    # try to find testcode2 assuming it is being run directly from the source
    # layout.
    SCRIPT_DIR = os.path.abspath(os.path.dirname(sys.argv[0]))
    TESTCODE2_LIB = os.path.join(SCRIPT_DIR, '../lib/')
    sys.path.extend([TESTCODE2_LIB])
    import testcode2

import testcode2.config
import testcode2.util
import testcode2.compatibility

#--- testcode initialisation ---

def init_tests(userconfig, jobconfig, test_id, reuse_id, executables=None,
        categories=None, nprocs=0, benchmark=None, userconfig_options=None,
        jobconfig_options=None):

    (user_options, test_programs) = testcode2.config.parse_userconfig(
            userconfig, executables, test_id, userconfig_options)

    # Set benchmark if required.
    if benchmark:
        for key in test_programs:
            test_programs[key].benchmark = benchmark

    (tests, test_categories) = testcode2.config.parse_jobconfig(
            jobconfig, user_options, test_programs, jobconfig_options)

    # Set number of processors...
    if nprocs:
        for test in tests:
            if not test.override_nprocs:
                test.nprocs = nprocs

    # parse selected job categories from command line
    # Remove those tests which weren't run most recently if comparing.
    if categories:
        tests = testcode2.config.select_tests(tests, test_categories,
                categories, os.path.abspath(os.path.dirname(userconfig)))

    if not test_id:
        test_id = testcode2.config.get_unique_test_id(tests, reuse_id,
                user_options['date_fmt'])
        for key in test_programs:
            test_programs[key].test_id = test_id

    return (user_options, test_programs, tests)

#--- create command line interface ---

def parse_cmdline_args(args):

    # Curse not being able to use argparse in order to support python <= 2.7!
    # TODO: usage string.
    parser = optparse.OptionParser()

    allowed_actions = ['compare', 'run', 'diff', 'tidy', 'make-benchmarks']

    parser.add_option('-b', '--benchmark', help='Set the file ID of the '
            'benchmark files.  Default: specified in the [user] section of the '
            'userconfig file.')
    parser.add_option('-c', '--category', action='append', default=[],
            help='Select the category/group of tests.  Can be specified '
            'multiple times.  Default: use the _default_ category if run is an '
            'action unless make-benchmarks is an action.  All other cases use '
            'the _all_ category by default.  The _default_ category contains '
            'all  tests unless otherwise set in the jobconfig file.')
    parser.add_option('-e', '--executable', action='append', default=[],
            help='Set the executable(s) to be used to run the tests.  Can be '
            ' a path or name of an option in the userconfig file, in which'
            ' case all test programs are set to use that value, or in the'
            ' format program_name=value, which affects only the specified'
            ' program.')
    parser.add_option('--jobconfig', default='jobconfig', help='Set path to the'
            ' job configuration file.  Default: %default.')
    parser.add_option('--job-option', action='append', dest='job_option',
            default=[], nargs=3, help='Override/add setting to jobconfig.  '
            'Takes three arguments.  Format: section_name option_name value.  '
            'Default: none.')
    parser.add_option('-n', '--nthreads', type='int', default=1, help='Set the '
            'number of tests to run concurrently.  Default: %default.')
    parser.add_option('--older-than', type='int', dest='older_than', default=14,
            help='Set the age (in days) of files to remove.  '
            'Default: %default days.')
    parser.add_option('-p', '--processors', type='int', dest='nprocs',
            help='Set the number of processors to run each test on.  '
            'Default: run tests as serial jobs.')
    parser.add_option('-q', '--quiet', action='store_false', dest='verbose',
            default=True, help='Print only minimal output.  Default: False.')
    parser.add_option('-s', '--submit', dest='queue_system', default=None,
            help='Submit tests to a queueing system of the specified type.  '
            'Only PBS system is currently implemented.  Default: %default.')
    parser.add_option('-t', '--test-id', dest='test_id', help='Set the file ID '
            'of the test outputs.  Default: unique filename based upon date '
            'if running tests and most recent test_id if comparing tests.')
    parser.add_option('--userconfig', default='userconfig', help='Set path to '
            'the user configuration file.  Default: %default.')
    parser.add_option('--user-option', action='append', dest='user_option',
            default=[], nargs=3, help='Override/add setting to userconfig.  '
            'Takes three arguments.  Format: section_name option_name value.  '
            'Default: none.')

    (options, args) = parser.parse_args(args)

    # Default action.
    if not args or ('make-benchmarks' in args and 'compare' not in args 
            and 'run' not in args):
        # Run tests by default if no action provided.
        # Run tests before creating benchmark by default.
        args.append('run')

    # Default category.
    if not options.category:
        # We quietly filter out tests which weren't run last when diffing
        # or comparing.
        options.category = ['_all_']
        if 'run' in args and 'make-benchmarks' not in args:
            options.category = ['_default_']

    test_args = (arg not in allowed_actions for arg in args)
    if testcode2.compatibility.compat_any(test_args):
        print('At least one action is not understood: %s.' % (' '.join(args)))
        parser.print_usage()
        sys.exit(1)

    # Parse executable option to form dictionary in format expected by
    # parse_userconfig.
    exe = {}
    for item in options.executable:
        words = item.split('=')
        if len(words) == 1:
            # setting executable for all programs (unless otherwise specified)
            exe['_tc_all'] = words[0]
        else:
            # format: program_name=executable
            exe[words[0]] = words[1]
    options.executable = exe

    # Set FILESTEM if test_id refers to a benchmark file or the benchmark
    # refers to a test_id.
    filestem = testcode2.FILESTEM.copy()
    if options.benchmark and options.benchmark[:2] == 't:':
        filestem['benchmark'] = testcode2.FILESTEM['test']
        options.benchmark = options.benchmark[2:]
    if options.test_id and options.test_id == 'b:':
        filestem['test'] = testcode2.FILESTEM['benchmark']
        options.test_id = options.test_id[2:]
    if filestem['test'] != testcode2.FILESTEM['test'] and 'run' in args:
        print('Not allowed to set test filename to be a benchmark filename '
                'when running calculations.')
        sys.exit(1)
    testcode2.FILESTEM = filestem.copy()
    
    # Convert job-options and user-options to dict of dicsts format.
    for item in ['user_option', 'job_option']:
        uj_opt = getattr(options, item)
        opt = dict( (section, {}) for section in 
                testcode2.compatibility.compat_set(opt[0] for opt in uj_opt) )
        for (section, option, value) in uj_opt:
            opt[section][option] = value
        setattr(options, item, opt)

    return (options, args)

#--- actions ---

def run_tests(tests, verbose, cluster_queue=None, nthreads=1):

    # If submitting tests to a queueing system, then each test actually runs
    # independently.  Override nthreads.
    if cluster_queue:
        nthreads = len(tests)

    jobs = [threading.Thread(
                target=test.run_test, args=(verbose, cluster_queue)
                            )
                for test in tests]
    if nthreads > 1:
        for job in jobs:
            while threading.activeCount()-1 == nthreads:
                time.sleep(0.2)
            job.start()
        for job in jobs:
            job.join()
    else:
        # run straight through
        for job in jobs:
            job.start()
            job.join()


def compare_tests(tests, verbose):

    nskipped = 0

    for test in tests:
        for (inp, args) in test.inputs_args:
            test_file = testcode2.util.testcode_filename(
                    testcode2.FILESTEM['test'],
                    test.test_program.test_id, inp, args
                    )
            test_file = os.path.join(test.path, test_file)
            if os.path.exists(test_file):
                test.verify_job(inp, args, verbose)
            else:
                if verbose:
                    print('Skipping comparison.  '
                          'Test file does not exist: %s.\n' % test_file)
                nskipped += 1

    return nskipped

def diff_tests(tests, diff_program, verbose):

    for test in tests:
        cwd = os.getcwd()
        os.chdir(test.path)
        for (inp, args) in test.inputs_args:
            benchmark = testcode2.util.testcode_filename(
                    testcode2.FILESTEM['benchmark'],
                    test.test_program.benchmark, inp, args
                    )
            test_file = testcode2.util.testcode_filename(
                    testcode2.FILESTEM['test'],
                    test.test_program.test_id, inp, args
                    )
            if verbose:
                print('Diffing %s and %s in %s.' % (benchmark, test_file,
                    test.path))
            if not os.path.exists(test_file) or not os.path.exists(benchmark):
                if verbose:
                    print('Skipping diff: %s does not exist.' % test_file)
            else:
                diff_cmd = '%s %s %s' % (diff_program, benchmark, test_file)
                diff_popen = subprocess.Popen(diff_cmd, shell=True)
                diff_popen.wait()
        os.chdir(cwd)

def tidy_tests(tests, ndays, submit_templates=None):

    epoch_time = time.time() - 86400*ndays

    test_globs = ['test.out*','test.err*']
    if submit_templates:
        test_globs.extend(['%s*' % tmpl for tmpl in submit_templates])

    print(
            'Delete all %s files older than %s days from each job directory?'
                % (' '.join(test_globs), ndays)
         )
    ans = ''
    while ans != 'y' and ans != 'n':
        ans = testcode2.compatibility.compat_input('Confirm [y/n]: ')

    if ans == 'n':
        print('No files deleted.')
    else:
        for test in tests:
            cwd = os.getcwd()
            os.chdir(test.path)
            for test_glob in test_globs:
                for test_file in glob.glob(test_glob):
                    if os.stat(test_file)[-2] < epoch_time:
                        os.remove(test_file)
            os.chdir(cwd)

def make_benchmarks(test_programs, tests, userconfig, copy_files_since):

    # All tests passed?
    statuses = [test.get_status() for test in tests]
    npassed = sum(status[0] for status in statuses)
    nran = sum(status[1] for status in statuses)
    if npassed != nran:
        ans = ''
        print('Not all tests passed.')
        while ans != 'y' and ans != 'n':
            ans = testcode2.compatibility.compat_input(
                                                'Create new benchmarks? [y/n] ')
        if ans != 'y':
            return None

    # Get vcs info.
    vcs = {}
    for (key, program) in test_programs.items():
        if program.vcs and program.vcs.vcs:
            vcs[key] = program.vcs.get_code_id()
        else:
            print('Program not under (known) version control system')
            vcs[key] = testcode2.compatibility.compat_input(
                    'Enter revision id for %s: ' % (key))

    # Benchmark label from vcs info. 
    if len(vcs) == 1:
        benchmark = vcs.popitem()[1]
    else:
        benchmark = []
        for (key, code_id) in vcs.items():
            benchmark.append('%s-%s' % (key, code_id))
        benchmark = '.'.join(benchmark)

    # Create benchmarks.
    for test in tests:
        test.create_new_benchmarks(benchmark, copy_files_since)

    # update userconfig file.
    if userconfig:
        print('Setting new benchmark in userconfig to be %s.' % (benchmark))
        config = testcode2.compatibility.configparser.RawConfigParser()
        config.optionxform = str # Case sensitive file.
        config.read(userconfig)
        config.set('user', 'benchmark', benchmark)
        userconfig = open(userconfig, 'w')
        config.write(userconfig)
        userconfig.close()

#--- info output ---

def start_status(tests, running, verbose):

    if verbose:
        exes = [test.test_program.exe for test in tests]
        exes = testcode2.compatibility.compat_set(exes)
        if running:
            for exe in exes:
                print('Using executable: %s.' % (exe))
        # All tests use the same test_id and benchmark.
        print('Test id: %s.' % (tests[0].test_program.test_id))
        print('Benchmark: %s.' % (tests[0].test_program.benchmark))
        print('')

def end_status(tests, skipped=0, verbose=True):

    statuses = [test.get_status() for test in tests]
    npassed = sum(status[0] for status in statuses)
    nran = sum(status[1] for status in statuses)

    if skipped != 0:
        skipped_msg = '  (Skipped: %s.)'  % (skipped)
    else:
        skipped_msg = ''

    if verbose:
        msg = 'All done.  %s%s out of %s tests passed.' + skipped_msg 
        if npassed == nran:
            print(msg % ('', npassed, nran))
        else:
            print(msg % ('WARNING: only ', npassed, nran))
    else:
        print(' [%s/%s]%s'% (npassed, nran, skipped_msg))

#--- main runner ---

def main(args):

    start_time = time.time()

    (options, actions) = parse_cmdline_args(args)

    # Shortcut names to options used multiple times.
    verbose = options.verbose
    userconfig = options.userconfig
    reuse_id = ( ('compare' in actions or 'diff' in actions)
                 and not 'run' in actions )

    (user_options, test_programs, tests) = init_tests(userconfig,
            options.jobconfig, options.test_id, reuse_id,
            options.executable, options.category, options.nprocs,
            options.benchmark, options.user_option,
            options.job_option)

    start_status(tests, 'run' in actions, verbose)
    if 'run' in actions:
        run_tests(tests, verbose, options.queue_system, options.nthreads)
        end_status(tests, 0, verbose)
    if 'compare' in actions:
        nskipped = compare_tests(tests, verbose)
        end_status(tests, nskipped, verbose)
    if 'diff' in actions:
        diff_tests(tests, user_options['diff'], verbose)
    if 'tidy' in actions:
        submit_templates = []
        for test_program in test_programs.values():
            if test_program.submit_template:
                submit_templates.append(test_program.submit_template)
        tidy_tests(tests, options.older_than, submit_templates)
    if 'make-benchmarks' in actions:
        make_benchmarks(test_programs, tests, userconfig, start_time)

if __name__ == '__main__':

    main(sys.argv[1:])
