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


@click.command()
@click.pass_context
def ssh_copy_id(ctx):
    os.execvp('ssh-copy-id',
              ['ssh-copy-id', '{}@{}'.format(
                  os.environ['USER'], ctx.obj['vm']['hostname'])])


def user_add(name, user):
    sp.call(
        ['lxc-start', '--name', name])
    sp.call(
        ['lxc-attach', '--name', name, '--',
         'useradd', '--create-home', user,
         '-p', crypt.crypt('passwd', 'aa')])
    sp.call(
        ['lxc-stop', '--name', name])


def bind_home(name, user):
    sp.call(
        ['lxc-start', '--name', name])
    passwd = sp.check_output(['getent', 'passwd', user])
    sp.call(
        ['lxc-attach', '--name', name, '--', 'sed', '-i',
         '$ a\{}'.format(passwd), '/etc/passwd'])
    shadow = sp.check_output(['sudo', 'getent', 'shadow', user])
    sp.call(
        ['lxc-attach', '--name', name, '--', 'sed', '-i',
         '$ a\{}'.format(shadow), '/etc/shadow'])
    home = passwd.split(':')[5]
    sp.call(
        ['lxc-attach', '--name', name, '--', 'mkdir', '-p', home])
    config = os.path.join(
        os.path.expanduser('~/.local/share/lxc/'), name, 'config')
    with open(config, 'a') as f:
        f.write('lxc.mount.entry = {0} {0} none bind 0 0'.format(home))
    sp.call(
        ['lxc-attach', '--name', name, '--', 'sed', '-i',
         '$ a\{}'.format(sp.check_output(['getent', 'group', user])),
         '/etc/group'])
    sp.call(
        ['lxc-stop', '--name', name])


def install_packages(rootfs, packages, manager='apt-get'):
    sp.call(
        ['lxc-attach', '--name', name, '--', manager, 'install', '-y']
        + packages)
    # sp.call(['sudo', 'chroot', rootfs, manager, 'install', '-y'] + packages)


PLAYBOOK_UP = string.Template('''
---
- hosts: all
  become: yes
  tasks:
    - lineinfile: dest=/etc/default/lxc-net regexp=LXC_DHCP_CONFILE line=LXC_DHCP_CONFILE=/etc/dnsmasq.d/lxc
    - lineinfile: dest=/etc/dnsmasq.d/lxc line="dhcp-host=${hostname},${ip}"
    - lineinfile: dest=/etc/hosts line="${ip} ${hostnames}"
    - lineinfile: dest=${rootfs}/etc/sudoers line="${user} ALL=(ALL) NOPASSWD:ALL" state=present
''')


