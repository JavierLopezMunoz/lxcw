import json
import os
import random
import socket
import subprocess as sp
import tempfile
import time

import click


def info(name):
    for info in json.loads(
            sp.check_output(['lxc', 'list', '--format', 'json'])):
        if info['name'] == name:
            return info
    else:
        return None

def ip(name):
    _info = info(name)
    if _info:
        for iteration in range(10):
            for address in _info['state']['network']['eth0']['addresses']:
                if address['family'] == 'inet':
                    return address['address']
            time.sleep(1)
            _info = info(name)
    raise Exception('No ip4 found')


def os_distro():
    return sp.check_output(['lsb_release', '-is']).strip().lower()


def os_release():
    return sp.check_output(['lsb_release', '-cs']).strip()


def ansible(host, module, argument):
    cmd = [
        'ansible', 'all', '-i', '{},'.format(host), '-m',
        module, '-a', '{}'.format(argument), '--become']
    if host == 'localhost':
        cmd += ['-c', 'local']
    sp.call(cmd)


def ansible_playbook(host, playbook=None, playbook_content=None,
                     extra_vars=None, tags=[]):
    if playbook_content:
        with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as f:
            playbook = f.name
            f.write(playbook_content)
    cmd = ['ansible-playbook', '-i', '{},'.format(host),]
    if host == 'localhost':
        cmd += ['-c', 'local']
    if extra_vars:
        cmd += ['--extra-vars', json.dumps(extra_vars)]
    if tags:
        cmd += ['--tags', ','.join(tags)]
    cmd += [playbook]
    sp.call(cmd)
    if playbook_content:
        os.remove(f.name)


def random_unused_ip():
    for iteration in range(100, 256):
        ip = '10.0.3.{}'.format(random.randint(100, 256))
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if sock.connect_ex((ip, 22)):
                return ip
        finally:
            sock.close()
    click.secho('None unsued IP found', fg='red')
    sys.exit(1)
