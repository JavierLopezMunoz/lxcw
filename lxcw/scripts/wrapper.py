from distutils import spawn
import json
import os
import re
import subprocess as sp
import sys
import yaml

import click

from .. import utils


@click.group()
@click.pass_context
@click.option('--ask-sudo-pass', default=False, is_flag=True)
def cli(ctx, ask_sudo_pass):
    if ctx.invoked_subcommand not in ('init', 'ls'):
        try:
            with open("lxcwfile.yml", 'r') as stream:
                ctx.obj = yaml.load(stream)[0]
                ctx.obj['ask_sudo_pass'] = ask_sudo_pass
        except IOError as err:
            click.secho('No \'lxcwfile.yml\' present', fg='red')
            sys.exit(1)


@click.command()
@click.pass_context
def ssh(ctx):
    os.execvp('ssh',
              ['ssh', ctx.obj['vm']['hostname'], '-l', os.environ['USER']])


@click.command()
@click.pass_context
def up(ctx):
    try:
        output = sp.check_output(
            ['sudo', 'lxc-info', '--name', ctx.obj['vm']['hostname']])
    except sp.CalledProcessError:
        output = None
    finally:
        message = (
            'is not running' if utils.os_version() == 'precise'
            else "doesn't exist")
        if not output or message in output:
            user = os.environ['USER']
            packages = [
                'python', 'python-pip', 'python-dev', 'build-essential']
            cmd = ['sudo', 'lxc-create', '-t', 'ubuntu',
                   '--name', ctx.obj['vm']['hostname'], '--',
                   '--bindhome', user, '--user', user, '--packages',
                   ','.join(packages), '--release', ctx.obj['vm']['box']]
            sp.call(cmd)

            utils.ansible_local(
                'lineinfile',
                'dest=/etc/default/lxc-net regexp=LXC_DHCP_CONFILE'
                ' line=LXC_DHCP_CONFILE=/etc/dnsmasq.d/lxc',
                ctx.obj['ask_sudo_pass'])

            IP = utils.random_unused_ip()
            utils.ansible_local(
                'lineinfile',
                'dest=/etc/dnsmasq.d/lxc line=dhcp-host={},{}'.format(
                    ctx.obj['vm']['hostname'], IP),
                ctx.obj['ask_sudo_pass'])
            sp.call(['sudo', 'service', 'lxc-net', 'restart'])

            utils.ansible_local(
                'lineinfile',
                'dest=/etc/hosts line=\'{0} {1}\''.format(
                    IP, ' '.join([ctx.obj['vm']['hostname']]
                                 + ctx.obj['vm']['aliases'])),
                ctx.obj['ask_sudo_pass'])

            sp.call(
                ['sudo', 'lxc-start', '--name', ctx.obj['vm']['hostname'],
                 '--daemon'])
            utils.ansible(
                IP, 'lineinfile',
                'dest=/etc/sudoers state=present regexp=\'^%sudo ALL\=\''
                ' line=\'%sudo ALL=(ALL:ALL) NOPASSWD:ALL\''
                ' validate=\'visudo -cf %s\'',
                ask_become_pass=True)
        else:
            sp.call(
                ['sudo', 'lxc-start', '--name', ctx.obj['vm']['hostname'],
                 '--daemon'])


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


@click.command()
@click.pass_context
def destroy(ctx):
    sp.call(
        ['sudo', 'lxc-stop', '--name', ctx.obj['vm']['hostname'], '--nokill'])
    sp.call(['sudo', 'lxc-destroy', '--name', ctx.obj['vm']['hostname']])
    sp.call(
        ['ssh-keygen', '-f', os.path.expanduser('~/.ssh/known_hosts'),
         '-R', ctx.obj['vm']['hostname']])
    utils.ansible_local(
        'lineinfile',
        'dest=/etc/hosts regexp=\'10.0.3.[0-9]* {}\' state=absent'.format(
            ctx.obj['vm']['hostname']),
        ctx.obj['ask_sudo_pass'])
    utils.ansible_local(
        'lineinfile',
        'dest=/etc/dnsmasq.d/lxc regexp=\'dhcp-host={},10.0.3.[0-9]*\''
        ' state=absent'.format(ctx.obj['vm']['hostname']),
        ctx.obj['ask_sudo_pass'])
    sp.call(['sudo', 'service', 'lxc-net', 'restart'])


@click.command()
@click.pass_context
def provision(ctx):
    cmd = [
        'ansible-playbook', '-l', ctx.obj['vm']['hostname'],
        '-i', spawn.find_executable('lxci')]
    if 'extra_vars' in ctx.obj['vm']['provision']['ansible']:
        cmd += ['--extra-vars',
                json.dumps(
                    ctx.obj['vm']['provision']['ansible']['extra_vars'])]
    cmd += [
        os.path.join(os.getcwd(),
                     ctx.obj['vm']['provision']['ansible']['playbook'])]
    if ctx.obj['ask_sudo_pass']:
        cmd += ['--ask-become-pass']
    sp.call(cmd)


@click.command()
@click.pass_context
def status(ctx):
    os.execvp(
        'lxc-info',
        ['sudo', 'lxc-info', '--name', ctx.obj['vm']['hostname']])


@click.command()
@click.argument('hostname')
def init(hostname):
    lxcwfile = yaml.dump([
        dict([('vm',
               dict([('box', utils.os_version()),
                     ('hostname', str(hostname)),
                     ('provision',
                      dict([('ansible',
                             dict([('playbook',
                                    'provision/playbook.yml')]))]))]))])],
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
