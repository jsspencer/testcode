'''Parse jobconfig and userconfig ini files.'''

import copy
import glob
import os

import testcode2
import testcode2.compatibility as compat
import testcode2.exceptions as exceptions
import testcode2.validation as validation
import testcode2.vcs as vcs

def parse_tolerance_tuple(val):
    '''Parse (abs_tol,rel_tol,name).'''
    if len(val) == 3:
        name = val[2]
    else:
        name = None
    if len(val) >= 2:
        rel_tol = val[1]
    else:
        rel_tol = None
    if len(val) >= 1:
        abs_tol = val[0]
    else:
        abs_tol = None
    return (name, validation.Tolerance(abs_tol, rel_tol))

def parse_userconfig(config_file, executables=None, test_id=None):
    '''Parse the user options and job types from the userconfig file.

config_file: location of the userconfig file, either relative or absolute.'''

    if executables is None:
        executables = {}

    if not os.path.exists(config_file):
        raise exceptions.TestCodeError(
                'User configuration file %s does not exist.' % (config_file)
                                      )

    userconfig = compat.configparser.RawConfigParser()
    userconfig.optionxform = str # Case sensitive file.
    userconfig.read(config_file)

    # Sensible defaults for the user options.
    user_options = dict(benchfile=None, date_fmt='%d%m%Y',
            tolerance='(1.e-10,None)', output_files=None, diff='diff')

    if userconfig.has_section('user'):
        user_options.update(dict(userconfig.items('user')))
        userconfig.remove_section('user')
        # Append a comma to the option to ensure literal_eval returns a tuple
        # of tuples, even if the option only contains a single tuple.
        user_options['tolerance'] = dict(
                (parse_tolerance_tuple(item)
                     for item in
                        compat.literal_eval('%s,' % user_options['tolerance']))
                                        )
    else:
        raise exceptions.TestCodeError(
                'user section in userconfig does not exist.'
                                      )

    if not userconfig.sections():
        raise exceptions.TestCodeError(
                'No job types specified in userconfig.'
                                      )

    test_program_options = ('run_cmd_template', 'submit_template',
            'ignore_fields', 'data_tag', 'extract_cmd_template',
            'extract_program', 'extract_args', 'verify', 'vcs')
    default_test_options = ('inputs_args', 'output', 'nprocs')
    test_programs = {}
    for section in userconfig.sections():
        tp_dict = {}
        tolerances = copy.deepcopy(user_options['tolerance'])
        # Read in possible TestProgram settings.
        for item in test_program_options:
            if userconfig.has_option(section, item):
                tp_dict[item] = userconfig.get(section, item)
        if section in executables:
            exe = executables[section]
        elif '_tc_all' in executables:
            exe = executables['_tc_all']
        else:
            exe = 'exe'
        if userconfig.has_option(section, exe):
            # exe is set to be a key rather than the path to an executable.
            # Expand.
            exe = userconfig.get(section, exe)
        if 'vcs' in tp_dict:
            tp_dict['vcs'] = vcs.VCSRepository(tp_dict['vcs'],
                    os.path.dirname(exe))
        # Create a default test settings.
        # First, tolerances...
        if userconfig.has_option(section, 'tolerance'):
            for item in (
                    compat.literal_eval('%s,' %
                        userconfig.get(section, 'tolerance'))
                        ):
                (name, tol) = parse_tolerance_tuple(item)
                tolerances[name] = tol
        test_dict = dict(
                         default_tolerance=tolerances[None],
                         tolerances=tolerances,
                        )
        # Other settings...
        for item in default_test_options:
            if userconfig.has_option(section, item):
                test_dict[item] = userconfig.get(section, item)
        if 'nprocs' in test_dict:
            test_dict['nprocs'] = int(test_dict['nprocs'])
        if 'inputs_args' in test_dict:
            # format: (input, arg), (input, arg)'
            test_dict['inputs_args'] = compat.literal_eval(
                                               '%s,' % test_dict['inputs_args'])
        # Create default test instance.
        default_test_settings = testcode2.Test(None, None, **test_dict)
        # Create a default test.
        tp_dict['default_test_settings'] = default_test_settings
        program = testcode2.TestProgram(section, exe, test_id,
            user_options['benchmark'], **tp_dict)
        test_programs[section] = program

        if len(test_programs) == 1:
            # only one program; set default program which helpfully is the most
            # recent value of section from the previous loop.
            user_options['default_program'] = section

    return (user_options, test_programs)

def parse_jobconfig(config_file, user_options, test_programs):
    '''Parse the test configurations from the jobconfig file.

config_file: location of the jobconfig file, either relative or absolute.'''

    if not os.path.exists(config_file):
        raise exceptions.TestCodeError(
                'Job configuration file %s does not exist.' % (config_file)
                                      )

    # paths to the test directories can be specified relative to the config
    # file.
    config_directory = os.path.dirname(os.path.abspath(config_file))

    jobconfig = compat.configparser.RawConfigParser()
    jobconfig.optionxform = str # Case sensitive file.
    jobconfig.read(config_file)

    # Parse job categories.
    # Just store as list of test names for now.
    if jobconfig.has_section('categories'):
        test_categories = dict(jobconfig.items('categories'))
        for (key, val) in test_categories.items():
            test_categories[key] = val.split()
        jobconfig.remove_section('categories')
    else:
        test_categories = {}

    # Parse individual tests.
    tests = []
    for section in jobconfig.sections():
        # test program
        if jobconfig.has_option(section, 'program'):
            test_program = test_programs[jobconfig.get(section, 'program')]
        else:
            test_program = test_programs[user_options['default_program']]
        # Copy default test options.
        default_test = test_program.default_test_settings
        test_dict = dict(
                            inputs_args=default_test.inputs_args,
                            output=default_test.output,
                            default_tolerance=default_test.default_tolerance,
                            tolerances=default_test.tolerances,
                            nprocs=default_test.nprocs,
                        )
        # tolerances
        if jobconfig.has_option(section, 'tolerance'):
            for item in (
                    compat.literal_eval('%s,' %
                        jobconfig.get(section,'tolerance'))
                        ):
                (name, tol) = parse_tolerance_tuple(item)
                test_dict['tolerances'][name] = tol
            jobconfig.remove_option(section, 'tolerance')
        if None in test_dict['tolerances']:
            test_dict['default_tolerance'] = test_dict['tolerances'][None]
        # inputs and arguments
        if jobconfig.has_option(section, 'input'):
            # format: (input, arg), (input, arg)'
            test_dict['inputs_args'] = compat.literal_eval(
                                               '%s,' % test_dict['inputs_args'])
            jobconfig.remove_option(section, 'input')
        # Other options.
        for option in jobconfig.options(section):
            test_dict[option] = jobconfig.get(section, option)
        # Expand any globs in the input files.
        if 'path' in test_dict:
            path = os.path.join(config_directory, test_dict['path'])
            test_dict.pop('path')
        else:
            path = os.path.join(config_directory, section)
        old_dir = os.getcwd()
        os.chdir(path)
        if 'inputs_args' in test_dict:
            inputs_args = []
            for input_arg in test_dict['inputs_args']:
                inp = input_arg[0]
                if len(input_arg) == 2:
                    arg = input_arg[1]
                else:
                    arg = ''
                if inp:
                    for inp_file in glob.glob(inp):
                        inputs_args.append((inp_file, arg))
            test_dict['inputs_args'] = tuple(inputs_args)
        os.chdir(old_dir)
        # Create test.
        tests.append(testcode2.Test(test_program, path, **test_dict))

    return (tests, test_categories)
