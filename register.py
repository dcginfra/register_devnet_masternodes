import paramiko
import time
import boto3
import pdb

# SIMPLY A PROOF OF CONCEPT

#This script assumes you already have a network running...
#Step 1: Create image of existing masternode created by dash-network-deploy
#Step 2: Put the image ID in below and fill the rest (L15-21)
#Step 3: Create a dynamodb table in AWS called 'devnet' - eg simply 'vanaheim' or 'malort'
#Step 4: Ensure you have an IAM role for dashdev on AWS under 'default' in ~/.aws/credentials
#Step 5: Ensure an IAM role exists called devnet-masternode (eg malort-masternode) with read/write to dynamo and read access to EC2 (at least itself)

image_id = 'ami-05bf636864923cd4c'
devnet = 'vanaheim'
key_location = '/home/monotoko/.ssh/evo-app-deploy.rsa' #give full path, doesn't work with ~
dashd_protx_server = '34.221.207.161'
dashd_premine_server = '54.203.97.105'
payee = 'yaxpG7hBNgBE3LwRzgjP3DVZfSDj1XJ9Fm' #not used at the moment
nodes = 1 #how many masternodes need setting up (not used yet, just does a single MN as a POC)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

#connect to get new address
ssh.connect(dashd_protx_server, username='ubuntu', key_filename=key_location)
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getnewaddress')
stdin.close()

#set address
new_dash_address = stdout.readlines()[0].strip()
print(new_dash_address)

#do it again for a second address
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getnewaddress')
stdin.close()

#set address
voting_address = stdout.readlines()[0].strip()
print(voting_address)

#do it again for a second address
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getnewaddress')
stdin.close()

#set address
payout_address = stdout.readlines()[0].strip()
print(payout_address)

#blskey

stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli bls generate')
stdin.close()
blskey = stdout.readlines()
ssh.close()
print(blskey)

#Do some format fixing...
blssecret = blskey[1].strip()[11:-2]
print(blssecret)
blspubkey = blskey[2].strip()[11:-1]
print(blspubkey)

#connect to dashd-wallet-1 to get 1000 shiny tdash
ssh.connect(dashd_premine_server, username='ubuntu', key_filename=key_location)
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli sendtoaddress {} 1000'.format(new_dash_address))
stdin.close()

#We'll need this for protx later + wait for next block
collat_txid = stdout.readlines()[0].strip()

ssh.connect(dashd_premine_server, username='ubuntu', key_filename=key_location)
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli sendtoaddress {} 10'.format(payout_address))
stdin.close()

ssh.connect(dashd_premine_server, username='ubuntu', key_filename=key_location)
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getblockcount')
stdin.close()

block_count = stdout.readlines()[0].strip()
ssh.close()
print("Current block count: "+block_count)
new_block_count = block_count

while block_count == new_block_count:
    ssh.connect(dashd_premine_server, username='ubuntu', key_filename=key_location)
    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getblockcount')
    stdin.close()

    new_block_count = stdout.readlines()[0].strip()
    if new_block_count == block_count:
        print("Still "+new_block_count+": sleeping")
        time.sleep(30)


#Dynamo!
dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
table = dynamodb.Table('vanaheim')

respose = table.put_item(
    Item={
        'address': new_dash_address,
        'blspublic': blspubkey,
        'blssecret': blssecret,
        'txid': collat_txid
    }
)

#Launch the machine - some of this needs to be dynamic eventually.
ec2 = boto3.resource('ec2', region_name='us-west-2')
tag_purpose_test = {"Key": "address", "Value": new_dash_address} #Don't add another tag here, it overwrites existing... as tempting as it is to add the NAME here
response = ec2.create_instances(
    ImageId=image_id,
    InstanceType='t3.medium',
    MaxCount=1,
    MinCount=1,
    KeyName='dn-devnet-{}-auth'.format(devnet),
    Monitoring={
        'Enabled': False
    },
    SecurityGroupIds=[
        'sg-07fd40822dd7f5ba3',
        'sg-0050038afb32b3f05',
        'sg-0af95842b67c96efd'
    ],
    IamInstanceProfile={
        'Name': 'vanaheim-masternode'
    },
    UserData=open("init.sh").read(),
    SubnetId='subnet-07f340b252323b3f4',
    TagSpecifications=[{'ResourceType': 'instance',
                        'Tags': [tag_purpose_test]}])[0]
response.wait_until_running()
response.reload()
ip_addr = response.public_ip_address
print(ip_addr)

# #Insert blskey and launch the machine here

# # Do some boto3 stuff to launch the AWS instance using init.sh as 

# #protx register_prepare collateralHash collateralIndex ipAndPort ownerKeyAddr operatorPubKey votingKeyAddr operatorReward payoutAddress (feeSourceAddress)

#Connect back to dash-wallet-2 to prepare protx

protx_command = 'sudo -i dash-cli protx register_prepare {} 1 {}:20001 {} {} {} 0 {}'.format(collat_txid, ip_addr, voting_address, blspubkey, voting_address, payout_address)
print("DEBUG: "+protx_command)

ssh.connect(dashd_protx_server, username='ubuntu', key_filename='/home/monotoko/.ssh/evo-app-deploy.rsa')
stdin, stdout, stderr = ssh.exec_command(protx_command)
stdin.close()
protx_output = stdout.readlines()

#Really hacky way of getting what we want from the CLI/json because it comes to us weirdly through SSH (but it works!)
tx = protx_output[1][9:-3]
#new_dash_address is our coll address
signthismessage = protx_output[3][17:-1]

ssh.connect(dashd_protx_server, username='ubuntu', key_filename='/home/monotoko/.ssh/evo-app-deploy.rsa')
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli signmessage {} {}'.format(new_dash_address, signthismessage))
stdin.close()

signed_output = stdout.readlines()[0].strip()
print(signed_output)

#one last hurrah!
ssh.connect(dashd_protx_server, username='ubuntu', key_filename='/home/monotoko/.ssh/evo-app-deploy.rsa')
stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli protx register_submit {} {}'.format(tx, signed_output))
stdin.close()

final_tx_id = stdout.readlines()
print("DIP3 TX ID: "+final_tx_id)