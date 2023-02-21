#!/bin/bash
# remember to disable the timeout by setting recording_stopped_script_timeout to 0 (or to a high value)
FILE=`find $1 -iname *.mp4`

# user/password authentication
curl -k "sftp://server.com" --user "user:pass" -T $FILE

# ssh key authentication; remember to add the ~/.ssh/miris-manager-client-key.pub into the authorized keys file of the remote server
#curl -k -T $FILE "sftp://user@server.com/" --key /home/ubicast/.ssh/miris-manager-client-key --pubkey /home/ubicast/.ssh/miris-manager-client-key.pub
