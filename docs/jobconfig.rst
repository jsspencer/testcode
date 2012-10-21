.. _jobconfig:

jobconfig
=========

The jobconfig file defines the tests to run.  If a section named 'categories'
exists, then it gives labels to sets of tests.  All other sections are assumed
to individually define a test.

Tests
-----

A test is assumed to reside in the directory given by the name of the test
section.  For example::

    [carbon_dioxide_ccsd]
    inputs_args = ('co2.inp','')

would define a test in the ``carbon_dioxide_ccsd`` subdirectory relative to the
``jobconfig`` configuration file, with the input file as ``co2.inp`` (in the
``carbon_dioxide_ccsd`` subdirectory) with no additional arguments to be passed
to the test program.  All input and output files related to the test are
assumed to be contained within the test subdirectory.

The following options are permitted:

inputs_args [inputs and arguments format (see :ref:`below <inputs>`)]
    Input filename and associated arguments to be passed to the test program.
    No default.
min_nprocs [integer]
    Minimum number of processors to run test on.  Cannot be overridden by the
    '--processors' command-line option.  Default: 0.
max_nprocs [integer]
    Maximum number of processors to run test on.  Cannot be overridden by the
    '--processors' command-line option.  Default: 2^31-1 or 2^63-1.
nprocs [integer]
    Number of processors to run the test on.  Zero indicates to run the test
    purely in serial, without using an external program such as mpirun to
    launch the test program.  Default: 0.
output [string]
    Filename to which the output is written if the output is not written to
    standard output.  The output file is moved to the specific testcode test
    filename at the end of the calculation before the test output is validated
    against the benchmark output.  Wildcards are allowed so long as the pattern
    only matches a single file at the end of the calculation.  Default:
    inherits from setting in :ref:`userconfig`.
override_nprocs [boolean]
    True if the number of processors to run the test cannot be overidden by
    command-line options to :ref:`testcode.py`.  Useful to force certain tests
    to be executed on a given number of processors.  Default: false.
test_program [string]
    Program name (appropriate section heading in :ref:`userconfig`) to use to
    run the test.  Default: specified in the [user] section of
    :ref:`userconfig`.
tolerance [tolerance format (see :ref:`tolerance`)]
    Tolerances for comparing test output to the benchmark output.  Default:
    inherits from the settings in :ref:`userconfig`.

Test categories
---------------

Each test is automatically defined to reside in a category of the same name.
Additional categories can be specified in the [categories] section.  This makes
it very easy to select subsets of the tests to run.  For example::

    [categories]
    cat1 = t1 t2
    cat2 = t3 t4
    cat3 = cat1 t3

defines three categories (`cat`, `cat2` and `cat3`), each containing a subset
of the overall tests.  A category may contain another category so long as
circular dependencies are avoided.  There are two special categories, `_all_`
and `_default_`.  The `_all_` category contains, by default, all tests and
should not be changed under any circumstances.  The `_default_` category can
be set; if it is not specified then it is set to be the `_all_` category.

.. _inputs:

Program inputs and arguments
----------------------------

The inputs and arguments must be given in a specific format.  As with the
:ref:`tolerance format <tolerance>`,  the inputs and arguments are specified
using a comma-separated list of python tuples.  Each tuple (basically
a comma-separated list enclosed in parantheses) contains two elements: the name
of an input file and the associated arguments, in that order, represents
a test.  Both elements must be quoted.  If the input filename contains
wildcard, then those wildcards are expanded to find all files in the test
subdirectory which match that pattern; the expanded list is sorted in
alphanumerical order.  A separate test (with the same arguments string) is then
created for each file matching the pattern.  used to construct the command to
run.  A null string (``''``) should be used to represent the absence of an
input file or arguments.  Tests within the same subdirectory are run in the
order they are specified.  For example::

    inputs_args = ('test.inp', '')

defines a single test, with input filename ``test.inp`` and no arguments,

::

    inputs_args = ('test.inp', ''), ('test2.inp', '--verbose')

defines two tests, with an additional argument for the second test, and

::

    inputs_args = ('test*.inp', '')

defines a test for each file matching the pattern ``test*inp`` in the test
subdirectory.
