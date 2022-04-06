# register_devnet_masternodes

This software will add a lot of masternodes to a Dash devnet very quickly using AWS, it's to be used in conjuction with https://github.com/dashevo/dash-network-deploy

Advising if you use this tool to deploy a devnet first using the above tool with a single masternode, this will ensure it completes within 30-60 minutes. 
Once complete take an AMI of the masternode created and name it devnet-masternode (replace devnet with your devnet name)

* Step 1: Create image of existing masternode created by dash-network-deploy
* Step 2: Put the image ID in register.py and fill the rest (L15-23)
* Step 3: Create a dynamodb table in AWS called 'devnet' - eg simply 'vanaheim' or 'malort'
* Step 4: Ensure you have an IAM role for dashdev on AWS under 'default' in ~/.aws/credentials
* Step 5: Ensure an IAM role exists called vanaheim-masternode with read/write to dynamo, read access to EC2 (at least itself) and read access to SQS

For step 5 the devnet name is hardcoded to vanaheim, it doesn't matter as long as it exists.
