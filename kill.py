import re
import boto3
import time
import sys
from botocore.exceptions import ClientError

ec2 = boto3.resource('ec2', region_name='us-west-2')

with open('debug.log') as db:
    fstring = db.readlines()

lst = []

for line in fstring:
    if line.startswith('i-'):
        lst.append(line.strip())
        instance = ec2.Instance(line.strip())
        try:
            print(instance.terminate())
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                print("Instance not found")
            else:
                print("Rate limit")
                sleep(100)


fo = open("debug.log", "w+")
fo.truncate()