import boto3
import json
import argparse
import requests
from botocore import exceptions
from time import sleep
from pathlib import Path
from pprint import pprint

ALLOWED_ACTIONS = ["build", "destroy", "info", "test"]
DEFAULT_REGION = 'us-east-1'
DEFAULT_KEY_PAIR = 'merickson-miniproject'
DEFAULT_NAME = 'merickson-miniproject'
DEFAULT_FILES = ['app.py', 'requirements.txt']


class AwsUtil(object):
    def get_session(self, access_key=None, secret_key=None, region='us-east-1'):
        """
        Get a valid boto3 session to use for base clients.
        
        If access and secret keys are not passed in, will 
        try to use environment variable or config file.

        :param access_key: The AWS Access Key Id
        :type access_key: str

        :param secret_key: The AWS Secret Access Key Id
        :type secret_key: str

        :param region: The AWS region to operate in
        :type region: str

        :return: A session inside the AWS account
        :rtype: boto3.Session
        """
        try:
            # If keys are passed in, use them first
            if access_key and secret_key:
                session = boto3.Session(
                    aws_access_key_id=access_key, 
                    aws_secret_access_key=secret_key,
                    region_name=region)
            # Otherwise, try to use other credentials
            else:
                session = boto3.Session(region_name=region)
            # Test the session to comfirm valid credentials
            account = session.client('sts').get_caller_identity()['Account']
        except exceptions.EndpointConnectionError as e:
            print("Unable to create a session. " \
                "Please check the region and/or credentials passed in.")
            exit(1)
        except exceptions.NoCredentialsError as e:
            print("Unable to locate credentials. " \
                "Please setup credentials file or pass in " \
                "access and secret keys.")
            exit(1)
        except exceptions.ClientError as e:
            if 'invalid' in e.response['Error']['Message']:
                print("Invalid access and/or secret key, please verify and retry")
                exit(1)
        print(f"Established a connection to AWS in account {account}")
        print(f"Operating in region: {region}")
        return session


