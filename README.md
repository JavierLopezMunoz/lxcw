# lxcw

lxcw is a wrapper on top of linux containers using the nomenclature of
vagrant command API.

## Features

- When creating a container, it assigns a static IP to it, adds an
  entry to the hosts file so that the container is reachable.
- Destroying a container cleans up entries in the host file.

## Installation

sudo pip install https://github.com/JavierLopezMunoz/lxcw/archive/master.zip
