import re
import boto3

ec2 = boto3.resource('ec2', region_name='us-west-2')

with open('debug.log') as db:
    fstring = db.readlines()

lst = []

for line in fstring:
    if line.startswith('i-'):
        lst.append(line.strip())
        instance = ec2.Instance(line.strip())
        print(instance.terminate())

fo = open("debug.log", "w+")
fo.truncate()