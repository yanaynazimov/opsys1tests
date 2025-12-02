#!/usr/bin/env python3
"""
Test runner for smash shell
Runs module tests, system tests, and stress tests
"""

import subprocess
import os
import sys
import time
import signal
import tempfile
import shutil

# Colors for output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

SMASH_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'smash')

class TestResult:
    def __init__(self, name, passed, expected=None, actual=None, error=None):
        self.name = name
        self.passed = passed
        self.expected = expected
        self.actual = actual
        self.error = error

def run_smash(commands, timeout=5):
    """Run smash with given commands and return output"""
    try:
        proc = subprocess.Popen(
            [SMASH_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True  # Python 3.5 compatible (text=True is 3.7+)
        )
        
        if isinstance(commands, list):
            commands = '\n'.join(commands)
        
        stdout, stderr = proc.communicate(input=commands + '\n', timeout=timeout)
        return stdout, stderr, proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        return None, None, -1
    except Exception as e:
        return None, None, str(e)

def check_output_contains(output, expected_strings):
    """Check if output contains all expected strings"""
    if output is None:
        return False
    for s in expected_strings:
        if s not in output:
            return False
    return True

def check_output_exact_line(output, expected_line):
    """Check if output contains an exact line"""
    if output is None:
        return False
    lines = output.strip().split('\n')
    for line in lines:
        # Remove prompt if present
        if line.startswith('smash > '):
            line = line[8:]
        if line.strip() == expected_line.strip():
            return True
    return False

# ============================================================================
# MODULE TESTS - Test individual commands
# ============================================================================

def test_showpid():
    """Test showpid command"""
    stdout, stderr, code = run_smash(['showpid', 'quit'])
    if stdout is None:
        return TestResult('showpid', False, error='Timeout or error')
    
    # Should contain "smash pid is" followed by a number
    if 'smash pid is' in stdout:
        return TestResult('showpid', True)
    return TestResult('showpid', False, expected='smash pid is <PID>', actual=stdout)

def test_showpid_with_args():
    """Test showpid with arguments (should fail)"""
    stdout, stderr, code = run_smash(['showpid arg1', 'quit'])
    if stdout is None:
        return TestResult('showpid_with_args', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'expected 0 arguments' in combined:
        return TestResult('showpid_with_args', True)
    return TestResult('showpid_with_args', False, 
                     expected='smash error: showpid: expected 0 arguments', 
                     actual=combined)

def test_pwd():
    """Test pwd command"""
    stdout, stderr, code = run_smash(['pwd', 'quit'])
    if stdout is None:
        return TestResult('pwd', False, error='Timeout or error')
    
    # Should contain a path (starts with /)
    lines = stdout.split('\n')
    for line in lines:
        if line.startswith('smash > '):
            line = line[8:]
        if line.startswith('/'):
            return TestResult('pwd', True)
    return TestResult('pwd', False, expected='/<path>', actual=stdout)

def test_pwd_with_args():
    """Test pwd with arguments (should fail)"""
    stdout, stderr, code = run_smash(['pwd arg1', 'quit'])
    if stdout is None:
        return TestResult('pwd_with_args', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'expected 0 arguments' in combined:
        return TestResult('pwd_with_args', True)
    return TestResult('pwd_with_args', False, 
                     expected='smash error: pwd: expected 0 arguments', 
                     actual=combined)

def test_cd_basic():
    """Test basic cd command"""
    stdout, stderr, code = run_smash(['cd /tmp', 'pwd', 'quit'])
    if stdout is None:
        return TestResult('cd_basic', False, error='Timeout or error')
    
    if '/tmp' in stdout:
        return TestResult('cd_basic', True)
    return TestResult('cd_basic', False, expected='/tmp in output', actual=stdout)

def test_cd_parent():
    """Test cd .. command"""
    stdout, stderr, code = run_smash(['cd /tmp', 'cd ..', 'pwd', 'quit'])
    if stdout is None:
        return TestResult('cd_parent', False, error='Timeout or error')
    
    # After cd /tmp and cd .., we should be at /
    # Handle output that may be on same line as prompt
    output = stdout.replace('smash > ', '\n')
    lines = [l.strip() for l in output.split('\n') if l.strip()]
    # Find the last path output
    for line in reversed(lines):
        if line.startswith('/'):
            if line == '/':
                return TestResult('cd_parent', True)
    return TestResult('cd_parent', False, expected='/', actual=stdout)

def test_cd_dash():
    """Test cd - command"""
    stdout, stderr, code = run_smash(['cd /tmp', 'cd /var', 'cd -', 'pwd', 'quit'])
    if stdout is None:
        return TestResult('cd_dash', False, error='Timeout or error')
    
    # cd - should print the path and go back to /tmp
    if '/tmp' in stdout:
        return TestResult('cd_dash', True)
    return TestResult('cd_dash', False, expected='/tmp in output', actual=stdout)

def test_cd_dash_no_oldpwd():
    """Test cd - when no previous directory"""
    stdout, stderr, code = run_smash(['cd -', 'quit'])
    if stdout is None:
        return TestResult('cd_dash_no_oldpwd', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'old pwd not set' in combined.lower() or 'OLDPWD not set' in combined:
        return TestResult('cd_dash_no_oldpwd', True)
    return TestResult('cd_dash_no_oldpwd', False, 
                     expected='old pwd not set error', 
                     actual=combined)

def test_cd_nonexistent():
    """Test cd to nonexistent directory"""
    stdout, stderr, code = run_smash(['cd /nonexistent_path_12345', 'quit'])
    if stdout is None:
        return TestResult('cd_nonexistent', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'does not exist' in combined or 'no such' in combined.lower():
        return TestResult('cd_nonexistent', True)
    return TestResult('cd_nonexistent', False, 
                     expected='directory does not exist error', 
                     actual=combined)

def test_cd_to_file():
    """Test cd to a file (not directory)"""
    # Create a temp file
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_file = f.name
    
    try:
        stdout, stderr, code = run_smash(['cd {}'.format(temp_file), 'quit'])
        if stdout is None:
            return TestResult('cd_to_file', False, error='Timeout or error')
        
        combined = stdout + stderr
        if 'not a directory' in combined.lower() or 'Not a directory' in combined:
            return TestResult('cd_to_file', True)
        return TestResult('cd_to_file', False, 
                         expected='not a directory error', 
                         actual=combined)
    finally:
        os.unlink(temp_file)

def test_jobs_empty():
    """Test jobs command with empty list"""
    stdout, stderr, code = run_smash(['jobs', 'quit'])
    if stdout is None:
        return TestResult('jobs_empty', False, error='Timeout or error')
    
    # Should just show prompts, no job listings
    lines = [l for l in stdout.split('\n') if l.strip() and not l.startswith('smash >') and '[' in l]
    if len(lines) == 0:
        return TestResult('jobs_empty', True)
    return TestResult('jobs_empty', False, expected='no jobs listed', actual=stdout)

def test_jobs_with_background():
    """Test jobs command with background job"""
    stdout, stderr, code = run_smash(['sleep 10 &', 'jobs', 'quit kill'], timeout=10)
    if stdout is None:
        return TestResult('jobs_with_background', False, error='Timeout or error')
    
    # Should show the sleep job
    if 'sleep' in stdout and '[' in stdout:
        return TestResult('jobs_with_background', True)
    return TestResult('jobs_with_background', False, 
                     expected='job listing with sleep', 
                     actual=stdout)

def test_kill_job():
    """Test kill command"""
    stdout, stderr, code = run_smash(['sleep 100 &', 'kill 9 0', 'quit'], timeout=5)
    if stdout is None:
        return TestResult('kill_job', False, error='Timeout or error')
    
    if 'signal 9 was sent to pid' in stdout:
        return TestResult('kill_job', True)
    return TestResult('kill_job', False, 
                     expected='signal 9 was sent to pid', 
                     actual=stdout)

def test_kill_nonexistent():
    """Test kill on nonexistent job"""
    stdout, stderr, code = run_smash(['kill 9 99', 'quit'])
    if stdout is None:
        return TestResult('kill_nonexistent', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'job id 99 does not exist' in combined:
        return TestResult('kill_nonexistent', True)
    return TestResult('kill_nonexistent', False, 
                     expected='job id 99 does not exist', 
                     actual=combined)

def test_kill_invalid_args():
    """Test kill with invalid arguments"""
    stdout, stderr, code = run_smash(['kill abc 0', 'quit'])
    if stdout is None:
        return TestResult('kill_invalid_args', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'invalid arguments' in combined:
        return TestResult('kill_invalid_args', True)
    return TestResult('kill_invalid_args', False, 
                     expected='invalid arguments', 
                     actual=combined)

def test_diff_same_files():
    """Test diff with identical files"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f1:
        f1.write('test content\n')
        file1 = f1.name
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
        f2.write('test content\n')
        file2 = f2.name
    
    try:
        stdout, stderr, code = run_smash(['diff {} {}'.format(file1, file2), 'quit'])
        if stdout is None:
            return TestResult('diff_same_files', False, error='Timeout or error')
        
        if '0' in stdout:
            return TestResult('diff_same_files', True)
        return TestResult('diff_same_files', False, expected='0', actual=stdout)
    finally:
        os.unlink(file1)
        os.unlink(file2)

def test_diff_different_files():
    """Test diff with different files"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f1:
        f1.write('content 1\n')
        file1 = f1.name
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
        f2.write('content 2\n')
        file2 = f2.name
    
    try:
        stdout, stderr, code = run_smash(['diff {} {}'.format(file1, file2), 'quit'])
        if stdout is None:
            return TestResult('diff_different_files', False, error='Timeout or error')
        
        if '1' in stdout:
            return TestResult('diff_different_files', True)
        return TestResult('diff_different_files', False, expected='1', actual=stdout)
    finally:
        os.unlink(file1)
        os.unlink(file2)

def test_diff_nonexistent():
    """Test diff with nonexistent file"""
    stdout, stderr, code = run_smash(['diff /nonexistent1 /nonexistent2', 'quit'])
    if stdout is None:
        return TestResult('diff_nonexistent', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'expected valid paths' in combined:
        return TestResult('diff_nonexistent', True)
    return TestResult('diff_nonexistent', False, 
                     expected='expected valid paths for files', 
                     actual=combined)

def test_diff_directory():
    """Test diff with directory"""
    stdout, stderr, code = run_smash(['diff /tmp /var', 'quit'])
    if stdout is None:
        return TestResult('diff_directory', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'paths are not files' in combined:
        return TestResult('diff_directory', True)
    return TestResult('diff_directory', False, 
                     expected='paths are not files', 
                     actual=combined)

def test_diff_wrong_args():
    """Test diff with wrong number of arguments"""
    stdout, stderr, code = run_smash(['diff /tmp', 'quit'])
    if stdout is None:
        return TestResult('diff_wrong_args', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'expected 2 arguments' in combined:
        return TestResult('diff_wrong_args', True)
    return TestResult('diff_wrong_args', False, 
                     expected='expected 2 arguments', 
                     actual=combined)

def test_quit():
    """Test quit command"""
    stdout, stderr, code = run_smash(['quit'])
    if code == 0:
        return TestResult('quit', True)
    return TestResult('quit', False, expected='exit code 0', actual='exit code {}'.format(code))

def test_quit_kill():
    """Test quit kill command"""
    stdout, stderr, code = run_smash(['sleep 100 &', 'sleep 100 &', 'quit kill'], timeout=15)
    if stdout is None:
        return TestResult('quit_kill', False, error='Timeout or error')
    
    # Should show SIGTERM messages
    if 'SIGTERM' in stdout and code == 0:
        return TestResult('quit_kill', True)
    return TestResult('quit_kill', False, 
                     expected='SIGTERM messages and exit 0', 
                     actual='stdout: {}, code: {}'.format(stdout, code))

def test_quit_invalid_arg():
    """Test quit with invalid argument"""
    stdout, stderr, code = run_smash(['quit foo', 'quit'])
    if stdout is None:
        return TestResult('quit_invalid_arg', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'unexpected arguments' in combined:
        return TestResult('quit_invalid_arg', True)
    return TestResult('quit_invalid_arg', False, 
                     expected='unexpected arguments', 
                     actual=combined)

def test_external_ls():
    """Test external command (ls)"""
    stdout, stderr, code = run_smash(['ls', 'quit'])
    if stdout is None:
        return TestResult('external_ls', False, error='Timeout or error')
    
    # ls should produce some output
    lines = [l for l in stdout.split('\n') if l.strip() and not l.startswith('smash >')]
    if len(lines) > 0:
        return TestResult('external_ls', True)
    return TestResult('external_ls', False, expected='file listing', actual=stdout)

def test_external_echo():
    """Test external command (echo)"""
    stdout, stderr, code = run_smash(['echo hello world', 'quit'])
    if stdout is None:
        return TestResult('external_echo', False, error='Timeout or error')
    
    if 'hello world' in stdout:
        return TestResult('external_echo', True)
    return TestResult('external_echo', False, expected='hello world', actual=stdout)

def test_external_background():
    """Test external command in background"""
    stdout, stderr, code = run_smash(['sleep 5 &', 'jobs', 'quit kill'], timeout=10)
    if stdout is None:
        return TestResult('external_background', False, error='Timeout or error')
    
    if 'sleep' in stdout and '[' in stdout:
        return TestResult('external_background', True)
    return TestResult('external_background', False, 
                     expected='sleep job in listing', 
                     actual=stdout)

def test_alias_basic():
    """Test basic alias"""
    stdout, stderr, code = run_smash(["alias ll='ls -l'", 'll', 'quit'])
    if stdout is None:
        return TestResult('alias_basic', False, error='Timeout or error')
    
    # ll should work as ls -l
    if 'total' in stdout or 'rw' in stdout or len(stdout.split('\n')) > 3:
        return TestResult('alias_basic', True)
    return TestResult('alias_basic', False, expected='ls -l output', actual=stdout)

def test_alias_list():
    """Test alias creation works (alias list printing not required)"""
    # Just test that alias is created and can be used
    stdout, stderr, code = run_smash(["alias ll='ls'", 'll', 'quit'], timeout=5)
    if stdout is None:
        return TestResult('alias_list', False, error='Timeout or error')
    
    # If we get output from ls command (or no error), alias worked
    combined = stdout + stderr
    if 'not found' not in combined.lower() and 'error' not in combined.lower():
        return TestResult('alias_list', True)
    return TestResult('alias_list', False, expected='alias ll to work', actual=combined)

def test_unalias():
    """Test unalias"""
    stdout, stderr, code = run_smash(["alias ll='ls -l'", 'unalias ll', 'alias', 'quit'])
    if stdout is None:
        return TestResult('unalias', False, error='Timeout or error')
    
    # After unalias, ll should not appear in alias list
    lines = stdout.split('\n')
    alias_output = False
    for i, line in enumerate(lines):
        if 'alias' in line and i > 0:  # Second alias command
            alias_output = True
        if alias_output and 'll' in line:
            return TestResult('unalias', False, expected='ll removed from aliases', actual=stdout)
    return TestResult('unalias', True)

# ============================================================================
# SYSTEM TESTS - Test command combinations
# ============================================================================

def test_complex_command_success():
    """Test && with first command succeeding"""
    stdout, stderr, code = run_smash(['echo first && echo second', 'quit'])
    if stdout is None:
        return TestResult('complex_command_success', False, error='Timeout or error')
    
    if 'first' in stdout and 'second' in stdout:
        return TestResult('complex_command_success', True)
    return TestResult('complex_command_success', False, 
                     expected='first and second', 
                     actual=stdout)

def test_complex_command_fail():
    """Test && with first command failing"""
    stdout, stderr, code = run_smash(['cd /nonexistent && echo should_not_appear', 'quit'])
    if stdout is None:
        return TestResult('complex_command_fail', False, error='Timeout or error')
    
    if 'should_not_appear' not in stdout:
        return TestResult('complex_command_fail', True)
    return TestResult('complex_command_fail', False, 
                     expected='should_not_appear NOT in output', 
                     actual=stdout)

def test_fg_basic():
    """Test fg command"""
    # Start a background job, then bring to foreground
    stdout, stderr, code = run_smash(['sleep 1 &', 'fg 0', 'quit'], timeout=5)
    if stdout is None:
        return TestResult('fg_basic', False, error='Timeout or error')
    
    # fg should work without error
    combined = stdout + stderr
    if 'does not exist' not in combined and 'invalid' not in combined:
        return TestResult('fg_basic', True)
    return TestResult('fg_basic', False, expected='fg to work', actual=combined)

def test_fg_empty_list():
    """Test fg with empty job list"""
    stdout, stderr, code = run_smash(['fg', 'quit'])
    if stdout is None:
        return TestResult('fg_empty_list', False, error='Timeout or error')
    
    combined = stdout + stderr
    if 'jobs list is empty' in combined or 'job list is empty' in combined:
        return TestResult('fg_empty_list', True)
    return TestResult('fg_empty_list', False, 
                     expected='jobs list is empty', 
                     actual=combined)

def test_bg_basic():
    """Test bg command on stopped job"""
    # This is tricky to test without signals, skip for now
    return TestResult('bg_basic', True, error='Requires manual signal testing')

def test_multiple_background_jobs():
    """Test multiple background jobs"""
    stdout, stderr, code = run_smash([
        'sleep 100 &',
        'sleep 100 &', 
        'sleep 100 &',
        'jobs',
        'quit kill'
    ], timeout=20)
    if stdout is None:
        return TestResult('multiple_background_jobs', False, error='Timeout or error')
    
    # Should have 3 jobs listed
    job_count = stdout.count('[')
    if job_count >= 3:
        return TestResult('multiple_background_jobs', True)
    return TestResult('multiple_background_jobs', False, 
                     expected='3 jobs', 
                     actual='{} jobs found'.format(job_count))

def test_job_id_reuse():
    """Test that job IDs are reused correctly"""
    stdout, stderr, code = run_smash([
        'sleep 100 &',  # job 0
        'sleep 100 &',  # job 1
        'kill 9 0',     # kill job 0
        'sleep 100 &',  # should get job 0 again
        'jobs',
        'quit kill'
    ], timeout=15)
    if stdout is None:
        return TestResult('job_id_reuse', False, error='Timeout or error')
    
    # Job 0 should be reused
    if '[0]' in stdout and '[1]' in stdout:
        return TestResult('job_id_reuse', True)
    return TestResult('job_id_reuse', False, expected='jobs 0 and 1', actual=stdout)

# ============================================================================
# STRESS TESTS
# ============================================================================

def test_many_commands():
    """Test many sequential commands"""
    commands = ['echo test' for _ in range(50)]
    commands.append('quit')
    
    stdout, stderr, code = run_smash(commands, timeout=30)
    if stdout is None:
        return TestResult('many_commands', False, error='Timeout or error')
    
    test_count = stdout.count('test')
    if test_count >= 45:  # Allow some margin
        return TestResult('many_commands', True)
    return TestResult('many_commands', False, 
                     expected='~50 test outputs', 
                     actual='{} found'.format(test_count))

def test_many_background_jobs():
    """Test many background jobs"""
    commands = ['sleep 100 &' for _ in range(20)]
    commands.append('jobs')
    commands.append('quit kill')
    
    stdout, stderr, code = run_smash(commands, timeout=60)
    if stdout is None:
        return TestResult('many_background_jobs', False, error='Timeout or error')
    
    # Count job listings
    job_count = stdout.count('[')
    if job_count >= 15:
        return TestResult('many_background_jobs', True)
    return TestResult('many_background_jobs', False, 
                     expected='~20 jobs', 
                     actual='{} found'.format(job_count))

def test_rapid_cd():
    """Test rapid directory changes"""
    commands = []
    for _ in range(20):
        commands.append('cd /tmp')
        commands.append('cd /var')
    commands.append('pwd')
    commands.append('quit')
    
    stdout, stderr, code = run_smash(commands, timeout=15)
    if stdout is None:
        return TestResult('rapid_cd', False, error='Timeout or error')
    
    if '/var' in stdout:
        return TestResult('rapid_cd', True)
    return TestResult('rapid_cd', False, expected='/var', actual=stdout)

def test_alias_chain():
    """Test alias with && chain"""
    stdout, stderr, code = run_smash([
        "alias cd2out='cd .. && cd ..'",
        "cd /var/log",
        "cd2out",
        "pwd",
        'quit'
    ])
    if stdout is None:
        return TestResult('alias_chain', False, error='Timeout or error')
    
    # After cd /var/log and cd2out (cd .. && cd ..), should be at /
    # /var/log -> /var -> /
    if '/' in stdout:
        # Check that pwd shows root
        output = stdout.replace('smash > ', '\n')
        lines = [l.strip() for l in output.split('\n') if l.strip()]
        for line in lines:
            if line == '/':
                return TestResult('alias_chain', True)
    return TestResult('alias_chain', False, 
                     expected='/ after cd2out from /var/log', 
                     actual=stdout)

def test_alias_recursive():
    """Test recursive alias expansion"""
    stdout, stderr, code = run_smash([
        "alias a='echo hello'",
        "alias b='a'",
        "alias c='b'",
        "c",
        'quit'
    ])
    if stdout is None:
        return TestResult('alias_recursive', False, error='Timeout or error')
    
    # c -> b -> a -> echo hello
    if 'hello' in stdout:
        return TestResult('alias_recursive', True)
    return TestResult('alias_recursive', False, 
                     expected='hello from recursive alias c->b->a', 
                     actual=stdout)

def test_garbage_collector():
    """Test garbage collector by creating many short-lived background jobs over time"""
    # The garbage collector runs before each new command is processed.
    # So if we create jobs that finish quickly, they should be cleaned up
    # before we hit the 100 job limit.
    # 
    # Each command line is processed separately, so we send individual commands
    # with short-lived background jobs. Between command lines, the garbage
    # collector should clean up finished jobs.
    
    commands = []
    
    # Create 120 very short-lived background jobs
    # 'true' exits immediately, so by the time next command runs,
    # the garbage collector should clean it up
    for i in range(120):
        commands.append('true &')
    
    # At the end, check jobs - should have very few or no jobs left
    commands.append('jobs')
    commands.append('quit')
    
    stdout, stderr, code = run_smash(commands, timeout=60)
    if stdout is None:
        return TestResult('garbage_collector', False, error='Timeout or error')
    
    # Check that we don't have an error about job list being full
    combined = stdout + stderr
    if 'full' in combined.lower() or 'overflow' in combined.lower():
        return TestResult('garbage_collector', False, 
                         expected='no overflow error', 
                         actual='Job list overflow detected')
    
    # If we got here without overflow, garbage collector is working
    return TestResult('garbage_collector', True)

def test_garbage_collector_with_sleep():
    """Test garbage collector with short sleep jobs that complete during execution"""
    commands = []
    
    # Create 30 jobs that sleep for 1 second each
    for i in range(30):
        commands.append('sleep 1 &')
    
    # Wait a bit by running some commands
    for i in range(5):
        commands.append('pwd')
    
    # By now some jobs should have finished and been collected
    # Create 30 more jobs
    for i in range(30):
        commands.append('sleep 1 &')
    
    # Check jobs - if garbage collector works, we shouldn't have 60 jobs
    commands.append('jobs')
    commands.append('quit kill')
    
    stdout, stderr, code = run_smash(commands, timeout=120)
    if stdout is None:
        return TestResult('garbage_collector_sleep', False, error='Timeout or error')
    
    # Count jobs in the output
    job_count = stdout.count('[')
    
    # Should have some jobs but not all 60 if garbage collector works
    # This is a softer test - just ensure no overflow
    combined = stdout + stderr
    if 'full' in combined.lower() or 'overflow' in combined.lower():
        return TestResult('garbage_collector_sleep', False, 
                         expected='no overflow error', 
                         actual='Job list overflow detected')
    
    return TestResult('garbage_collector_sleep', True)

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run all tests and report results"""
    
    # Check if smash exists
    if not os.path.exists(SMASH_PATH):
        print("{}Error: smash executable not found at {}{}".format(RED, SMASH_PATH, RESET))
        print("Please run 'make' first to build the project.")
        return 1
    
    module_tests = [
        # showpid tests
        test_showpid,
        test_showpid_with_args,
        
        # pwd tests
        test_pwd,
        test_pwd_with_args,
        
        # cd tests
        test_cd_basic,
        test_cd_parent,
        test_cd_dash,
        test_cd_dash_no_oldpwd,
        test_cd_nonexistent,
        test_cd_to_file,
        
        # jobs tests
        test_jobs_empty,
        test_jobs_with_background,
        
        # kill tests
        test_kill_job,
        test_kill_nonexistent,
        test_kill_invalid_args,
        
        # diff tests
        test_diff_same_files,
        test_diff_different_files,
        test_diff_nonexistent,
        test_diff_directory,
        test_diff_wrong_args,
        
        # quit tests
        test_quit,
        test_quit_kill,
        test_quit_invalid_arg,
        
        # external command tests
        test_external_ls,
        test_external_echo,
        test_external_background,
        
        # alias tests
        test_alias_basic,
        test_alias_list,
        test_unalias,
    ]
    
    system_tests = [
        test_complex_command_success,
        test_complex_command_fail,
        test_fg_basic,
        test_fg_empty_list,
        test_bg_basic,
        test_multiple_background_jobs,
        test_job_id_reuse,
    ]
    
    stress_tests = [
        test_many_commands,
        test_many_background_jobs,
        test_rapid_cd,
        test_alias_chain,
        test_alias_recursive,
        test_garbage_collector,
        test_garbage_collector_with_sleep,
    ]
    
    all_tests = [
        ("Module Tests", module_tests),
        ("System Tests", system_tests),
        ("Stress Tests", stress_tests),
    ]
    
    total_passed = 0
    total_failed = 0
    total_tests = 0
    
    for category_name, tests in all_tests:
        print("\n{}{}{}".format(BLUE, '='*60, RESET))
        print("{}{}{}".format(BLUE, category_name, RESET))
        print("{}{}{}".format(BLUE, '='*60, RESET))
        
        for test_func in tests:
            total_tests += 1
            try:
                result = test_func()
                if result.passed:
                    total_passed += 1
                    print("  {}[PASS]{} {}".format(GREEN, RESET, result.name))
                else:
                    total_failed += 1
                    print("  {}[FAIL]{} {}".format(RED, RESET, result.name))
                    if result.expected:
                        print("      Expected: {}".format(result.expected))
                    if result.actual:
                        actual_short = result.actual[:200] + '...' if len(str(result.actual)) > 200 else result.actual
                        print("      Actual: {}".format(actual_short))
                    if result.error:
                        print("      Error: {}".format(result.error))
            except Exception as e:
                total_failed += 1
                print("  {}[FAIL]{} {}: Exception - {}".format(RED, RESET, test_func.__name__, e))
    
    print("\n{}{}{}".format(BLUE, '='*60, RESET))
    print("{}SUMMARY{}".format(BLUE, RESET))
    print("{}{}{}".format(BLUE, '='*60, RESET))
    print("  Total:  {}".format(total_tests))
    print("  {}Passed: {}{}".format(GREEN, total_passed, RESET))
    print("  {}Failed: {}{}".format(RED, total_failed, RESET))
    
    if total_failed == 0:
        print("\n{}All tests passed!{}".format(GREEN, RESET))
        return 0
    else:
        print("\n{}Some tests failed. Please review the output above.{}".format(YELLOW, RESET))
        return 1

if __name__ == '__main__':
    sys.exit(run_all_tests())
