import random
import socket
import subprocess as sp

import click


def ip(name):
    return sp.check_output([
        'sudo', 'lxc-info', '--name', name, '-i']).strip().split()[1]


def os_version():
    return sp.check_output(['lsb_release', '-cs']).strip()


def ansible(host, module, argument, ask_become_pass):
    cmd = [
        'ansible', 'all', '-i', '{},'.format(host), '-m',
        module, '-a', '{}'.format(argument), '--become']
    if host == 'localhost':
        cmd += ['-c', 'local']
    if ask_become_pass:
        cmd += ['--ask-become-pass']
    sp.call(cmd)


def ansible_local(module, argument, ask_become_pass):
    ansible('localhost', module, argument, ask_become_pass)


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
