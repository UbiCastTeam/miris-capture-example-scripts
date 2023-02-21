#!/bin/bash
### SONY cameras
set -e

# call preset
curl http://192.168.12.11/command/presetposition.cgi?PresetCall=1,24
