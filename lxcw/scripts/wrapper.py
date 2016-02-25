import crypt
import json
import os
import re
import string
import subprocess as sp
import sys
import yaml

import click

from .. import utils


@click.group()
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand not in ('init', 'ls'):
        try:
            with open("lxcwfile.yml", 'r') as stream:
                ctx.obj = yaml.load(stream)
                ctx.obj['vm']['box']['release'] = str(
                    ctx.obj['vm']['box']['release'])
                ctx.obj['vm']['hostnames'] = [ctx.obj['vm']['hostname']]
                if 'aliases' in ctx.obj['vm']:
                    ctx.obj['vm']['hostnames'] += ctx.obj['vm']['aliases']
                if 'provision' in ['vm']:
                    ctx.obj['vm']['provision']['ansible']['playbook'] = (
                        os.path.join(
                            os.getcwd(),
                            ctx.obj['vm']['provision']['ansible']['playbook']))
        except IOError as err:
            click.secho('No \'lxcwfile.yml\' present', fg='red')
            sys.exit(1)


@click.command()
@click.pass_context
def ssh(ctx):
    os.execvp('ssh',
              ['ssh', ctx.obj['vm']['hostname'], '-l', os.environ['USER']])


PLAYBOOK_UP = string.Template('''
---
- hosts: all
  become: yes
  tasks:
    - lineinfile: dest=/etc/default/lxc-net regexp=LXC_DHCP_CONFILE line=LXC_DHCP_CONFILE=/etc/dnsmasq.d/lxc
    - lineinfile: dest=/etc/dnsmasq.d/lxc line="dhcp-host=${hostname},${ip}"
    - lineinfile: dest=/etc/hosts line="${ip} ${hostnames}"
    - lineinfile: dest=/var/lib/lxc/${hostname}/rootfs/etc/sudoers line="${user} ALL=(ALL) NOPASSWD:ALL" state=present
''')

@click.command()
@click.pass_context
def up(ctx):
    if not ctx.obj['nopasswd_sudoer']:
        # Add user to sudoers to allow run sudo commands without password
        utils.ansible(
            'localhost', 'lineinfile',
            'dest=/etc/sudoers line="{} ALL=(ALL) NOPASSWD:ALL"'
            ' state=present'.format(os.environ['USER']))

    try:
        output = sp.check_output(
            ['sudo', 'lxc-info', '--name', ctx.obj['vm']['hostname']])
    except sp.CalledProcessError:
        output = None
    finally:
        message = (
            'is not running' if utils.os_release() == '12.04'
            else "doesn't exist")
        if not output or message in output:
            cmd = ['sudo', 'lxc-create',
                   '--template', ctx.obj['vm']['box']['distro'],
                   '--name', ctx.obj['vm']['hostname'], '--',
                   '--release', ctx.obj['vm']['box']['release']]
            if ctx.obj['vm']['box']['distro'] == 'ubuntu':
                cmd += ['--bindhome', os.environ['USER'],
                        '--user', os.environ['USER'],
                        '--packages', ','.join([
                            'python', 'python-pip', 'python-dev',
                            'build-essential'])]
            elif ctx.obj['vm']['box']['distro'] == 'centos':
                if int(ctx.obj['vm']['box']['release']) < 6:
                    click.secho(
                        'Only CentOS >= 6 container supported', fg='red')
                    sys.exit(1)
                try:
                   sp.check_call(['dpkg', '-l', 'yum'])
                except sp.CalledProcessError:
                    click.secho(
                        'Please, to install CentOS containers'
                        ' "sudo apt-get install yum"', fg='blue')
                    sys.exit(1)
            else:
                click.secho(
                    'Only Ubuntu and CentOS containers supported', fg='red')
                sys.exit(1)
            sp.call(cmd)

            if ctx.obj['vm']['box']['distro'] == 'centos':
                sp.call(
                    ['sudo', 'chroot', '/var/lib/lxc/{}/rootfs'.format(
                        ctx.obj['vm']['hostname']),
                     'useradd', '--create-home', os.environ['USER'],
                     '-p', crypt.crypt('centos', 'aa')])
                sp.call(
                    ['sudo', 'chroot', '/var/lib/lxc/{}/rootfs'.format(
                        ctx.obj['vm']['hostname']),
                     'chown', os.environ['USER'],
                     '/home/{}'.format(os.environ['USER'])])
                sp.call(
                    ['sudo', 'chroot', '/var/lib/lxc/{}/rootfs'.format(
                        ctx.obj['vm']['hostname']),
                     'yum', 'install', '-y', 'sudo', 'epel-release'])
                sp.call(
                    ['sudo', 'chroot', '/var/lib/lxc/{}/rootfs'.format(
                        ctx.obj['vm']['hostname']),
                     'yum', 'install', '-y', 'python-pip'])

            utils.ansible_playbook(
                'localhost', playbook_content=PLAYBOOK_UP.substitute(
                    hostname=ctx.obj['vm']['hostname'],
                    hostnames=' '.join(ctx.obj['vm']['hostnames']),
                    ip=utils.random_unused_ip(), user=os.environ['USER']))
            sp.call(['sudo', 'service', 'lxc-net', 'restart'])
            sp.call(
                ['sudo', 'lxc-start', '--name', ctx.obj['vm']['hostname']])

            if 'provision' in ctx.obj['vm']:
                utils.ansible_playbook(
                    ctx.obj['vm']['hostname'],
                    ctx.obj['vm']['provision']['ansible']['playbook'],
                    ctx.obj['vm']['provision']['ansible'].get('extra_vars'))
        else:
            sp.call(
                ['sudo', 'lxc-start', '--name', ctx.obj['vm']['hostname']])

        if not ctx.obj['nopasswd_sudoer']:
            # Remove nopasswd user from sudoers
            utils.ansible(
                'localhost', 'lineinfile',
                'dest=/etc/sudoers line="{} ALL=(ALL) NOPASSWD:ALL"'
                ' state=absent'.format(os.environ['USER']))

