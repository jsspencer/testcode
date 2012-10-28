.. _userconfig:

userconfig
==========

The userconfig file must contain at least two sections.  One section must be
entitled 'user' and contains various user settings.  Any other section is
assumed to define a program to be tested, where the program is referred to
internally by its section name.  This makes it possible for a set of tests to
cover multiple, heavily intertwined, programs.  It is, however, far better to
have a distinct set of tests for each program where possible.

[user] section
--------------

The following options are allowed in the [user] section:

benchmark [string]
    Specify the ID of the benchmark to compare to.  This should be set running

    .. code-block bash

        $ testcode.py make-benchmarks

    The format of the benchmark files is'benchmark.out.ID.inp=INPUT_FILE.arg=ARGS'.  
    The 'inp' and/or 'arg' section is not included if it is empty.
date_fmt [string]
    Format of the date string used to uniquely label test outputs.  This must
    be a valid date format string (see `Python documenation
    <http://docs.python.org/library/time.html>`_).  Default: %d%m%Y.
default_program [string]
    Default program used to run each test.  Only needs to be set if
    multiple program sections are specified.  No default.
diff [string]
    Program used to diff test and benchmark outputs.  Default: diff.
tolerance [tolerance format (see :ref:`below <tolerance>`.)]
    Default tolerance(s) used to compare all tests to their respective
    benchmarks.  Default: absolute tolerance 10^-10; no relative tolerance set.

[program_name] section(s)
-------------------------

The following options are allowed to specify a program (called 'program_name')
to be tested:

data_tag [string]
    Data tag to be used to extract data from test and benchmark output.  See
    :ref:`verification` for more details.  No default.
ignore_fields [space-separated list of strings]
    Specify the fields (e.g. column headings in the output from the extraction
    program) to ignore.  This can be used to include, say, timing information
    in the test output for performance comparison without causing failure of
    tests.  No default.
exe [string]
    Path to the program executable.  No default.
extract_args [string]
    Arguments to supply to the extraction program.  Default: null string. 
extract_cmd_template [string]
    Template of command used to extract data from output(s) with the following
    substitutions made:

        tc.extract
            replaced with the extraction program.
        tc.args
            replaced with extract_args.
        tc.file
            replaced with (as required) the filename of the test output or the
            filename of the benchmark output.
        tc.bench
            replaced with the filename of the benchmark output.
        tc.test
            replaced with the filename of the test output.

    Default: tc.extract tc.args tc.file if verify is False and
    tc.extract tc.args tc.test tc.bench if verify is True.
extract_program [string]
    Path to program to use to extract data from test and benchmark output.
    See :ref:`verification` for more details.  No default.
extract_fmt [string]
    Format of the data returned by extraction program. See :ref:`verification`
    for more details.  Can only take values table or yaml.  Default: table.
launch_parallel [string]
    Command template used to run the test program in parallel.  tc.nprocs is
    replaced with the number of processors a test uses (see run_cmd_template).
    If tc.nprocs does not appear, then testcode has no control over the number
    of processors a test is run on.  Default: mpirun -np tc.nprocs.
run_cmd_template [string]
    Template of command used to run the program on the test with the following
    substitutions made:

        tc.program
            replaced with the program to be tested.
        tc.args
            replaced with the arguments of the test.
        tc.input
            replaced with the input filename of the test.
        tc.output
            replaced with the filename for the standard output.  The filename
            is selected at runtime.
        tc.error
            replaced with the filename for the error output.  The filename is
            selected at runtime.
        tc.nprocs
            replaced with the number of processors the test is run on.

    Default: 'tc.program tc.args tc.input > tc.output 2> tc.error' in serial
    and 'launch_command tc.program tc.args tc.input > tc.output 2> tc.error' in
    parallel, where launch_command is specified above The parallel version is
    only used if the number of processors to run a test on is greater than
    zero.
submit_pattern [string]
    String in the submit to be replaced by the run command.  Default:
    testcode.run_cmd.
submit_template [string]
    Path to a template of a submit script used to submit jobs to a queueing
    system.  testcode will replace the string given in submit_pattern with the
    command(s) to run the test.  The submit script must do all other actions (e.g.
    setting environment variables, loading modules, copying files from the test
    directory to a local disk and copying files back afterwards).  No default.
tolerance [tolerance format (see :ref:`below <tolerance>`.)]
    Default tolerance for tests of this type.  Default: inherits from
    [user].
verify [boolean]
    True if the extraction program compares the benchmark and test
    outputs directly.  See :ref:`verification` for more details.  Default:
    False.
vcs [string]
    Version control system used for the source code.  This is used to
    label the benchmarks.  The program binary is assumed to be in the same
    directory tree as the source code.  Supported values are: hg, git and svn
    and None.  If vcs is set to None, then the version id of the program is
    requested interactively when benchmarks are produced.  Default: None.

Most settings are optional and need only be set if certain functionality is
required or the default is not appropriate.  Note that either data_tag or
extract_program must be supplied.

In addition, the following variables are used, if present, as default settings
for all tests of this type:

* inputs_args (no default)
* nprocs (default: 0)
* min_nprocs (default: 0)
* max_nprocs (default: 2^31-1 or 2^63-1)
* output (no default)
* run_concurrent (defailt: false)
 
See :ref:`jobconfig` for more details.

All other settings are assumed to be paths to other versions of the program
(e.g. a stable version).  Using one of these versions instead of the one listed
under the 'exe' variable can be selected by an option to :ref:`testcode.py`.

.. _tolerance:

Tolerance format
----------------

The format for the tolerance for the data is very specific.  Individual
tolerance elements are specified in a comma-separated list.  Each individual
tolerance element is a python tuple (essentially a comma-separated list
enclosed in parentheses) consisting of, in order, the absolute tolerance, the
relative tolerance and the label of the field to which the tolerances apply.
The labels must be quoted.  If no label is supplied then the setting is taken
to be the default tolerance to be applied to all data.  For example, the
setting::

    (1e-8, 1.e-6), (1.e-4, 1.e-4, 'Force')

uses an absolute tolerance of 10^-8 and a relative tolerance of 10^-6 by
default and an absolte tolerance and a relative tolerance of 10^-4 for data
items labelled with 'Force' (i.e. in columns headed by 'Force' using an
external data extraction program or labelled 'Force' by the internal data
extraction program using data tags).

