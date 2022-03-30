#!/bin/bash

#Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
apt install -y jq

#Get our address
INSTANCE_ID="`wget -qO- http://169.254.169.254/latest/meta-data/instance-id`"
TAG_VALUE=$(aws sqs receive-message --queue-url https://sqs.us-west-2.amazonaws.com/854439639386/vanaheim.fifo | jq -r '.[] | .[] | .Body')
REGION='us-west-2'
DEVNET="`aws ec2 describe-tags --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=devnet" --region $REGION --output=text | cut -f5`"

#Get the BLSKEY for this node
BLSKEY=$(aws dynamodb get-item --table-name $DEVNET --key=' {"address": {"S":"'${TAG_VALUE}'"} } ' --attributes-to-get blssecret --region $REGION | jq -r '.[] | .[] | .S')
#Done from the master python script instead for now....
#sed -i "s/masternodeblsprivkey=.*/masternodeblsprivkey=$BLSKEY/g" /dash/.dashcore/dash.conf

#what's my IP?
IP=$(dig +short myip.opendns.com @resolver1.opendns.com)
sed -i "s/externalip=.*/externalip=$IP/g" /dash/.dashcore/dash.conf

rm -rf /dash/.dashcore/devnet-$DEVNET
docker restart dashd