@click.command()
def ls():
    cmd = ['sudo', 'lxc-ls']
    if utils.os_release() != '12.04':
        cmd += ['--fancy']
    sp.call(cmd)


@click.command()
@click.pass_context
def halt(ctx):
    sp.call(
        ['sudo', 'lxc-stop', '--name', ctx.obj['vm']['hostname'], '--nokill'])


PLAYBOOK_DESTROY = string.Template('''
---
- hosts: all
  become: yes
  tasks:
    - lineinfile: dest=/etc/hosts regexp="\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3} ${hostnames}" state=absent
    - lineinfile: dest=/etc/dnsmasq.d/lxc regexp="dhcp-host=${hostname},\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}" state=absent
    - service: name=lxc-net state=restarted
''')


@click.command()
@click.pass_context
def destroy(ctx):
    sp.call(
        ['ssh-keygen', '-f', os.path.expanduser('~/.ssh/known_hosts'),
         '-R', ctx.obj['vm']['hostname']])
    utils.ansible_playbook(
        'localhost', playbook_content=PLAYBOOK_DESTROY.substitute(
            hostname=ctx.obj['vm']['hostname'],
            hostnames=' '.join(ctx.obj['vm']['hostnames'])))
    sp.call(
        ['sudo', 'lxc-destroy', '--force',
         '--name', ctx.obj['vm']['hostname']])


@click.command()
@click.pass_context
def provision(ctx):
    utils.ansible_playbook(
        ctx.obj['vm']['hostname'],
        playbook_content=PLAYBOOK_UP_CONTAINER)
    utils.ansible_playbook(
        ctx.obj['vm']['hostname'],
        ctx.obj['vm']['provision']['ansible']['playbook'],
        ctx.obj['vm']['provision']['ansible'].get('extra_vars'))


@click.command()
@click.pass_context
def status(ctx):
    os.execvp(
        'lxc-info',
        ['sudo', 'lxc-info', '--name', ctx.obj['vm']['hostname']])


@click.command()
@click.argument('hostname')
def init(hostname):
    lxcwfile = yaml.dump(
        dict([('nopasswd_sudoer', False),
              ('vm',
               dict([('box',
                      dict([('distro', utils.os_distro()),
                            ('release', utils.os_release())])),
                     ('hostname', str(hostname)),
                     ('provision',
                      dict([('ansible',
                             dict([('playbook',
                                    'provision/playbook.yml')]))]))]))]),
        default_flow_style=False)
    output = re.sub(r'^\s(\s+provision)', r'#\1',
                    re.sub(r'^\s(\s+ansible)', r'#\1',
                           re.sub(r'^\s(\s+playbook)', r'#\1', lxcwfile,
                                  flags=re.M), flags=re.M), flags=re.M)
    with open('lxcwfile.yml', 'w') as stream:
        stream.write(output)


cli.add_command(destroy)
cli.add_command(init)
cli.add_command(halt)
cli.add_command(ls)
cli.add_command(provision)
cli.add_command(status)
cli.add_command(ssh)
cli.add_command(up)
