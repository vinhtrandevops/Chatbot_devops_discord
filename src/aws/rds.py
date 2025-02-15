"""
AWS RDS management module.
Provides functionality to manage RDS instances including:
- Start/Stop instances
- Get instance status
- Get instance metrics
"""

import boto3
import os
import datetime
import json
from ..utils.logger import get_logger
from ..config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION
)

logger = get_logger(__name__)

class RDSInstanceTypeInfo:
    """Handles RDS instance type information retrieval and caching."""
    
    def __init__(self, region=AWS_REGION):
        """
        Initialize RDS instance type info manager.
        
        Args:
            region (str): AWS region name. Defaults to AWS_REGION from config.
        """
        # Pricing API only available in us-east-1
        self.pricing_client = boto3.client('pricing', region_name='us-east-1')
        self.region = region
        self._instance_memory_cache = {}
        self._cache_expiry = None
        self._cache_duration = datetime.timedelta(days=1)

    def _is_cache_valid(self):
        """
        Check if the memory cache is still valid.
        
        Returns:
            bool: True if cache is valid, False otherwise.
        """
        return (self._cache_expiry is not None and 
                datetime.datetime.now() < self._cache_expiry and 
                self._instance_memory_cache)

    async def get_instance_memory(self, instance_class):
        """
        Get memory (in GB) for an RDS instance class.
        Uses AWS Pricing API with local caching.
        
        Args:
            instance_class (str): RDS instance class (e.g., 'db.t4g.micro')
            
        Returns:
            float: Memory in GB, or None if information cannot be retrieved
        """
        try:
            # Check cache first
            if self._is_cache_valid() and instance_class in self._instance_memory_cache:
                return self._instance_memory_cache[instance_class]

            # If cache invalid or instance not in cache, query AWS Pricing API
            response = self.pricing_client.get_products(
                ServiceCode='AmazonRDS',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_class},
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'Asia Pacific (Singapore)'}
                ]
            )

            for price in response['PriceList']:
                attributes = json.loads(price)['product']['attributes']
                if 'memory' in attributes:
                    # Memory comes in format like "2 GiB"
                    memory_str = attributes['memory']
                    memory_gb = float(memory_str.split()[0])
                    self._instance_memory_cache[instance_class] = memory_gb
                    self._cache_expiry = datetime.datetime.now() + self._cache_duration
                    return memory_gb

            # Fallback to common instance types if API fails
            fallback_memory = {
                'db.t4g.micro': 1,
                'db.t4g.small': 2,
                'db.t4g.medium': 4,
                'db.t4g.large': 8,
                'db.t4g.xlarge': 16,
                'db.t4g.2xlarge': 32
            }
            
            if instance_class in fallback_memory:
                self._instance_memory_cache[instance_class] = fallback_memory[instance_class]
                return fallback_memory[instance_class]

            logger.warning(f"Could not find memory info for instance class: {instance_class}")
            return None

        except Exception as e:
            logger.error(f"Error getting instance memory info: {str(e)}")
            return None

