#!/bin/sh
set -eu

# NVIDIA Container Toolkit mounts its Debian/Ubuntu driver libraries here. Alpine
# uses musl, whose default lookup path does not include this directory.
if [ -d /usr/lib/x86_64-linux-gnu ]; then
    export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

exec "$@"
