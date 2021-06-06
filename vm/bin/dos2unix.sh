#!/usr/bin/env bash

apt-get install dos2unix
find /home/ubuntu/p4-learning/vm/bin/ -not -name "*dos2unix.sh" -type f  -print0 | xargs -0 dos2unix
find /home/ubuntu/p4-learning/vm/vm_files/ -not -name "*dos2unix.sh" -type f  -print0 | xargs -0 dos2unix

#provision vm_files after dos2unix
cp /home/ubuntu/p4-learning/vm/vm_files/p4_16-mode.el /home/ubuntu/p4_16-mode.el
cp /home/ubuntu/p4-learning/vm/vm_files/p4.vim /home/ubuntu/p4.vim
cp /home/ubuntu/p4-learning/vm/vm_files/nsg-logo.png /home/ubuntu/nsg-logo.png
cp /home/ubuntu/p4-learning/vm/vm_files/tmux.conf /home/ubuntu/.tmux.conf
