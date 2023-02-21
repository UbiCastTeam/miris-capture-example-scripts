#!/bin/bash
# remember to disable the timeout by setting recording_stopped_script_timeout to 0 (or to a high value)
FILE=`find $1 -iname *.mp4`
curl -T $FILE ftp://user:pass@ftp.domain.com
