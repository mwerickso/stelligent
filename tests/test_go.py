import os
import sys
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir) 

import go
from unittest import TestCase, mock, main
from botocore.exceptions import ClientError, EndpointConnectionError


class test_AwsDriver(TestCase):

    @mock.patch('go.boto3')
    def test_get_session(self, mock_boto3):
        mock_boto3.Session().client().get_caller_identity.return_value = {'Account':'012345678901'}

        setobj = go.AwsDriver()

        # Should be able to successfully call get_session
        setobj.get_session()

        # Test with region
        setobj.get_session(region='us-west-1')

    @mock.patch('go.AwsUtil.get_session')
    def test_get_bucket_name(self, mock_get_session):
        client_mock = mock.MagicMock()
        client_mock.get_caller_identity.return_value = {'Account':'012345678901'}
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()
        bucket = setobj.get_bucket_name('test')

        self.assertEqual(bucket, '012345678901-test')

    @mock.patch('go.AwsDriver.get_bucket_name')
    @mock.patch('go.AwsUtil.get_session')
    def test_create_bucket(self, mock_get_session, mock_get_bucket_name):
        mock_get_bucket_name.return_value = '012345678901-test'
        client_mock = mock.MagicMock()
        client_mock.create_bucket.return_value = True
        mock_get_session().client.return_value = client_mock
 
        setobj = go.AwsDriver()
        bucket = setobj.create_bucket('test')

        self.assertEqual(bucket, '012345678901-test')
        client_mock.create_bucket.assert_called_with(Bucket='012345678901-test')

        setobj = go.AwsDriver(region='us-west-1')
        bucket = setobj.create_bucket('test')

        self.assertEqual(bucket, '012345678901-test')
        client_mock.create_bucket.assert_called_with(Bucket='012345678901-test', 
            CreateBucketConfiguration={'LocationConstraint': 'us-west-1'})

    @mock.patch('go.open')
    @mock.patch('go.AwsUtil.get_session')
    def test_upload_files(self, mock_get_session, mock_open):
        open_mock = mock.MagicMock()
        open_mock.read.side_effect = ['test-data', 'testing-data', 'single-test-data']
        mock_open.return_value = open_mock

        client_mock = mock.MagicMock()
        client_mock.put_object.return_value = True
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()

        files = ['test', 'testing']
        setobj.upload_files(files, 'test')

        client_mock.put_object.assert_any_call(Body='test-data', Bucket='test', Key='test', ServerSideEncryption='AES256', StorageClass='STANDARD')
        client_mock.put_object.assert_any_call(Body='testing-data', Bucket='test', Key='testing', ServerSideEncryption='AES256', StorageClass='STANDARD')

        files = 'single-test'
        setobj.upload_files(files, 'test')

        client_mock.put_object.assert_any_call(Body='single-test-data', Bucket='test', Key='single-test', ServerSideEncryption='AES256', StorageClass='STANDARD')

    @mock.patch('go.AwsUtil.get_session')
    def test_delete_files(self, mock_get_session):
        client_mock = mock.MagicMock()
        client_mock.delete_object.return_value = True
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()

        files = ['test', 'testing']
        setobj.delete_files(files, 'test')

        client_mock.delete_object.assert_any_call(Bucket='test', Key='test')
        client_mock.delete_object.assert_any_call(Bucket='test', Key='testing')

        files = 'single-test'
        setobj.delete_files(files, 'test')

        client_mock.delete_object.assert_any_call(Bucket='test', Key='single-test')

    @mock.patch('go.AwsUtil.get_session')
    def test_verify_key_pair(self, mock_get_session):
        client_mock = mock.MagicMock()
        client_mock.describe_key_pairs.side_effect = [{'KeyPairs':['test']}, {'KeyPairs':[]}]
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()
        kp_exists = setobj.verify_key_pair('test')

        client_mock.describe_key_pairs.assert_called_with(Filters=[{'Name': 'key-name', 'Values': ['test']}])
        self.assertTrue(kp_exists)

        kp_exists = setobj.verify_key_pair('test')
        self.assertFalse(kp_exists)

    @mock.patch('go.AwsUtil.get_session')
    def test_create_key_pair(self, mock_get_session):
        client_mock = mock.MagicMock()
        client_mock.create_key_pair.return_value = {'KeyPair':'test', 'KeyMaterial':'0123'}
        client_mock.list_aliases.side_effect = [{'Aliases':[{'AliasName':'alias/test', 'TargetKeyId':'1'}]}, {'Aliases':[]}]
        client_mock.create_key.return_value = {'KeyMetadata':{'KeyId':'1'}}
        client_mock.create_alias.return_value = True
        client_mock.put_parameter.return_value = True
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()
        kp_material = setobj.create_key_pair('test')

        client_mock.create_key_pair.assert_called_with(KeyName='test')
        self.assertEqual(kp_material, '0123')

        kp_material = setobj.create_key_pair('test')
        self.assertTrue(client_mock.create_key.called)
        self.assertTrue(client_mock.create_alias.called)

    @mock.patch('go.Path')
    @mock.patch('go.open')
    @mock.patch('go.AwsUtil.get_session')
    def test_save_key_pair(self, mock_get_session, mock_open, mock_path):
        file_mock = mock.MagicMock()
        file_mock.write.return_value = True
        file_mock.save.return_value = True
        mock_open.return_value = file_mock

        mock_path.home.return_value = '/User/test'
        
        setobj = go.AwsDriver()
        setobj.save_key_pair('test-kp', '0123')

        self.assertTrue(mock_path.home.assert_called)
        self.assertTrue(file_mock.write.assert_called)
        self.assertTrue(file_mock.save.assert_called)

    @mock.patch('go.AwsDriver.save_key_pair')
    @mock.patch('go.AwsDriver.verify_key_pair')
    @mock.patch('go.AwsUtil.get_session')
    def test_download_key_pair(self, mock_get_session, mock_verify_key_pair, 
        mock_save_key_pair):
        client_mock = mock.MagicMock()
        client_mock.get_parameter.return_value = {'Parameter':{'Value':'0123'}}
        mock_get_session().client.return_value = client_mock

        mock_verify_key_pair.side_effect = [True, False]

        setobj = go.AwsDriver()
        setobj.download_key_pair('test')

        self.assertTrue(mock_verify_key_pair.called)
        client_mock.get_parameter.assert_called_with(Name='test-key-pair-us-east-1', WithDecryption=True)
        mock_save_key_pair.called_only_once()

        setobj.download_key_pair('test')
        self.assertTrue(mock_verify_key_pair.called)
        mock_save_key_pair.called_only_once()

    @mock.patch('go.AwsUtil.get_session')
    def test_get_cf_stack(self, mock_get_session):
        stack = {'Outputs':[{'OutputKey':'URL', 'OutputValue':'http://link.com'}], 
                 'Parameters':[{'ParameterKey':'Name','ParameterValue':'test-project'}]}
        client_mock = mock.MagicMock()
        client_mock.describe_stacks.return_value = {'Stacks': [stack]}
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()
        cf_stack = setobj.get_cf_stack('test-project')

        self.assertTrue(client_mock.describe_stacks.called)
        self.assertEqual(cf_stack, stack)

    @mock.patch('go.open')
    @mock.patch('go.json')
    @mock.patch('go.AwsUtil.get_session')
    def test_create_cf_stack(self, mock_get_session, mock_json, mock_open):
        client_mock = mock.MagicMock()
        client_mock.describe_stacks.side_effect = [ClientError({'Error': {'Message': ''}}, 'DescribeStacks'), True]
        client_mock.get_parameter.return_value = {'Parameter':{'Value':'ami-123'}}
        client_mock.validate_template.return_value = True
        client_mock.create_stack.return_value = {'StackId':'789'}
        mock_get_session().client.return_value = client_mock

        mock_json.loads.return_value = {'Resources':{'LaunchConfiguration':{'Properties':{'ImageId':'ami-0'}}}}
        mock_json.dumps.return_value = {'MyTemplate':'Values'}
        mock_open.read.return_value = ''

        setobj = go.AwsDriver()
        stack_id = setobj.create_cf_stack('test-kp', 'test-stack')

        self.assertTrue(mock_json.loads.called)
        client_mock.create_stack.assert_called_with(Capabilities=['CAPABILITY_IAM'], 
            Parameters=[{'ParameterKey': 'KeyPairName', 'ParameterValue': 'test-kp'}], 
            StackName='test-stack', TemplateBody={'MyTemplate': 'Values'})
        self.assertEqual(stack_id, '789')

    @mock.patch('go.AwsUtil.get_session')
    def test_wait_for_stack_completion(self, mock_get_session):
        client_mock = mock.MagicMock()
        client_mock.describe_stacks.side_effect = [{'Stacks':[{'StackStatus':'CREATE_IN_PROGRESS'}]},
            {'Stacks':[{'StackStatus':'CREATE_COMPLETE', 'Outputs':[{'OutputKey': 'URL', 
            'OutputValue': 'http://link.com'}]}]}]
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()
        setobj.wait_for_stack_completion('test-stack')

        self.assertTrue(client_mock.describe_stacks.called)

    @mock.patch('go.AwsUtil.get_session')
    def test_delete_cf_stack(self, mock_get_session):
        client_mock = mock.MagicMock()
        client_mock.delete_stack.return_value = True
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()
        setobj.delete_cf_stack('test-stack')

        self.assertTrue(client_mock.delete_stack.called)

    @mock.patch('go.AwsUtil.get_session')
    def test_wait_for_stack_deletion(self, mock_get_session):
        client_mock = mock.MagicMock()
        client_mock.describe_stacks.side_effect = [{'Stacks':[{'StackStatus':'DELETE_IN_PROGRESS'}]},
            ClientError({'Error': {'Message': 'exist'}}, 'DescribeStacks')]
        mock_get_session().client.return_value = client_mock

        setobj = go.AwsDriver()
        setobj.wait_for_stack_deletion('test-stack')

        self.assertTrue(client_mock.describe_stacks.called)


