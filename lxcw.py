import json
import os
import random
import subprocess as sp
import socket

import click


@click.group()
def cli():
    pass


def _lxc_ip(name):
    return sp.check_output([
        'sudo', 'lxc-info', '--name', name, '-i']).strip().split()[1]


@click.command()
@click.argument('name')
def ssh(name):
    os.execvp('ssh', ['ssh', name, '-l', os.environ['USER']])


def _os_version():
    sp.check_output(['lsb_release', '-cs'])

def _ansible_local(module, argument):
    sp.call([
        'ansible', 'all', '-i', 'localhost,', '-c', 'local', '-m',
        module, '-a', '{}'.format(argument), '--become', '--ask-become'])

@click.command()
@click.argument('name')
@click.option('--release', default=None)
@click.option('--ip',  default=None)
@click.option('--hostname', default=None, multiple=True)
def up(name, release, ip, hostname):
    try:
        output = sp.check_output(['sudo', 'lxc-info', '--name', name])
    except sp.CalledProcessError:
        output = None
    finally:
        message = (
            'is not running' if  _os_version() == 'precise'
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

            _ansible_local(
                'lineinfile',
                'dest=/etc/default/lxc-net regexp=LXC_DHCP_CONFILE'
                ' line=LXC_DHCP_CONFILE=/etc/dnsmasq.d/lxc')

            if not ip:
                while True:
                    ip = '10.0.3.{}'.format(random.randint(100, 256))
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        if sock.connect_ex((ip, 22)):
                            break
                    finally:
                        sock.close()
            _ansible_local(
                'lineinfile',
                'dest=/etc/dnsmasq.d/lxc line=dhcp-host={},{}'.format(name, ip))
            sp.call(['sudo', 'service', 'lxc-net', 'restart'])

            if not hostname:
                hostname = (name,)
            for _hostname in hostname:
                _ansible_local(
                    'lineinfile',
                    'dest=/etc/hosts line=\'{0} {1}\''.format(ip, _hostname))

        sp.call(['sudo', 'lxc-start', '--name', name, '--daemon'])


@click.command()
def ls():
    cmd = ['sudo', 'lxc-ls']
    if _os_version() != 'precise':
        cmd += ['--fancy']
    sp.call(cmd)


@click.command()
@click.argument('name')
def halt(name):
    sp.call(['sudo', 'lxc-stop', '--name', name, '--nokill'])


@click.command()
@click.argument('names', nargs=-1)
def destroy(names):
    for name in names:
        sp.call(['sudo', 'lxc-stop', '--name', name, '--nokill'])
        sp.call(['sudo', 'lxc-destroy', '--name', name])
        sp.call(
            ['ssh-keygen', '-f', os.path.expanduser('~/.ssh/known_hosts'),
             '-R', name])
        _ansible_local(
            'lineinfile',
            'dest=/etc/hosts regexp=\'10.0.3.[0-9]* {}\' state=absent'.format(
                name))


@click.command()
@click.argument('name')
@click.option('--playbook', '-p', type=click.Path(exists=True, dir_okay=False))
def provision(name, playbook):
    sp.call([
        'ansible-playbook', '-l', name, '-i', '"lxcw inventory"', playbook])


@click.command()
@click.option('--list', is_flag=True)
@click.option('--host')
def inventory(list, host):
    if host:
        data = {'ansible_ssh_host': _lxc_ip(host)}
    else:
        containers = sp.check_output(['sudo', 'lxc-ls']).splitlines()
        data = {'containers': containers}
    click.echo(json.dumps(data))

cli.add_command(destroy)
cli.add_command(halt)
cli.add_command(ls)
cli.add_command(ssh)
cli.add_command(provision)
cli.add_command(up)
cli.add_command(inventory)
