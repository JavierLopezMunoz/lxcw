import subprocess as sp

def ip(name):
    return sp.check_output([
        'sudo', 'lxc-info', '--name', name, '-i']).strip().split()[1]

def os_version():
    sp.check_output(['lsb_release', '-cs'])

def ansible(host, module, argument, ask_become_pass):
    cmd = [
        'ansible', 'all', '-i', '{},'.format(host), '-m',
        module, '-a', '{}'.format(argument), '--become']
    if host == 'localhost':
        cmd +=  ['-c', 'local']
    if ask_become_pass:
        cmd += ['--ask-become-pass']
    sp.call(cmd)

def ansible_local(module, argument, ask_become_pass):
    ansible('localhost', module, argument, ask_become_pass)