class test_go_functions(TestCase):
    def setUp(self):
        self.args = mock.MagicMock()
        self.args.id = None
        self.args.secret = None
        self.args.key_pair = 'test-project'
        self.args.region = 'us-east-1'
        self.args.name = 'test'

    @mock.patch('go.test_api')
    @mock.patch('go.AwsDriver')
    def test_build(self, mock_driver, mock_test_api):
        driver_mock = mock.MagicMock()
        driver_mock.create_bucket.return_value = '012345678901-test'
        driver_mock.upload_files.return_value = True
        driver_mock.verify_key_pair.side_effect = [True, False]
        driver_mock.create_key_pair.return_value = True
        driver_mock.save_key_pair.return_value = True
        driver_mock.create_cf_stack.return_value = '0123'
        driver_mock.wait_for_stack_completion.return_value = True
        mock_driver.return_value = driver_mock

        go.build(self.args)

        self.assertTrue(driver_mock.create_bucket.called)
        driver_mock.upload_files.assert_called_with(['app.py', 'requirements.txt'], '012345678901-test')
        driver_mock.verify_key_pair.assert_called_with('test-project')
        driver_mock.create_cf_stack.assert_called_with('test-project', 'test')
        self.assertTrue(driver_mock.wait_for_stack_completion.called)
        self.assertFalse(driver_mock.create_key_pair.called)

        go.build(self.args)
        self.assertTrue(driver_mock.create_key_pair.called)

    @mock.patch('go.AwsDriver')
    def test_destroy(self, mock_driver):
        driver_mock = mock.MagicMock()
        driver_mock.get_bucket_name.return_value = '012345678901-test'
        driver_mock.delete_files.return_value = True
        driver_mock.delete_cf_stack.return_value = True
        driver_mock.wait_for_stack_deletion.return_value = True
        mock_driver.return_value = driver_mock

        go.destroy(self.args)

        self.assertTrue(driver_mock.get_bucket_name.called)
        driver_mock.delete_files.assert_called_with(['app.py', 'requirements.txt'], '012345678901-test')
        driver_mock.delete_cf_stack.assert_called_with('test')
        self.assertTrue(driver_mock.wait_for_stack_deletion.called)

    @mock.patch('go.requests.get')
    def test_test_api(self, mock_requests):
        response = mock.MagicMock()
        response.json.return_value = ({'message':'Automation for the People', 'timestamp': 0000000000.0000})
        mock_requests.return_value = response
        go.test_api('http://link.com')

        self.assertTrue(response.json.called)
        mock_requests.assert_called_with(url='http://link.com')

    @mock.patch('go.pprint')
    @mock.patch('go.AwsDriver')
    def test_info(self, mock_driver, mock_pprint):
        driver_mock = mock.MagicMock()
        driver_mock.get_cf_stack.return_value = {
            'Outputs':[{'OutputKey':'URL', 'OutputValue':'http://link.com'}], 
            'Parameters':[{'ParameterKey':'Name', 'ParameterValue':'test-project'}]}
        mock_driver.return_value = driver_mock

        go.info(self.args)

        self.assertTrue(mock_pprint.called)
        self.assertTrue(driver_mock.get_cf_stack.called)

    @mock.patch('go.AwsDriver')
    def test_test(self, mock_driver):
        driver_mock = mock.MagicMock()
        driver_mock.get_cf_stack.return_value = {'Outputs':[{'OutputKey':'URL', 
                                                             'OutputValue':'http://link.com'}], 
                                                 'Parameters':[{'ParameterKey':'Name',
                                                                'ParameterValue':'test-project'}]}
        mock_driver.return_value = driver_mock

        go.info(self.args)

        self.assertTrue(driver_mock.get_cf_stack.called)

if __name__ == '__main__':
    main()
