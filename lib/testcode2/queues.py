'''Access to external queueing systems.'''

import os.path
import subprocess
import sys
import time

import testcode2.exceptions as exceptions

class ClusterQueueJob:
    '''Interface to external queueing system.

:param string submit_file: filename of submit script to be submitted to the
    queueing system.
:param string system: name of queueing system.  Currently only an interface to
    PBS is implemented.
'''
    def __init__(self, submit_file, system='PBS'):
        self.job_id = None
        self.submit_file = submit_file
        self.system = system
        if self.system not in ['PBS']:
            err = 'Queueing system not implemented: %s' % self.system
            raise exceptions.RunError(err)
    def create_submit_file(self, pattern, string, template):
        '''Create a submit file.
        
Replace pattern in the template file with string and place the result in
self.submit_file.

:param string pattern: string in template to be replaced.
:param string string: string to replace pattern in template.
:param string template: filename of file containing the template submit script.
'''
        # get template
        if not os.path.exists(template):
            err = 'Submit file template does not exist: %s.' % (template,)
            raise exceptions.RunError(err)
        ftemplate = open(template)
        submit = ftemplate.read()
        ftemplate.close()
        # replace marker with our commands
        submit = submit.replace(pattern, string)
        # write to submit script
        fsubmit = open(self.submit_file, 'w')
        fsubmit.write(submit)
        fsubmit.close()
    def start_job(self):
        '''Submit job to cluster queue.'''
        if self.system == 'PBS':
            submit_cmd = ['qsub', self.submit_file]
        try:
            submit_popen = subprocess.Popen(submit_cmd, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT)
            submit_popen.wait()
            self.job_id = submit_popen.communicate()[0].strip()
        except OSError:
            # 'odd' syntax so exceptions work with python 2.5 and python 2.6/3.
            err = 'Error submitting job: %s' % (sys.exc_info()[1],)
            raise exceptions.RunError(err)
    def wait(self):
        '''Returns when job has finished running on the cluster.'''
        retcode = 0
        if self.system == 'PBS':
            qstat_cmd = ['qstat', self.job_id]
        while retcode == 0:
            time.sleep(60)
            # TODO: improve this by examining output from qstat/equivalent
            # command.
            qstat_popen = subprocess.Popen(qstat_cmd, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
            qstat_popen.wait()
            # If the return code to qstat is non-zero, then the job_id no
            # longer exists: must have ended one way or the other!
            retcode = qstat_popen.returncode
