#!/usr/bin/env bash

set -xe

#Installs all the editors and set gui applications
bash /home/ubuntu/p4-learning/vm/bin/gui-apps.sh

#Install Extra Networking Tools and Helpers
bash /home/ubuntu/p4-learning/vm/bin/misc-install.sh

# Install P4lang tools
bash /home/ubuntu/p4-learning/vm/bin/install-p4-tools.sh
