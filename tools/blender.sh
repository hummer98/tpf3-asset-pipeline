#!/bin/sh
# Run Blender headless (flatpak) with a Python script.
# --factory-startup keeps user prefs/add-ons out so builds are reproducible.
# usage: tools/blender.sh <script.py> [-- script args...]
script="$(realpath "$1")"; shift
exec flatpak run org.blender.Blender -b --factory-startup --python-exit-code 1 -P "$script" "$@"
