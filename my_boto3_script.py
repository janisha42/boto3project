import boto3
import json 

# Define boto3 clients
ec2_client = boto3.client('ec2')
s3_client = boto3.client('s3')
sns_client = boto3.client('sns')
lambda_client = boto3.client('lambda') 

def lambda_health_check_handler(event, context):
    try:
        # Define ARNs for the target group and SNS topic
        target_group_arn = 'arn:aws:elasticloadbalancing:eu-west-2:515210271098:targetgroup/boto3project/c2d3a6b3e267e2c4'
        sns_topic_arn = 'arn:aws:sns:eu-west-2:515210271098:boto3project.fifo'
        
        # Retrieve instance health status
        health_response = ec2_client.describe_instance_status()
        # Filter unhealthy instances (e.g., those in a 'stopped' state)
        unhealthy_instances = [instance for instance in health_response['InstanceStatuses'] if instance['InstanceState']['Name'] == 'stopped']
        
        # Process each unhealthy instance
        for instance in unhealthy_instances:
            instance_id = instance['InstanceId']
            # Create a snapshot for debugging purposes
            create_snapshot_response = ec2_client.create_snapshot(
                Description=f'Snapshot for debugging instance {instance_id}',
                InstanceId=instance_id,
            )
            # Terminate the unhealthy instance
            terminate_response = ec2_client.terminate_instances(InstanceIds=[instance_id])
            # Publish a notification about the terminated instance
            sns_message = {
                'InstanceID': instance_id,
                'Action': 'Terminated',
                'Reason': 'Health check failure',
                'SnapshotDetails': create_snapshot_response
            }
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Message=json.dumps({'default': json.dumps(sns_message)}),
                Subject='Web Application Instance Failure Notification',
                MessageStructure='json'
            )
            print(f"Instance {instance_id} terminated and snapshot initiated for debugging. Notification sent.")
    except Exception as e:
        print(f"Error in lambda_health_check_handler: {str(e)}")

def create_bucket(bucket_name, region='us-west-2'):
    try:
        if region is None:
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            location = {'LocationConstraint': region}
            s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration=location)
        print(f"Bucket {bucket_name} created.")
    except Exception as e:
        print(f"Error in create_bucket: {str(e)}")

bucket_name = 'janishab320'
create_bucket(bucket_name)

# Specify your VPC, subnet, and key pair
vpc_id = 'vpc-008f9ed7fb0bb4c5e'
subnet_id = 'subnet-08a785f20857330e7'
key_pair_name = 'JANX'

# Common user data script for installing Nginx and cloning repository
common_user_data_script = """#!/bin/bash
sudo apt update
sudo apt install nginx -y
systemctl start nginx
systemctl enable nginx
"""

# Additional backend setup, including Node.js installation and environment setup
backend_user_data_script = common_user_data_script + """
git clone https://github.com/UnpredictablePrashant/TravelMemory.git /var/www/html/TravelMemory
curl -sL https://deb.nodesource.com/setup_current.x | sudo -E bash -
sudo apt-get install -y nodejs
cd /var/www/html/TravelMemory/backend
echo "MONGO_URI=mongodb+srv://testdb:hi@travelmemorydb.b3sfizx.mongodb.net/" > .env
echo "PORT=3000" >> .env
npm install
nohup npm start &
"""

# Frontend setup, including Node.js installation
frontend_user_data_script = common_user_data_script + """
git clone https://github.com/UnpredictablePrashant/TravelMemory.git /var/www/html/TravelMemory
curl -sL https://deb.nodesource.com/setup_current.x | sudo -E bash -
sudo apt-get install -y nodejs
cd /var/www/html/TravelMemory/frontend
npm install
nohup npm start &
"""

# Security group configuration
security_group_response = ec2_client.create_security_group(
    GroupName='newsecuritygroup',  
    Description='Security group for MERN application',
    VpcId=vpc_id
)

# Extract the security group ID from the response
security_group_id = security_group_response['GroupId']

# Authorize inbound traffic for HTTP, SSH, and custom TCP port 3000
ec2_client.authorize_security_group_ingress(
    GroupId=security_group_id,
    IpPermissions=[
        {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
        {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
        {'IpProtocol': 'tcp', 'FromPort': 3000, 'ToPort': 3000, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
    ]
)

# Launch EC2 instances for frontend and backend
def launch_ec2_instance(name_tag, user_data):
    # Use the defined security_group_id variable here
    instance = ec2_client.run_instances(
        ImageId='ami-0e5f882be1900e43b',
        InstanceType='t2.micro',
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[security_group_id],  # Use the security group ID here
        KeyName=key_pair_name,
        UserData=user_data,
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [{'Key': 'Name', 'Value': name_tag}],
        }],
        SubnetId=subnet_id
    )
    return instance['Instances'][0]['InstanceId']

# Now you can call the launch_ec2_instance function
frontend_instance_id = launch_ec2_instance('MERN-Frontend', frontend_user_data_script)
backend_instance_id = launch_ec2_instance('MERN-Backend', backend_user_data_script)
print("Bucket janishab320 created.")
print("Frontend and backend instances launched successfully.")
