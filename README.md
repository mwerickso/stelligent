# Stelligent

## About
This project is to showcase knowledge in a programming language (Python), 
in Amazon Web Services and development techniques. Deploying this 
application will expose an API endpoint that can be queried to retrieve 
an ultra secret message and the current timestamp.

## Prerequisites
* In order to run the script to build or destroy the application, python3.6 
(or newer version) and boto3 must be installed.
* In order to successfully deploy the infrastructure to Amazon Web Services, 
an AWS Account with an IAM User that has programmatic access (Access Key ID 
and Secret Access Key ID) must be made available through the AWS credentials 
or config files, environment variables or passed into the scripts during run 
time.
* The IAM User must have sufficient access to create, update and delete the 
following types of AWS Resources: 
    * IAM Roles
    * Security Groups
    * VPC, Subnet, Internet Gateway, NAT Gateway, Route Tables
    * Application Load Balancers and Target Groups
    * Launch Configurations and Auto Scaling Groups

## Installation
Python3.6 and pip must be installed.

To install boto3, run the following:
```
sudo pip install boto3 botocore
```

**The AWS Access Key ID and AWS Secret Access Key ID _MUST_ be passed to the script unless it is stored in `~/.aws/credentials` or `~/.aws/config` files, or have it set as an environment variable. If the script cannot find valid credentials, it will notify and exit.**

Clone the repository, or ensure that you have the `app.cf`, `app.py`, `go.py`, 
and `requirements.txt` downloaded to the same folder. To run the script:
```
cd /path/to/directory
python3 go.py build
```

### Arguments
The following are arguments that the script will accept:
| Argument | Default | Description |
|---|---|---|
| -i | null | The AWS Access Key ID |
| -s | null | The AWS Secret Access Key ID |
| -k | merickson-miniproject | The AWS EC2 Key Pair name. If it does not exist, script will create it |
| -r | us-east-1 | The AWS Region |
| -n | merickson-miniproject | The CloudFormation stack name |

Actions:
* build
* info
* test
* destroy

### Examples
```
python3 setup.py build -n 'test-project' -k 'testing'
python3 setup.py build -i 'AKIAIOSFODNN7EXAMPLE' -s 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' -r 'us-west-1'
```

### Output
The `go.py` script will display the on-going progress of the build or destroy actions. Upon the completiong
of the stack, the Message API URL and response will be displayed.

The VPC ID and Message API URL will also be displayed in the CloudFormation Stack's output tab.

### AWS Infrastructure
The setup script will create a new CloudFormation Stack based on the `app.cf` file. This stack will do the following:
* Create a VPC
* Create and attach an internet gateway
* Create 2 public and 2 private subnets
* Create 2 NAT Gateways, one in each private subnet
* Create a public and 2 private route tables
* Add appropriate routes to use gateways
* Security groups with appropriate rules
* Application load balancer in public subnet
* Target group 
* Launch configuration
* Auto scaling group in private subnets

## Usage
Once the application has been deployed, the user can go to the application load balancer's dns name 
to view the message. The user can also curl, request or any other method of *get* to the URL to receive 
the message.

At the completion of the `build` action, the API URL will be displayed to the user, in addition to the 
response of the request of the URL. 

Alternatively, the location of the application load balancer's dns name can be found by:  
1. Going to the AWS Console 
1. Selecting the EC2 service
1. Selecting the Load Balancers link
1. Selecting the appropriate load balancer 
1. Viewing the Description tab 
1. Retrieve the DNS name

Additionally, the user can get the parameters and outputs of the CloudFormation stack can be seen by 
using the scripts `info` action:
```
cd /path/to/directory
python3 go.py info
```

Lastly, the user can test the API URL and receive the response by using the `test` action of the 
script:
```
cd /path/to/directory
python3 go.py test
```

## Uninstallation
To remove the application infrastructure from AWS, run the following command:
```
cd /path/to/directory
python3 go.py destroy
```

This `destroy` action of the script will remove the CloudFormation stack and 
delete the application files from the bucket. 
It **will not** delete the following: 
* Key Pair (even if the setup script created it)
* The SSM Parameter used to store the Key Pair Material
* The KMS Key used to encrypt the SSM Parameter
* The bucket created to store the application files.

### Arguments
The same arguments apply to the script's `destroy` action with the exception of the `-k` argument. 
Since the Key Pair is not deleted, the argument is not applicable. 

### Examples
```
python3 go.py destroy -n 'test-project' -k 'testing'
python3 go.py destroy -i 'AKIAIOSFODNN7EXAMPLE' -s 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' -r 'us-west-1'
```

## Testing
Unit testing has been written for each function within in each python file. 

In order to run the `test_app.py` script, you must first install the application dependencies list in the 
`requirements.txt` file. You can run the following command to install them:
```
cd /path/to/dir
pip install -r requirements.txt
```

Then the tests can be run using the following commands:
```
cd /path/to/dir
python3 test_app.py
python3 test_go.py
```
These tests do not actually deploy anything, but instead test the logic of each function, mocking outside resources.
