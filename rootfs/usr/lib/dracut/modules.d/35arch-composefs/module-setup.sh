#!/bin/bash

check() {
    return 0
}

depends() {
    echo bootc
    return 0
}

install() {
    dracut_install /usr/bin/mount.composefs
    dracut_install /usr/lib/bootc/arch-composefs-setup
}
