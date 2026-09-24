#!/bin/sh
set -eu
rsync -a . "$1":/srv/app
