import json
import subprocess as sp

import click

from .. import utils


@click.command()
@click.option('--list', is_flag=True)
@click.option('--host')
def inventory(list, host):
    if host:
        data = {'ansible_ssh_host': utils.ip(host)}
    else:
        containers = sp.check_output(['sudo', 'lxc-ls']).splitlines()
        data = {'containers': containers}
    click.echo(json.dumps(data))