class AwsDriver(AwsUtil):
    def __init__(self, access_key=None, secret_key=None, region='us-east-1'):
        """
        Initializes the class. Establishes an AWS session
        and the many clients used within the class.

        :param access_key: The AWS Access Key Id
        :type access_key: str

        :param secret_key: The AWS Secret Access Key Id
        :type secret_key: str
        """
        super(AwsDriver, self).__init__()
        self.region = region
        self.session = self.get_session(access_key, secret_key, self.region)
        self.ec2_client = self.session.client('ec2')
        self.s3_client = self.session.client('s3')
        self.kms_client = self.session.client('kms')
        self.ssm_client = self.session.client('ssm')
        self.cf_client = self.session.client('cloudformation')
        self.account_id = self.session.client('sts').get_caller_identity()['Account']

    def get_bucket_name(self, stack_name):
        """
        Helper function that returns the name of the bucket we are expecting.

        :param stack_name: The stack name to be used as part of the bucket name
        :type stack_name: str

        :return: The name of the bucket
        :rtype: str
        """
        bucket_name = f"{self.account_id}-{stack_name}"
        return bucket_name

    def create_bucket(self, stack_name):
        """
        Creates a S3 bucket to upload application files to.
        
        This bucket is used during bootstrap of new application 
        servers.

        :param stack_name: The stack name to be used as part of the bucket name
        :type stack_name: str

        :return: The name of the bucket that was created
        :rtype: str
        """
        # Create a bucket with the account id in the name, to ensure uniqueness
        bucket_name = self.get_bucket_name(stack_name)
        try:
            if self.region == 'us-east-1':
                self.s3_client.create_bucket(Bucket=bucket_name)
            else:
                self.s3_client.create_bucket(Bucket=bucket_name, 
                    CreateBucketConfiguration={'LocationConstraint': self.region})
            print(f"Created bucket {bucket_name}")
        except self.s3_client.exceptions.BucketAlreadyExists:
            print(f"Bucket {bucket_name} already exists, will try to use it")
        except self.s3_client.exceptions.BucketAlreadyOwnedByYou:
            print(f"Bucket {bucket_name} already exists, will try to use it")
        return bucket_name

    def upload_files(self, files, bucket):
        """
        Uploads the files to S3.
        
        These files are used during bootstrap of new application 
        servers.

        :param files: The file(s) to upload to S3
        :type files: str or list

        :param bucket: The name of the bucket to upload files to
        :type bucket: str
        """
        # Ensure files is a list to ensure logic works
        if type(files).__name__ == 'str':
            files = [files,]

        try:
            for f in files:
                body = open(f, 'r').read()
                self.s3_client.put_object(Body=body, Bucket=bucket, Key=f,
                    ServerSideEncryption='AES256', StorageClass='STANDARD')
                print(f"Uploaded file {f} to bucket {bucket}")
        except exceptions.ClientError:
            print("Failed to upload files to the bucket. Ensure the bucket is in this account")
            exit(1)

    def delete_files(self, files, bucket):
        """
        Deletes the files from S3.

        :param files: The file(s) to delete from S3
        :type files: str or list

        :param bucket: The name of the bucket to delete files from
        :type bucket: str
        """
        # Ensure files is a list to ensure logic works
        if type(files).__name__ == 'str':
            files = [files,]

        try:
            for f in files:
                self.s3_client.delete_object(Bucket=bucket, Key=f)
                print(f"Deleted file {f} from bucket {bucket}")
        except exceptions.ClientError:
            print("Failed to delete files from the bucket. Ensure the bucket is in this account")
            exit(1)

    def verify_key_pair(self, kp_name):
        """
        Verifies the key pair passed in exists. If the key pair does 
        not exist, it will create the key pair.

        :param kp_name: The name of the key pair
        :type kp_name: str
        """
        # Check to see if key pair exists
        kp_list = self.ec2_client.describe_key_pairs(Filters=[
            {'Name':'key-name', 'Values':[kp_name]}])['KeyPairs']
        if len(kp_list) == 1:
            print(f"Key pair already exists, please use " \
                f"{kp_name} to connect to app server")
            return True
        else:
            return False

    def create_key_pair(self, kp_name):
        """
        Creates a key pair if the user did not specify one during execution.

        Uploads the key pair to the SSM Param Store in AWS.

        :param kp_name: The name of the key pair
        :type kp_name: str

        :return: The key material
        :rtype: str
        """
        # Create key pair
        try:
            kp = self.ec2_client.create_key_pair(KeyName=kp_name)
            print(f"Created key pair {kp_name}")
        except exceptions.ClientError as e:
            if 'exists' in e.response['Error']['Message']:
                print(f"Key pair {kp_name} already exists")
                return
            else:
                print(f"Failed to create key pair {kp_name}")
                raise(e)

        # Prepare to upload key pair values to SSM Param Store
        kms_name = 'kms-for-ssm'
        kms_key = None

        # See if KMS Key for SSM exists
        kms_list = self.kms_client.list_aliases()['Aliases']
        for key in kms_list:
            if key['AliasName'] == f'alias/{kms_name}':
                kms_key = key['TargetKeyId']
                print("KMS Key for use with SSM Param Store exists")
                continue
        
        # Create KMS Key for SSM if it does not exist
        if kms_key is None:
            policy = '{"Id":"key-consolepolicy-3","Version":"2012-10-17","Statement":[ \
                {"Sid":"Enable IAM User Permissions","Effect":"Allow","Principal": \
                {"AWS":["arn:aws:iam::'+self.account_id+':root"]},"Action":"kms:*", \
                "Resource":"*"}, {"Sid":"Allow access for Key Administrators", \
                "Effect":"Allow","Principal": {"AWS":[ \
                "arn:aws:iam::'+self.account_id+':root"]}, \
                "Action":["kms:Create*","kms:Describe*","kms:Enable*","kms:List*", \
                "kms:Put*","kms:Update*","kms:Revoke*","kms:Disable*","kms:Get*", \
                "kms:Delete*","kms:TagResource","kms:UntagResource", \
                "kms:ScheduleKeyDeletion","kms:CancelKeyDeletion"],"Resource":"*"}, \
                {"Sid":"Allow use of the key","Effect":"Allow","Principal":{"AWS":[ \
                "arn:aws:iam::'+self.account_id+':root"]}, \
                "Action":["kms:Encrypt","kms:Decrypt","kms:ReEncrypt*", \
                "kms:GenerateDataKey*","kms:DescribeKey"],"Resource":"*"}, \
                {"Sid":"Allow attachment of persistent resources","Effect":"Allow", \
                "Principal":{"AWS":["arn:aws:iam::'+self.account_id+':root"]}, \
                "Action":["kms:CreateGrant","kms:ListGrants","kms:RevokeGrant"], \
                "Resource":"*","Condition":{"Bool":{"kms:GrantIsForAWSResource":true}}}]}'

            kms_key = self.kms_client.create_key(Policy=policy,
                Description='Used for SSM services including Param Store.',
                KeyUsage='ENCRYPT_DECRYPT', Origin='AWS_KMS')['KeyMetadata']['KeyId']
            kms_alias = self.kms_client.create_alias(AliasName=f'alias/{kms_name}', 
                TargetKeyId=kms_key)
            print("Created KMS Key for use with SSM Param Store")

        # Store Key Pair data in SSM Param Store
        ssm_name = f'{kp_name}-key-pair'
        ssm_parameter = self.ssm_client.put_parameter(Name=ssm_name, 
            Description=f'Key pair data for {kp_name}', 
            Value=kp['KeyMaterial'], Type='SecureString', 
            KeyId=kms_key, Overwrite=True)
        print(f"Uploaded key pair {kp_name} to SSM Param Store")
        return kp['KeyMaterial']

    def save_key_pair(self, kp_name, kp_material):
        """
        Saves the key pair to the user's home directory.

        :param kp_name: The name of the key pair to download
        :type kp_name: str
        """
        home_dir = str(Path.home())
        file_path = f'{home_dir}/{kp_name}.pem'

        f = open(file_path, 'w')
        f.write(kp_material)
        f.close()
        print(f"Saved key pair to {file_path}")

    def download_key_pair(self, kp_name):
        """
        Downloads the key pair to the user's home dicrectory.

        :param kp_name: The name of the key pair to download
        :type kp_name: str
        """
        kp_exists = self.verify_key_pair(kp_name)
        if kp_exists:
            ssm_name = f'{kp_name}-key-pair-{self.region}'
            ssm_value = self.ssm_client.get_parameter(
                Name=ssm_name, WithDecryption=True)['Parameter']['Value']
            self.save_key_pair(kp_name, ssm_value)
        else:
            print("Error downloading key pair. Could not find key pair.")

    def get_cf_stack(self, stack_name):
        """
        Gets the CF

        :param kp_name: The name of the key pair
        :type kp_name: str

        :param stack_name: The name to use for the CloudFormation stack
        :type stack_name: str

        :return: CloudFormation stack id
        :rtype: str
        """
        try:
            stack = self.cf_client.describe_stacks(StackName=stack_name)
            return stack['Stacks'][0]
        except exceptions.ClientError as e:
            return None

    def create_cf_stack(self, kp_name, stack_name):
        """
        Uploads the AWS CloudFormation template creates the
        application stack in AWS.

        :param kp_name: The name of the key pair
        :type kp_name: str

        :param stack_name: The name to use for the CloudFormation stack
        :type stack_name: str

        :return: CloudFormation stack id
        :rtype: str
        """
        stack = self.get_cf_stack(stack_name)
        if stack:
            self.cf_client.describe_stacks(StackName=stack_name)
            print(f"CloudFormation stack with name {stack_name} already exists, exiting")
            exit(0)
        # Get template and update with correct AMI for region
        template = json.loads(open('app.cf', 'r').read())
        ami_id = self.ssm_client.get_parameter(
            Name='/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2')['Parameter']['Value']
        template['Resources']['LaunchConfiguration']['Properties']['ImageId'] = ami_id
        # Validate template
        try:
            self.cf_client.validate_template(TemplateBody=json.dumps(template))
        except exceptions.ClientError as e:
            print(f"CloudFormation template syntax failed to validate with the following message: \n " \
                f"{e.response['Error']['Message']}")
        # Create stack in AWS
        try:
            stack_id = self.cf_client.create_stack(
                StackName=stack_name, TemplateBody=json.dumps(template),
                Parameters=[{'ParameterKey': 'KeyPairName', 'ParameterValue': kp_name}], 
                Capabilities=['CAPABILITY_IAM'])
        except exceptions.ClientError as e:
            print(f"Cloud Formation Stack creation FAILED: " \
                f"{e.response['Error']['Message']}")
        print(f"Initiated creation of cloudformation stack {stack_name}")
        return stack_id['StackId']

    def wait_for_stack_completion(self, stack_id):
        """
        Waits for the specified stack to either complete or fail.

        :param stack_id: CloudFormation stack id
        :type stack_id: str
        """
        keep_waiting = True
        while keep_waiting:
            for i in range(30):
                cf_stack = self.cf_client.describe_stacks(StackName=stack_id)['Stacks'][0]
                if cf_stack['StackStatus'] == 'CREATE_IN_PROGRESS':
                    print("Waiting for stack to complete")
                    sleep(15)
                elif cf_stack['StackStatus'] == 'CREATE_COMPLETE':
                    print("CloudFormation stack completed")
                    for output in cf_stack['Outputs']:
                        if output['OutputKey'] == 'URL':
                            url = output['OutputValue']
                    print(f"Message API URL: \n{url}")
                    keep_waiting = False
                    return url
                else:
                    print(f"CloudFormation stack had the following code: " \
                        f"{cf_stack['StackStatus']}")
                    exit(1)
            else:
                print(f"Creation of the CloudFormation stack is taking too long, exiting.")
                exit(0)

    def delete_cf_stack(self, stack_name):
        """
        Deletes the CloudFormation stack.

        :param stack_name: The name of the CloudFormation stack
        :type stack_name: str
        """
        try:
            self.cf_client.delete_stack(StackName=stack_name)
        except exceptions.ClientError as e:
            print(f"Cloud Formation Stack deletion FAILED: " \
                f"{e.response['Error']['Message']}")
        print(f"Initated deletion of cloudformation stack {stack_name}")

    def wait_for_stack_deletion(self, stack_name):
        """
        Waits for the specified stack to either complete or fail.

        :param stack_name: CloudFormation stack name
        :type stack_name: str
        """
        keep_waiting = True
        while keep_waiting:
            for i in range(30):
                try:
                    cf_stack = self.cf_client.describe_stacks(StackName=stack_name)['Stacks'][0]
                except exceptions.ClientError as e:
                    if 'exist' in e.response['Error']['Message']:
                        print("CloudFormation stack deleted")
                        keep_waiting = False
                        break
                if cf_stack['StackStatus'] == 'DELETE_IN_PROGRESS':
                    print("Waiting for stack to delete")
                    sleep(15)
                elif cf_stack['StackStatus'] == 'DELETE_COMPLETE':
                    print("CloudFormation stack deleted")
                    keep_waiting = False
                    break
                else:
                    print(f"CloudFormation stack had the following code: " \
                          f"{cf_stack['StackStatus']}")
                    exit(1)
            else:
                print(f"Creation of the CloudFormation stack is taking too long, exiting.")
                exit(0)

