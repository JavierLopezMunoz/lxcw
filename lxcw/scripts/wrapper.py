import os
import random
import subprocess as sp
import socket
from distutils import spawn

import click

from .. import utils

@click.group()
def cli():
    pass


@click.command()
@click.argument('name')
def ssh(name):
    os.execvp('ssh', ['ssh', name, '-l', os.environ['USER']])


@click.command()
@click.argument('name')
@click.option('--release', default=None)
@click.option('--ip',  default=None)
@click.option('--hostname', default=None, multiple=True)
@click.option('--ask-become-pass', default=False)
def up(name, release, ip, hostname, ask_become_pass):
    try:
        output = sp.check_output(['sudo', 'lxc-info', '--name', name])
    except sp.CalledProcessError:
        output = None
    finally:
        message = (
            'is not running' if  utils.os_version() == 'precise'
            else "doesn't exist")
        if not output or message in output:
            user = os.environ['USER']
            packages = ['python', 'python-pip', 'python-dev', 'build-essential']
            cmd = ['sudo', 'lxc-create', '-t', 'ubuntu', '--name', name, '--',
                   '--bindhome', user, '--user', user, '--packages',
                   ','.join(packages)]
            if release:
                cmd += ['--release', release]
            sp.call(cmd)

            utils.ansible_local(
                'lineinfile',
                'dest=/etc/default/lxc-net regexp=LXC_DHCP_CONFILE'
                ' line=LXC_DHCP_CONFILE=/etc/dnsmasq.d/lxc',
                ask_become_pass)

            if not ip:
                while True:
                    ip = '10.0.3.{}'.format(random.randint(100, 256))
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        if sock.connect_ex((ip, 22)):
                            break
                    finally:
                        sock.close()
            utils.ansible_local(
                'lineinfile',
                'dest=/etc/dnsmasq.d/lxc line=dhcp-host={},{}'.format(name, ip),
                ask_become_pass)
            sp.call(['sudo', 'service', 'lxc-net', 'restart'])

            if not hostname:
                hostname = (name,)
            for _hostname in hostname:
                utils.ansible_local(
                    'lineinfile',
                    'dest=/etc/hosts line=\'{0} {1}\''.format(ip, _hostname),
                    ask_become_pass)

            sp.call(['sudo', 'lxc-start', '--name', name, '--daemon'])
            utils.ansible(
                ip, 'lineinfile',
                'dest=/etc/sudoers state=present regexp=\'^%sudo ALL\=\''
                ' line=\'%sudo ALL=(ALL:ALL) NOPASSWD:ALL\''
                ' validate=\'visudo -cf %s\'',
                ask_become_pass=True)
        else:
            sp.call(['sudo', 'lxc-start', '--name', name, '--daemon'])


@click.command()
def ls():
    cmd = ['sudo', 'lxc-ls']
    if utils.os_version() != 'precise':
        cmd += ['--fancy']
    sp.call(cmd)


@click.command()
@click.argument('name')
def halt(name):
    sp.call(['sudo', 'lxc-stop', '--name', name, '--nokill'])


@click.command()
@click.argument('names', nargs=-1)
@click.option('--ask-become-pass', default=False)
def destroy(names, ask_become_pass):
    for name in names:
        sp.call(['sudo', 'lxc-stop', '--name', name, '--nokill'])
        sp.call(['sudo', 'lxc-destroy', '--name', name])
        sp.call(
            ['ssh-keygen', '-f', os.path.expanduser('~/.ssh/known_hosts'),
             '-R', name])
        utils.ansible_local(
            'lineinfile',
            'dest=/etc/hosts regexp=\'10.0.3.[0-9]* {}\' state=absent'.format(
                name),
            ask_become_pass)


@click.command()
@click.argument('name')
@click.option('--playbook', '-p', type=click.Path(exists=True, dir_okay=False))
def provision(name, playbook):
    sp.call([
        'ansible-playbook', '-l', name, '-i',
        spawn.find_executable('lxci'), playbook])


cli.add_command(destroy)
cli.add_command(halt)
cli.add_command(ls)
cli.add_command(ssh)
cli.add_command(provision)
cli.add_command(up)
