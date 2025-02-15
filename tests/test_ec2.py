import unittest
from unittest.mock import patch, MagicMock
from src.aws.ec2 import EC2Manager

class TestEC2Manager(unittest.TestCase):
    def setUp(self):
        self.ec2_manager = EC2Manager()
        
    @patch('boto3.client')
    async def test_start_instance_success(self, mock_boto):
        # Setup mock
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.start_instances.return_value = {'StartingInstances': [{'InstanceId': 'i-1234'}]}
        
        # Test
        result = await self.ec2_manager.start_instance('i-1234')
        
        # Assert
        self.assertTrue(result)
        mock_client.start_instances.assert_called_once_with(InstanceIds=['i-1234'])
        
    @patch('boto3.client')
    async def test_start_instance_failure(self, mock_boto):
        # Setup mock
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.start_instances.side_effect = Exception('AWS Error')
        
        # Test
        result = await self.ec2_manager.start_instance('i-1234')
        
        # Assert
        self.assertFalse(result)
        
    @patch('boto3.client')
    async def test_get_instance_state(self, mock_boto):
        # Setup mock
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'State': {'Name': 'running'},
                    'InstanceId': 'i-1234'
                }]
            }]
        }
        
        # Test
        state, instance = await self.ec2_manager.get_instance_state('i-1234')
        
        # Assert
        self.assertEqual(state, 'running')
        self.assertIsNotNone(instance)
        mock_client.describe_instances.assert_called_once_with(InstanceIds=['i-1234'])

if __name__ == '__main__':
    unittest.main()