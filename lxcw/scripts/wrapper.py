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
    try:
        # Add user to sudoers to allow run sudo commands without password
        user = os.environ['USER']
        utils.ansible(
            'localhost', 'lineinfile',
            'dest=/etc/sudoers line="{} ALL=(ALL) NOPASSWD:ALL"'
            ' state=present'.format(user),
            ctx.obj['ask_become_pass'])
        output = sp.check_output(
            ['sudo', 'lxc-info', '--name', ctx.obj['vm']['hostname']])
    except sp.CalledProcessError:
        output = None
    finally:
        message = (
            'is not running' if utils.os_version() == 'precise'
            else "doesn't exist")
        if not output or message in output:
            packages = [
                'python', 'python-pip', 'python-dev', 'build-essential']
            cmd = ['sudo', 'lxc-create', '-t', 'ubuntu',
                   '--name', ctx.obj['vm']['hostname'], '--',
                   '--bindhome', user, '--user', user, '--packages',
                   ','.join(packages), '--release', ctx.obj['vm']['box']]
            sp.call(cmd)

            utils.ansible_playbook(
                'localhost', playbook_content=PLAYBOOK_UP.substitute(
                    hostname=ctx.obj['vm']['hostname'],
                    hostnames=' '.join(ctx.obj['vm']['hostnames']),
                    ip=utils.random_unused_ip(), user=user),
                ask_become_pass=ctx.obj['ask_become_pass'])

            sp.call(['sudo', 'service', 'lxc-net', 'restart'])
            sp.call(
                ['sudo', 'lxc-start', '--name', ctx.obj['vm']['hostname']])
            if 'provision' in ctx.obj['vm']:
                utils.ansible_playbook(
                    ctx.obj['vm']['hostname'],
                    ctx.obj['vm']['provision']['ansible']['playbook'],
                    ctx.obj['vm']['provision']['ansible'].get('extra_vars'),
                    ctx.obj['ask_become_pass'])
        else:
            sp.call(
                ['sudo', 'lxc-start', '--name', ctx.obj['vm']['hostname']])

        # Remove nopasswd user from sudoers
        utils.ansible(
            'localhost', 'lineinfile',
            'dest=/etc/sudoers line="{} ALL=(ALL) NOPASSWD:ALL"'
            ' state=absent'.format(user),
            ctx.obj['ask_become_pass'])

@click.command()
def ls():
    cmd = ['sudo', 'lxc-ls']
    if utils.os_version() != 'precise':
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
    - lineinfile: dest=/etc/hosts line="${ip} ${hostnames}" state=absent
    - lineinfile: dest=/etc/dnsmasq.d/lxc line="dhcp-host=${hostname},${ip}" state=absent
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
            hostnames=' '.join(ctx.obj['vm']['hostnames']),
            ip=utils.ip(ctx.obj['vm']['hostname'])),
        ask_become_pass=ctx.obj['ask_become_pass'])
    sp.call(
        ['sudo', 'lxc-stop', '--name', ctx.obj['vm']['hostname'], '--nokill'])
    sp.call(['sudo', 'lxc-destroy', '--name', ctx.obj['vm']['hostname']])


@click.command()
@click.pass_context
def provision(ctx):
    utils.ansible_playbook(
        ctx.obj['vm']['hostname'],
        ctx.obj['vm']['provision']['ansible']['playbook'],
        ctx.obj['vm']['provision']['ansible'].get('extra_vars'),
        ctx.obj['ask_become_pass'])


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
        dict([('ask_become_pass', True),
              ('vm',
               dict([('box', utils.os_version()),
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