class RDSManager:
    """Manages AWS RDS instances operations."""
    
    def __init__(self):
        """Initialize RDS manager with AWS credentials or IAM role"""
        try:
            # First try to create client without credentials (will use IAM role if available)
            logger.info("Attempting to initialize AWS clients using IAM role...")
            self.rds_client = boto3.client('rds', region_name=AWS_REGION)
            self.cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)
            
            # Test the connection by making a simple API call
            self.rds_client.describe_db_instances(MaxRecords=5)
            logger.info("Successfully initialized AWS clients using IAM role")
            
        except Exception as e:
            logger.info(f"IAM role not available or insufficient permissions: {str(e)}")
            logger.info("Falling back to access key authentication")
            
            if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
                raise Exception("No IAM role available and AWS credentials not configured")
                
            # Fall back to using access keys
            self.rds_client = boto3.client('rds',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            self.cloudwatch = boto3.client('cloudwatch',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            logger.info("Successfully initialized AWS clients using access keys")
        self.instance_info = RDSInstanceTypeInfo()

    async def _is_read_replica(self, db_instance_id: str) -> bool:
        """
        Check if an RDS instance is a read replica.
        
        Args:
            db_instance_id (str): RDS instance identifier
            
        Returns:
            bool: True if instance is a read replica, False otherwise
        """
        try:
            response = self.rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_id)
            instance = response['DBInstances'][0]
            return 'ReadReplicaSourceDBInstanceIdentifier' in instance
        except Exception as e:
            logger.error(f"Error checking if instance is read replica: {str(e)}")
            return False

    async def start_instance(self, db_instance_id: str):
        """
        Start an RDS instance.
        
        Args:
            db_instance_id (str): RDS instance identifier
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Check if instance is a read replica
            if await self._is_read_replica(db_instance_id):
                return False, f"Không thể start/stop read replica instance. Vui lòng thao tác trên primary instance."

            response = self.rds_client.start_db_instance(DBInstanceIdentifier=db_instance_id)
            logger.info(f"Starting RDS instance: {db_instance_id}")
            return True, f"Đang khởi động RDS instance: {db_instance_id}"
        except Exception as e:
            logger.error(f"Error starting RDS instance: {str(e)}")
            return False, f"Lỗi khi khởi động RDS instance: {str(e)}"

    async def stop_instance(self, db_instance_id: str):
        """
        Stop an RDS instance.
        
        Args:
            db_instance_id (str): RDS instance identifier
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Check if instance is a read replica
            if await self._is_read_replica(db_instance_id):
                return False, f"Không thể start/stop read replica instance. Vui lòng thao tác trên primary instance."

            response = self.rds_client.stop_db_instance(DBInstanceIdentifier=db_instance_id)
            logger.info(f"Stopping RDS instance: {db_instance_id}")
            return True, f"Đang tắt RDS instance: {db_instance_id}"
        except Exception as e:
            logger.error(f"Error stopping RDS instance: {str(e)}")
            return False, f"Lỗi khi tắt RDS instance: {str(e)}"

    async def get_instance_status(self, db_instance_id: str):
        """
        Get status of an RDS instance.
        
        Args:
            db_instance_id (str): RDS instance identifier
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            response = self.rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_id)
            status = response['DBInstances'][0]['DBInstanceStatus']
            logger.info(f"RDS instance {db_instance_id} status: {status}")
            return True, f"Trạng thái của RDS instance {db_instance_id}: {status}"
        except Exception as e:
            logger.error(f"Error getting RDS instance status: {str(e)}")
            return False, f"Lỗi khi lấy trạng thái RDS instance: {str(e)}"

    async def list_all_instances(self):
        """
        List all RDS instances and their statuses.
        
        Returns:
            tuple: (success: bool, instances: list)
        """
        try:
            logger.info("Getting list of RDS instances...")
            response = self.rds_client.describe_db_instances()
            instances = []
            
            logger.info(f"Found {len(response['DBInstances'])} instances")
            for instance in response['DBInstances']:
                instance_id = instance['DBInstanceIdentifier']
                logger.info(f"Processing instance: {instance_id}")
                instance_info = {
                    'identifier': instance_id,
                    'status': instance['DBInstanceStatus'],
                    'engine': instance['Engine'],
                    'size': instance['DBInstanceClass'],
                    'storage': f"{instance['AllocatedStorage']} GB",
                    'endpoint': instance.get('Endpoint', {}).get('Address', 'N/A')
                }
                instances.append(instance_info)
                logger.info(f"Instance info: {instance_info}")
            
            return True, instances
        except Exception as e:
            logger.error(f"Error listing RDS instances: {str(e)}")
            return False, f"Lỗi khi lấy danh sách RDS: {str(e)}"

    async def get_instance_metrics(self, db_instance_id: str):
        """
        Get metrics for an RDS instance.
        Includes: CPU, Memory, Storage, IOPS, and Connections.
        
        Args:
            db_instance_id (str): RDS instance identifier
            
        Returns:
            tuple: (success: bool, metrics: dict)
        """
        try:
            end_time = datetime.datetime.utcnow()
            start_time = end_time - datetime.timedelta(hours=1)

            # Get instance info and memory
            rds_info = self.rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_id)
            instance_class = rds_info['DBInstances'][0]['DBInstanceClass']
            total_memory_gb = await self.instance_info.get_instance_memory(instance_class)
            total_memory = (total_memory_gb or 0) * 1024 * 1024 * 1024  # Convert GB to bytes

            # Define metrics to collect
            metrics = {
                'CPU': {
                    'MetricName': 'CPUUtilization',
                    'Unit': 'Percent'
                },
                'Memory': {
                    'MetricName': 'FreeableMemory',
                    'Unit': 'Bytes'
                },
                'Storage': {
                    'MetricName': 'FreeStorageSpace',
                    'Unit': 'Bytes'
                },
                'IOPS': {
                    'MetricName': 'ReadIOPS',
                    'Unit': 'Count/Second'
                },
                'Connections': {
                    'MetricName': 'DatabaseConnections',
                    'Unit': 'Count'
                }
            }

            # Collect and format metrics
            results = {}
            for metric_name, metric_info in metrics.items():
                response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/RDS',
                    MetricName=metric_info['MetricName'],
                    Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,  # 5 minutes
                    Statistics=['Average']
                )

                if response['Datapoints']:
                    latest = max(response['Datapoints'], key=lambda x: x['Timestamp'])
                    value = latest['Average']
                    
                    # Format based on metric type
                    if metric_info['Unit'] == 'Bytes':
                        if metric_name == 'Memory':
                            free_memory = value
                            used_memory = total_memory - free_memory if total_memory > 0 else 0
                            memory_usage_percent = (used_memory / total_memory * 100) if total_memory > 0 else 0
                            free_memory_gb = free_memory / (1024 * 1024 * 1024)
                            results[metric_name] = f"{free_memory_gb:.1f}/{total_memory_gb:.1f} GB ({memory_usage_percent:.1f}% used)"
                        else:
                            results[metric_name] = f"{value / (1024 * 1024 * 1024):.2f} GB"
                    elif metric_info['Unit'] == 'Percent':
                        results[metric_name] = f"{value:.1f}%"
                    elif metric_info['Unit'] == 'Count/Second':
                        results[metric_name] = f"{value:.1f}/s"
                    else:
                        results[metric_name] = f"{value:.1f}"
                else:
                    results[metric_name] = 'N/A'

            return True, results
        except Exception as e:
            logger.error(f"Error getting RDS metrics: {str(e)}")
            return False, f"Lỗi khi lấy metrics: {str(e)}"