'''Utility functions.'''

def testcode_filename(stem, file_id, inp, args):
    '''Construct filename in testcode format.'''
    filename = '%s.%s' % (stem, file_id)
    if inp:
        filename = '%s.inp=%s' % (filename, inp)
    if args:
        args_string = args.replace(' ','_')
        filename = '%s.args=%s' % (filename, args_string)
    return filename
