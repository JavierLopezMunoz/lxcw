import crypt
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
    if ctx.invoked_subcommand not in ['init']:
        try:
            with open("lxcwfile.yml", 'r') as stream:
                ctx.obj = yaml.load(stream)
                ctx.obj['vm']['box']['release'] = str(
                    ctx.obj['vm']['box']['release'])
                ctx.obj['vm']['name'] = ctx.obj['vm']['hostname'].replace('.', '-')
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
              ['ssh', ctx.obj['vm']['hostname'], '-l', 'ubuntu'])


@click.command()
@click.pass_context
def ssh_copy_id(ctx):
    os.execvp('ssh-copy-id',
              ['ssh-copy-id', 'ubuntu@{}'.format(ctx.obj['vm']['hostname'])])


@click.command()
@click.pass_context
def up(ctx):
    info = utils.info(ctx.obj['vm']['name'])
    if not info:
        sp.call(['lxc', 'init',
                 ':'.join([ctx.obj['vm']['box']['distro'],
                           ctx.obj['vm']['box']['release']]),
                 ctx.obj['vm']['name']])

        sp.call(['lxc', 'config', 'set',
                 ctx.obj['vm']['name'], 'raw.idmap',
                 'both {} 1000'.format(os.getuid())])

        sp.call(['lxc', 'config', 'device', 'add',
                 ctx.obj['vm']['name'], 'homedir', 'disk',
                 'source={}'.format(os.environ['HOME']),
                 'path=/home/ubuntu'])

        sp.call(['lxc', 'start', ctx.obj['vm']['name']])
        utils.ansible(
            'localhost',
            'lineinfile',
            'dest=/etc/hosts line="{ip} {hostnames}"'.format(
                ip=utils.ip(ctx.obj['vm']['name']),
                hostnames=' '.join(ctx.obj['vm']['hostnames'])))

        if 'provision' in ctx.obj['vm']:
            utils.ansible_playbook(
                ctx.obj['vm']['hostname'],
                ctx.obj['vm']['provision']['ansible']['playbook'],
                extra_vars=ctx.obj['vm']['provision']['ansible'].get('extra_vars'))
    else:
        if info['status'].lower() == 'stopped':
            sp.call(['lxc', 'start', ctx.obj['vm']['name']])
            utils.ansible(
                'localhost',
                'lineinfile',
                'dest=/etc/hosts line="{ip} {hostnames}"'.format(
                    ip=utils.ip(ctx.obj['vm']['name']),
                    hostnames=' '.join(ctx.obj['vm']['hostnames'])))
        else:
            click.echo('Container already Running')


@click.command()
@click.pass_context
def halt(ctx):
    sp.call(['lxc', 'stop', ctx.obj['vm']['name']])


@click.command()
@click.pass_context
def destroy(ctx):
    sp.call(['lxc', 'delete', '--force', ctx.obj['vm']['name']])
    sp.call(
        ['ssh-keygen', '-f', os.path.expanduser('~/.ssh/known_hosts'),
         '-R', ctx.obj['vm']['hostname']])
    utils.ansible(
        'localhost',
        'lineinfile',
        'dest=/etc/hosts regexp="\d{{1,3}}\.\d{{1,3}}\.\d{{1,3}}\.\d{{1,3}} {hostnames}"'
        ' state=absent'.format(
            hostnames=' '.join(ctx.obj['vm']['hostnames'])))


@click.command()
@click.pass_context
@click.argument('tags', nargs=-1)
def provision(ctx, tags):
    if 'provision' in ctx.obj['vm']:
        utils.ansible_playbook(
            ctx.obj['vm']['hostname'],
            ctx.obj['vm']['provision']['ansible']['playbook'],
            extra_vars=ctx.obj['vm']['provision']['ansible'].get('extra_vars'),
            tags=tags)
    else:
        click.secho('Nothing to be done', fg='blue')


@click.command()
@click.argument('hostname')
def init(hostname):
    lxcwfile = yaml.dump(
        dict([('vm',
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
cli.add_command(provision)
cli.add_command(ssh)
cli.add_command(ssh_copy_id, 'ssh-copy-id')
cli.add_command(up)