@click.command()
@click.pass_context
def up(ctx):
    if ctx.obj['vm']['box']['distro'] == 'ubuntu':
        if float(ctx.obj['vm']['box']['release']) < 12.04:
            click.secho(
                'Only Ubuntu >= 12.04 container supported', fg='red')
            sys.exit(1)
    elif ctx.obj['vm']['box']['distro'] == 'centos':
        if int(ctx.obj['vm']['box']['release']) < 6:
            click.secho(
                'Only CentOS >= 6 container supported', fg='red')
            sys.exit(1)
    else:
        click.secho(
            'Only Ubuntu and CentOS containers supported', fg='red')
        sys.exit(1)

    try:
        output = sp.check_output(
            ['lxc-info', '--name', ctx.obj['vm']['hostname']])
    except sp.CalledProcessError:
        output = None
    finally:
        message = (
            'is not running' if utils.os_release() == '12.04'
            else "doesn't exist")
        if not output or message in output:
            sp.call([
                'lxc-create', '--template', 'download',
                '--name', ctx.obj['vm']['hostname'], '--',
                '--dist', ctx.obj['vm']['box']['distro'],
                '--release', ctx.obj['vm']['box']['release'],
                '--arch', utils.os_arch()])

            rootfs = os.path.join(
                os.path.expanduser('~/.local/share/lxc/'),
                ctx.obj['vm']['hostname'], 'rootfs')
            if ctx.obj['vm']['box']['distro'] == 'ubuntu':
                bind_home(ctx.obj['vm']['hostname'], os.environ['USER'])
                install_packages(
                    rootfs, ['python', 'python-pip', 'python-dev',
                             'build-essential'])
            elif ctx.obj['vm']['box']['distro'] == 'centos':
                user_add(ctx.obj['vm']['hostname'], os.environ['USER'])
                install_packages(
                    rootfs, ['sudo', 'gcc', 'openssh-server', 'epel-release'],
                    'yum')
                install_packages(rootfs, ['python-pip'], 'yum')

            utils.ansible_playbook(
                'localhost', playbook_content=PLAYBOOK_UP.substitute(
                    hostname=ctx.obj['vm']['hostname'],
                    hostnames=' '.join(ctx.obj['vm']['hostnames']),
                    ip=utils.random_unused_ip(), user=os.environ['USER'],
                    rootfs=rootfs))
            sp.call(['sudo', 'service', 'lxc-net', 'restart'])
            sp.call(
                ['lxc-start', '--name', ctx.obj['vm']['hostname']])

            if 'provision' in ctx.obj['vm']:
                utils.ansible_playbook(
                    ctx.obj['vm']['hostname'],
                    playbook_contents='\n'.join(
                        ["- locale_gen: name={0} state=present".format(locale)
                         for locale in ctx.obj['vm']['provision']['locales']]))
                utils.ansible_playbook(
                    ctx.obj['vm']['hostname'],
                    ctx.obj['vm']['provision']['ansible']['playbook'],
                    extra_vars=ctx.obj['vm']['provision']['ansible'].get('extra_vars'))
        else:
            sp.call(
                ['lxc-start', '--name', ctx.obj['vm']['hostname']])


@click.command()
def ls():
    cmd = ['lxc-ls']
    if float(utils.os_release()) > 12.04:
        cmd += ['--fancy']
    sp.call(cmd)


@click.command()
@click.pass_context
def halt(ctx):
    sp.call(
        ['lxc-stop', '--name', ctx.obj['vm']['hostname'], '--nokill'])


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
        ['sudo', 'lxc-destroy', '--force', '--name', ctx.obj['vm']['hostname']])


@click.command()
@click.pass_context
@click.argument('tags', nargs=-1)
@click.option('-v', '--verbose', type=bool, default=False, is_flag=True)
def provision(ctx, tags, verbose):
    if 'provision' in ctx.obj['vm']:
        utils.ansible_playbook(
            ctx.obj['vm']['hostname'],
            ctx.obj['vm']['provision']['ansible']['playbook'],
            extra_vars=ctx.obj['vm']['provision']['ansible'].get('extra_vars'),
            tags=tags, verbose=verbose)
    else:
        click.secho(
            'Nothing to be done', fg='blue')


@click.command()
@click.pass_context
def status(ctx):
    sp.call(
        ['lxc-info', '--name', ctx.obj['vm']['hostname']])


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
                      dict([
                          ('locales', ['es_ES.UTF-8']),
                          ('ansible',
                           dict([('playbook',
                                  'provision/playbook.yml')]))]))]))]),
        default_flow_style=False)
    output = re.sub(r'^(\s+ansible)', r'#\1',
                    re.sub(r'^(\s+playbook)', r'#\1', lxcwfile,
                           flags=re.M), flags=re.M)
    with open('lxcwfile.yml', 'w') as stream:
        stream.write(output)


cli.add_command(destroy)
cli.add_command(init)
cli.add_command(halt)
cli.add_command(ls)
cli.add_command(provision)
cli.add_command(status)
cli.add_command(ssh)
cli.add_command(ssh_copy_id, 'ssh-copy-id')
cli.add_command(up)
