#!/bin/bash

#Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
apt install -y jq

#Get our address
TAG_NAME="address"
INSTANCE_ID="`wget -qO- http://169.254.169.254/latest/meta-data/instance-id`"
REGION='us-west-2'
TAG_VALUE="`aws ec2 describe-tags --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=$TAG_NAME" --region $REGION --output=text | cut -f5`"

#Get the BLSKEY for this node
BLSKEY=$(aws dynamodb get-item --table-name vanaheim --key=' {"address": {"S":"'${TAG_VALUE}'"} } ' --attributes-to-get blssecret --region $REGION | jq -r '.[] | .[] | .S')
sed -i "s/masternodeblsprivkey=.*/masternodeblsprivkey=$BLSKEY/g" /dash/.dashcore/dash.conf

#what's my IP?
IP=$(dig +short myip.opendns.com @resolver1.opendns.com)
sed -i "s/externalip=.*/externalip=$IP/g" /dash/.dashcore/dash.conf