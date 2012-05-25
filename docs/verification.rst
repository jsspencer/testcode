Test verification
=================

testcode compares selected data from an output with previously obtained output
(the 'benchmark'); a test passes if all data is within a desired tolerance.
The data can be compared using an absolute tolerance and/or a relative
tolerance.  testcode needs some way of knowing what data from the output files
should be validated.  There are three options.

* label output with a 'data tag'

  If a data tag is supplied, then testcode will search each output file for
  lines starting with that tag.  The first numerical entry on those lines will
  then be checked against the benchmark.  For example, if the data tag is set
  to be '[QA]', and the line

      [QA] Energy = 1.23456 eV

  appears in the test output, then testcode will ensure the value 1.23456 is
  identical (within the specified tolerance) to the equivalent line in the
  benchmark output.  The text preceding the value is used to label that data
  item; lines with identical text but different values are handled but it is
  assumed that such lines always come in the same (relative) order.

* user-supplied data extraction program

  An external program can be used to extract data from the test and benchmark
  output; the program must print the data to be compared in an output file in
  a tabular format to standard output.  A row of text is assumed to start
  a table.  Multiple tables are permitted, but each table must be square (i.e.
  no gaps and the same number of elements on each row) and hence each column
  heading must contain no spaces.  For example, a single table is of the
  format::

    val_1   val_2   val3
     1.2     2      3.32
     8.7     4      17.2

 and a table containing multiple subtables::

    val_1   val_2   val3
     1.2     2      3.32
     8.7     4      17.2
    val_4   val_5
    11.22   221.0   

  Tables need not be beautifully presented: the amount of whitespace between
  each table cell is not important, so long as there's at least one space
  separating adjacent cells.

  Column headings are used to label the data in the subsequent rows.  These
  labels can be used to specify different tolerances for different types of
  data.

  Non-numerical values in a table are required to be equal (within python's
  definition of equality for a given object).

* user-supplied verification program

  An external program can be used to validate the test output; the program must
  set an exit status of 0 to indicate the test passed and a non-zero value to
  indicate failure.
