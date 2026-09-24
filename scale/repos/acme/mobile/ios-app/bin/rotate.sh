#!/bin/sh
set -eu
find /var/log -name '*.log' -mtime +7 -delete