def test_api(url):
    """
    Get request against api url.

    :param url: URL of the API
    :type url: str
    """
    response = requests.get(url=url).json()
    print(f"Response for the API Request against url ({url}):")
    pprint(response, indent=2)
    return response

def setup(access_key, secret_key, kp_name, region, stack_name):
    # Initialize the AwsSetup class
    setobj = AwsDriver(access_key=access_key, secret_key=secret_key, region=region)

    # Create the bucket and upload the app files
    bucket = setobj.create_bucket(stack_name)
    files = ['app.py', 'requirements.txt']
    setobj.upload_files(files, bucket)

    # Validate key pair and create if needed
    kp_exists = setobj.verify_key_pair(kp_name)
    if kp_exists is False:
            kp_material = setobj.create_key_pair(kp_name)

    # Create CloudFormation stack
    stack_id = setobj.create_cf_stack(kp_name, stack_name)
    setobj.wait_for_stack_completion(stack_id)

def build(args):
    # Initialize the AwsSetup class
    setobj = AwsDriver(access_key=args.id, secret_key=args.secret, region=args.region)

    # Create the bucket and upload the app files
    bucket = setobj.create_bucket(args.name)
    setobj.upload_files(DEFAULT_FILES, bucket)

    # Validate key pair and create if needed
    kp_exists = setobj.verify_key_pair(args.key_pair)
    if kp_exists is False:
            kp_material = setobj.create_key_pair(args.key_pair)

    # Create CloudFormation stack
    stack_id = setobj.create_cf_stack(args.key_pair, args.name)
    url = setobj.wait_for_stack_completion(stack_id)
    for i in range(30):
        try:
            response = test_api(url)
            return
        except:
            print("Waiting for servers to spin up..")
            sleep(10)

