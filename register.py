import paramiko
import time
import boto3
import argparse
import sys
import pdb
import os.path

parser = argparse.ArgumentParser()
parser.add_argument('--prep','-p', help='prepare protx/collaterals but do not bring up the nodes', action='store_true')
parser.add_argument('--run','-r', help='finish previously prepped setup', action='store_true')
args = parser.parse_args()

# SIMPLY A PROOF OF CONCEPT

#This script assumes you already have a network running...
#Step 1: Create image of existing masternode created by dash-network-deploy
#Step 2: Put the image ID in below and fill the rest (L15-23)
#Step 3: Create a dynamodb table in AWS called 'devnet' - eg simply 'vanaheim' or 'malort'
#Step 4: Ensure you have an IAM role for dashdev on AWS under 'default' in ~/.aws/credentials
#Step 5: Ensure an IAM role exists called devnet-masternode (eg malort-masternode) with read/write to dynamo, read access to EC2 (at least itself) and read access to SQS

image_id = 'ami-0b7fc1b9847b6632e' #an existing image from a masternode on the network
devnet = 'malort'
key_location = '/home/monotoko/.ssh/evo-app-deploy.rsa' #give full path, doesn't work with ~
dashd_protx_server = '54.148.235.29' #also called dashd-wallet-2
dashd_premine_server = '54.186.71.19' #also called dashd-wallet-1
nodes = 600 #how many masternodes need setting up
startkey = 0 #Set up to last deployment, for example if you've already deployed 5 using this script set this to 5.
subnet_id = 'subnet-03a1d16d171df3219' #Get this from AWS, it's generally going to be where your devnet is
SGIDs = ['sg-0b1b6d486a78331df','sg-00a6f910164e234e8','sg-0b93885731314abdd'] #Get these from an existing masternode

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

sshn = paramiko.SSHClient()
sshn.set_missing_host_key_policy(paramiko.AutoAddPolicy())

#Dynamo!
dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
table = dynamodb.Table(devnet)

if args.prep or args == []:
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

    with open('prep.log', 'w') as file:
        for i in range(len(collat_addresses)):
            file.write("%s\n" % collat_addresses[i])
            file.write("%s\n" % voting_addresses[i])
            file.write("%s\n" % payout_addresses[i])
            file.write("%s\n" % bls_secret_addresses[i])
            file.write("%s\n" % bls_public_addresses[i])
            file.write("%s\n" % coll_txids[i])
    if args.prep:
        sys.exit()
    else:
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

if args.run or args == []:

    #If it's empty, it means we still need to load them in from the prep file...
    if collat_addresses == []:
        #Check prep file exists...
        if not os.path.isfile('prep.log'):
            sys.exit("You sent run but no prep log exists!")
        
        toload = int(sum(1 for line in open('prep.log'))/6)
        prepfile = open('prep.log', 'r')        
        
        #'Borrowed' code from a Python God.
        groups = 6
        lists = [[] for _ in range(groups)]
        for i, line in enumerate(prepfile.readlines()):
            lists[i % groups].append(line.strip())
        
        #Restore the originally prepped stuff
        collat_addresses = lists[0]
        voting_addresses = lists[1]
        payout_addresses = lists[2]
        bls_secret_addresses = lists[3]
        bls_public_addresses = lists[4]
        coll_txids = lists[5]


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

    #reload all
    for r in response:
        r.wait_until_running()
        r.reload()

    for i in response:
        ip_addresses.append(i.public_ip_address)
        instance_ids.append(i.instance_id)
    print("Sleeping while instances come up...")
    time.sleep(120)

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

        #Okay this is hacky even for me...
        try:
            sshn.connect(ip_addresses[i], username='ubuntu', key_filename=key_location, banner_timeout=200)
            stdinn, stdoutn, stderrn = sshn.exec_command('sudo sed -i "s/masternodeblsprivkey=.*/masternodeblsprivkey='+bls_secret_addresses[i]+'/g" /dash/.dashcore/dash.conf')
            stdinn.close()
            stdinn, stdoutn, stderrn = sshn.exec_command('sudo docker restart dashd')
            stdinn.close()
            sshn.close()
            print("Replaced blskey of node {}".format(i))
        except:
            print("Something went wrong connecting to node {}".format(i))
    #Delete prep log
    if os.path.exists("prep.log"):
        os.remove("prep.log")
    #Write the important stuff once complete....
    with open('debug.log', 'a') as file:
        for i in ip_addresses:
            file.write("%s\n" % i)
        for i in final_txids:
            file.write("%s\n" % i)
        for i in instance_ids:
            file.write("%s\n" % i)