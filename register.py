import paramiko
import time
import boto3
# SIMPLY A PROOF OF CONCEPT

#This script assumes you already have a network running...
#Step 1: Create image of existing masternode created by dash-network-deploy
#Step 2: Put the image ID in below and fill the rest (L15-23)
#Step 3: Create a dynamodb table in AWS called 'devnet' - eg simply 'vanaheim' or 'malort'
#Step 3.5: Create a FIFO SQS table with a blinding time of at least 2 hours (so masternodes can receive their addresses)
#Step 4: Ensure you have an IAM role for dashdev on AWS under 'default' in ~/.aws/credentials
#Step 5: Ensure an IAM role exists called devnet-masternode (eg malort-masternode) with read/write to dynamo, read access to EC2 (at least itself) and read access to SQS

image_id = 'ami-05bf636864923cd4c' #an existing image from a masternode on the network
devnet = 'vanaheim'
key_location = '/home/monotoko/.ssh/evo-app-deploy.rsa' #give full path, doesn't work with ~
dashd_protx_server = '34.221.207.161' #also called dashd-wallet-2
dashd_premine_server = '54.203.97.105' #also called dashd-wallet-1
payee = 'yaxpG7hBNgBE3LwRzgjP3DVZfSDj1XJ9Fm' #not used at the moment
nodes = 2 #how many masternodes need setting up
startkey = 0 #Set up to last deployment, for example if you've already deployed 5 using this script set this to 5.
subnet_id = 'subnet-07f340b252323b3f4' #Get this from AWS, it's generally going to be where your devnet is
SGIDs = ['sg-07fd40822dd7f5ba3','sg-0050038afb32b3f05','sg-0af95842b67c96efd'] #Get these from an existing masternode

#Fun fun fun
sqs_client = boto3.client("sqs", region_name='us-west-2')

collat_addresses = []
voting_addresses = []
payout_addresses = []
bls_secret_addresses = []
bls_public_addresses = []
coll_txids = []
ip_addresses = []
final_txids = []
instance_ids = []

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

#Dynamo!
dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
table = dynamodb.Table(devnet)

#Generate addresses for each node
for i in range(nodes):
    #connect to get new address
    ssh.connect(dashd_protx_server, username='ubuntu', key_filename=key_location)
    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getnewaddress')
    stdin.close()

    #set address
    #new_dash_address = stdout.readlines()[0].strip()
    collat_addresses.append(stdout.readlines()[0].strip())
    print(collat_addresses[i])

    #Put the collateral address into SQS for the nodes to retreive later
    msg_body='{}'.format(collat_addresses[i])
    msg_attributes={ 'address': {'DataType': 'String','StringValue': 'address{}'.format(i)}}
    response = sqs_client.send_message(QueueUrl='https://sqs.us-west-2.amazonaws.com/854439639386/vanaheim.fifo',MessageAttributes=msg_attributes,MessageBody=msg_body,MessageGroupId="main8"+str(i),MessageDeduplicationId="main8"+str(i))
    print("DEBUG: Sent message")

    #do it again for a second address
    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getnewaddress')
    stdin.close()

    #set address
    #voting_address = stdout.readlines()[0].strip()
    voting_addresses.append(stdout.readlines()[0].strip())
    print(voting_addresses[i])

    #do it again for a third address
    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli getnewaddress')
    stdin.close()

    #set address
    payout_addresses.append(stdout.readlines()[0].strip())
    print(payout_addresses[i])

    #blskey

    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli bls generate')
    stdin.close()
    blskey = stdout.readlines()
    ssh.close()
    #print(blskey)

    #Do some format fixing... (hacky)
    blssecret = blskey[1].strip()[11:-2]
    bls_secret_addresses.append(blssecret)
    print(bls_secret_addresses[i])

    blspubkey = blskey[2].strip()[11:-1]
    bls_public_addresses.append(blspubkey)
    print(bls_public_addresses[i])

    #connect to dashd-wallet-1 to get 1000 shiny tdash
    ssh.connect(dashd_premine_server, username='ubuntu', key_filename=key_location)
    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli sendtoaddress {} 1000'.format(collat_addresses[i]))
    stdin.close()

    #We'll need this for protx later + wait for next block
    coll_txids.append(stdout.readlines()[0].strip())

    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli sendtoaddress {} 1'.format(payout_addresses[i]))
    stdin.close()

    respose = table.put_item(
        Item={
            'address': collat_addresses[i],
            'blspublic': bls_public_addresses[i],
            'blssecret': bls_secret_addresses[i],
            'txid': coll_txids[i]
        }
    )

#Now we have all addresses and collaterals filled.. we must wait for a block

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

#Launch the machine(s) - some of this needs to be dynamic eventually.
tag_purpose_devnet = {"Key": "devnet", "Value": devnet}
ec2 = boto3.resource('ec2', region_name='us-west-2')
response = ec2.create_instances(
    ImageId=image_id,
    InstanceType='t3.medium',
    MaxCount=nodes,
    MinCount=nodes,
    KeyName='dn-devnet-{}-auth'.format(devnet),
    Monitoring={
        'Enabled': False
    },
    SecurityGroupIds=SGIDs,
    IamInstanceProfile={
        'Name': '{}-masternode'.format(devnet)
    },
    UserData=open("init.sh").read(),
    SubnetId=subnet_id,
    TagSpecifications=[{'ResourceType': 'instance',
                            'Tags': [tag_purpose_devnet]}])

#Wait until last one is running...
response[-1].wait_until_running()

#reload all
for r in response:
    r.reload()

for i in response:
    ip_addresses.append(i.public_ip_address)
    instance_ids.append(i.instance_id)

# #protx register_prepare collateralHash collateralIndex ipAndPort ownerKeyAddr operatorPubKey votingKeyAddr operatorReward payoutAddress (feeSourceAddress)

#Connect back to dash-wallet-2 to prepare protx
ssh.connect(dashd_protx_server, username='ubuntu', key_filename=key_location)
for i in range(nodes):
    protx_command = 'sudo -i dash-cli protx register_prepare {} 1 {}:20001 {} {} {} 0 {}'.format(coll_txids[i], ip_addresses[i], voting_addresses[i], bls_public_addresses[i], voting_addresses[i], payout_addresses[i])
    print("DEBUG: "+protx_command)

    stdin, stdout, stderr = ssh.exec_command(protx_command)
    stdin.close()
    protx_output = stdout.readlines()

    #Really hacky way of getting what we want from the CLI/json because it comes to us weirdly through SSH (but it works!)
    tx = protx_output[1][9:-3]
    signthismessage = protx_output[3][17:-1]

    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli signmessage {} {}'.format(collat_addresses[i], signthismessage))
    stdin.close()

    signed_output = stdout.readlines()[0].strip()
    print(signed_output)

    #one last hurrah!
    stdin, stdout, stderr = ssh.exec_command('sudo -i dash-cli protx register_submit {} {}'.format(tx, signed_output))
    stdin.close()

    final_txids.append(stdout.readlines()[0].strip())

#Write the important stuff once complete....
with open('debug.log', 'a') as file:
    for i in ip_addresses:
        file.write("%s\n" % i)
    for i in final_txids:
        file.write("%s\n" % i)
    for i in instance_ids:
        file.write("%s\n" % i)