def destroy(args):
    # Initialize the AwsSetup class
    setobj = AwsDriver(access_key=args.id, secret_key=args.secret, region=args.region)

    # The bucket will not be deleted - if setup and teardown are run repeatedly, it would 
    # start throwing errors since AWS S3 name space is unique and deletion of buckets takes
    # time to propogate. 

    # The files inside the bucket will be deleted
    bucket = setobj.get_bucket_name(args.name)
    setobj.delete_files(DEFAULT_FILES, bucket)

    # The key pair will not be deleted - this is debatable and something easy to change.
    # The KMS and SSM parameters will also not be delted at this time.

    # Delete the CloudFormation stack
    setobj.delete_cf_stack(args.name)
    setobj.wait_for_stack_deletion(args.name)

def info(args):
    setobj = AwsDriver(access_key=args.id, secret_key=args.secret, region=args.region)
    cf_stack = setobj.get_cf_stack(args.name)
    if cf_stack:
        pprint(cf_stack['Parameters'], indent=2)
        pprint(cf_stack['Outputs'], indent=2)
    else:
        print("Could not find the CloudFormation stack. Exiting.")
        exit(1)

def test(args):
    setobj = AwsDriver(access_key=args.id, secret_key=args.secret, region=args.region)
    cf_stack = setobj.get_cf_stack(args.name)
    if cf_stack:
        for output in cf_stack['Outputs']:
            if output['OutputKey'] == 'URL':
                url = output['OutputValue']
        response = test_api(url)
    else:
        print("Could not find the CloudFormation stack. Exiting.")
        exit(1)

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("action", choices=ALLOWED_ACTIONS, 
                        help="Action to take against the stack(s)")
    parser.add_argument('-i', '--id', required=False, help='AWS Access Key ID')
    parser.add_argument('-s', '--secret', required=False, help='AWS Secret Access Key')
    parser.add_argument('-k', '--key_pair', default=DEFAULT_KEY_PAIR, 
                        help='Name of AWS Key Pair to use for EC2 Instance to allow SSH login')
    parser.add_argument('-r', '--region', default=DEFAULT_REGION, help='AWS Region ID')
    parser.add_argument('-n', '--name', default=DEFAULT_NAME,
                        help='The name to use for the CloudFormation stack')

    args = parser.parse_args()
    # Strips spaces from the name passed in, since AWS name space does not allow spaces
    (args.name).replace(" ", "")
    (args.key_pair).replace(" ", "")

    if args.action == 'build':
        build(args)
    elif args.action == 'destroy':
        destroy(args)
    elif args.action == 'info':
        info(args)
    elif args.action == 'test':
        test(args)

if __name__ == '__main__':
    main()
