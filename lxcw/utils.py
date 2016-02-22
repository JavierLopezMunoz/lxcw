from distutils import spawn
import os
import random
import socket
import subprocess as sp
import tempfile

import click

def ip(name):
    return sp.check_output([
        'sudo', 'lxc-info', '--name', name, '-i']).strip().split()[1]


def os_version():
    return sp.check_output(['lsb_release', '-cs']).strip()


def ansible(host, module, argument, ask_become_pass=False):
    cmd = [
        'ansible', 'all', '-i', '{},'.format(host), '-m',
        module, '-a', '{}'.format(argument), '--become']
    if host == 'localhost':
        cmd += ['-c', 'local']
    if ask_become_pass:
        cmd += ['--ask-become-pass']
    sp.call(cmd)


def ansible_playbook(host, playbook=None, playbook_content=None,
                     extra_vars=None, ask_become_pass=False):
    if playbook_content:
        with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as f:
            playbook = f.name
            f.write(playbook_content)
    cmd = ['ansible-playbook']
    if host == 'localhost':
        cmd += ['-i', 'localhost,', '-c', 'local']
    else:
        cmd += ['-l', host, '-i', spawn.find_executable('lxci')]
    if extra_vars:
        cmd += ['--extra-vars', json.dumps(extra_vars)]
    cmd += [playbook]
    if ask_become_pass:
        cmd += ['--ask-become-pass']
    sp.call(cmd)
    if playbook_content:
        os.remove(f.name)


def random_unused_ip():
    for iteration in xrange(100, 256):
        ip = '10.0.3.{}'.format(random.randint(100, 256))
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if sock.connect_ex((ip, 22)):
                return ip
        finally:
            sock.close()
    click.secho('None unsued IP found', fg='red')
    sys.exit(1)
