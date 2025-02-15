import boto3
import json
from botocore.exceptions import ClientError
from ..config import (
    AWS_ACCESS_KEY_ID, 
    AWS_SECRET_ACCESS_KEY, 
    AWS_REGION,
    EKS_CLUSTER_NAME
)
from ..utils.logger import get_logger
import time
import asyncio
from datetime import datetime, timezone
import yaml
from kubernetes import client, config
import os

logger = get_logger(__name__)

class EKSManager:
    def __init__(self):
        try:
            # Initialize AWS clients
            self.eks_client = boto3.client(
                'eks',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            self.sts_client = boto3.client(
                'sts',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            self.cluster_name = EKS_CLUSTER_NAME
            
            # Test connection and permissions
            try:
                response = self.eks_client.describe_cluster(name=self.cluster_name)
                self.cluster_info = response['cluster']
                
                # Get existing nodegroup for configuration reference
                nodegroups = self.eks_client.list_nodegroups(clusterName=self.cluster_name)['nodegroups']
                if nodegroups:
                    ng_info = self.eks_client.describe_nodegroup(
                        clusterName=self.cluster_name,
                        nodegroupName=nodegroups[0]
                    )['nodegroup']
                    
                    # Use configuration from existing nodegroup
                    self.node_role_arn = ng_info['nodeRole']
                    self.subnets = ng_info['subnets']
                else:
                    raise Exception("No existing nodegroups found to get configuration from")
                    
            except ClientError as e:
                logger.error(f"Error accessing EKS cluster: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Error initializing EKSManager: {str(e)}")
            raise

    async def list_nodegroups(self):
        """List all nodegroups in the cluster with their tags"""
        try:
            logger.info(f"Attempting to list nodegroups for cluster: {self.cluster_name}")
            
            # First, verify cluster access
            try:
                self.eks_client.describe_cluster(name=self.cluster_name)
                logger.info("Successfully verified cluster access")
            except ClientError as e:
                logger.error(f"Error accessing cluster: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error accessing cluster: {str(e)}"

            # List nodegroups
            try:
                response = self.eks_client.list_nodegroups(clusterName=self.cluster_name)
                logger.info(f"Successfully retrieved nodegroups list")
                logger.info(f"Found nodegroups: {response['nodegroups']}")
            except ClientError as e:
                logger.error(f"Error listing nodegroups: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error listing nodegroups: {str(e)}"

            nodegroups = []
            for ng_name in response['nodegroups']:
                try:
                    logger.info(f"Getting details for nodegroup: {ng_name}")
                    ng_info = self.eks_client.describe_nodegroup(
                        clusterName=self.cluster_name,
                        nodegroupName=ng_name
                    )['nodegroup']
                    
                    # Get tags
                    try:
                        tags = self.eks_client.list_tags_for_resource(
                            resourceArn=ng_info['nodegroupArn']
                        )['tags']
                        logger.info(f"Retrieved tags for nodegroup {ng_name}")
                    except ClientError as e:
                        logger.warning(f"Error getting tags for nodegroup {ng_name}: {str(e)}")
                        tags = {}
                    
                    nodegroups.append({
                        'name': ng_name,
                        'status': ng_info['status'],
                        'size': ng_info['scalingConfig']['desiredSize'],
                        'min_size': ng_info['scalingConfig']['minSize'],
                        'max_size': ng_info['scalingConfig']['maxSize'],
                        'tags': tags
                    })
                    logger.info(f"Successfully processed nodegroup: {ng_name}")
                except ClientError as e:
                    logger.error(f"Error getting details for nodegroup {ng_name}: {str(e)}")
                    continue
            
            return True, nodegroups
        except Exception as e:
            logger.error(f"Unexpected error in list_nodegroups: {str(e)}")
            return False, str(e)

    async def add_nodegroup_tags(self, nodegroup_name, tags):
        """
        Add tags to a nodegroup
        
        Args:
            nodegroup_name (str): Name of the nodegroup
            tags (dict): Dictionary of tag key-value pairs
        """
        try:
            logger.info(f"Attempting to add tags to nodegroup {nodegroup_name} in cluster {self.cluster_name}")
            
            # Get nodegroup ARN
            try:
                ng_info = self.eks_client.describe_nodegroup(
                    clusterName=self.cluster_name,
                    nodegroupName=nodegroup_name
                )['nodegroup']
                logger.info(f"Successfully retrieved nodegroup {nodegroup_name} details")
            except ClientError as e:
                logger.error(f"Error getting nodegroup {nodegroup_name} details: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error getting nodegroup {nodegroup_name} details: {str(e)}"
            
            # Add tags
            try:
                self.eks_client.tag_resource(
                    resourceArn=ng_info['nodegroupArn'],
                    tags=tags
                )
                logger.info(f"Successfully added tags to nodegroup {nodegroup_name}")
            except ClientError as e:
                logger.error(f"Error adding tags to nodegroup {nodegroup_name}: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error adding tags to nodegroup {nodegroup_name}: {str(e)}"
            
            return True, f"Successfully added tags to nodegroup {nodegroup_name}"
        except Exception as e:
            logger.error(f"Unexpected error in add_nodegroup_tags: {str(e)}")
            return False, str(e)

    async def remove_nodegroup_tags(self, nodegroup_name, tag_keys):
        """
        Remove tags from a nodegroup
        
        Args:
            nodegroup_name (str): Name of the nodegroup
            tag_keys (list): List of tag keys to remove
        """
        try:
            logger.info(f"Attempting to remove tags from nodegroup {nodegroup_name} in cluster {self.cluster_name}")
            
            # Get nodegroup ARN
            try:
                ng_info = self.eks_client.describe_nodegroup(
                    clusterName=self.cluster_name,
                    nodegroupName=nodegroup_name
                )['nodegroup']
                logger.info(f"Successfully retrieved nodegroup {nodegroup_name} details")
            except ClientError as e:
                logger.error(f"Error getting nodegroup {nodegroup_name} details: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error getting nodegroup {nodegroup_name} details: {str(e)}"
            
            # Remove tags
            try:
                self.eks_client.untag_resource(
                    resourceArn=ng_info['nodegroupArn'],
                    tagKeys=tag_keys
                )
                logger.info(f"Successfully removed tags from nodegroup {nodegroup_name}")
            except ClientError as e:
                logger.error(f"Error removing tags from nodegroup {nodegroup_name}: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error removing tags from nodegroup {nodegroup_name}: {str(e)}"
            
            return True, f"Successfully removed tags from nodegroup {nodegroup_name}"
        except Exception as e:
            logger.error(f"Unexpected error in remove_nodegroup_tags: {str(e)}")
            return False, str(e)

    async def scale_nodegroup(self, nodegroup_name, desired_size):
        """
        Scale a nodegroup to desired size
        
        Args:
            nodegroup_name (str): Name of the nodegroup
            desired_size (int): Desired number of nodes
        """
        try:
            logger.info(f"Attempting to scale nodegroup {nodegroup_name} to {desired_size} nodes in cluster {self.cluster_name}")
            
            # Get current nodegroup info
            try:
                nodegroup = self.eks_client.describe_nodegroup(
                    clusterName=self.cluster_name,
                    nodegroupName=nodegroup_name
                )['nodegroup']
                logger.info(f"Successfully retrieved nodegroup {nodegroup_name} details")
            except ClientError as e:
                logger.error(f"Error getting nodegroup {nodegroup_name} details: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error getting nodegroup {nodegroup_name} details: {str(e)}"
            
            current_size = nodegroup['scalingConfig']['desiredSize']
            min_size = nodegroup['scalingConfig']['minSize']
            max_size = nodegroup['scalingConfig']['maxSize']

            # Validate desired size
            if desired_size < min_size or desired_size > max_size:
                return False, f"Desired size {desired_size} is outside allowed range ({min_size}-{max_size})"

            # Update nodegroup
            try:
                self.eks_client.update_nodegroup_config(
                    clusterName=self.cluster_name,
                    nodegroupName=nodegroup_name,
                    scalingConfig={
                        'desiredSize': desired_size
                    }
                )
                logger.info(f"Successfully scaled nodegroup {nodegroup_name} to {desired_size} nodes")
            except ClientError as e:
                logger.error(f"Error scaling nodegroup {nodegroup_name}: {str(e)}")
                logger.error(f"Error code: {e.response['Error']['Code']}")
                logger.error(f"Error message: {e.response['Error']['Message']}")
                return False, f"Error scaling nodegroup {nodegroup_name}: {str(e)}"
            
            return True, {
                'message': f"Scaling nodegroup {nodegroup_name} from {current_size} to {desired_size} nodes",
                'previous_size': current_size,
                'new_size': desired_size,
                'min_size': min_size,
                'max_size': max_size
            }
        except Exception as e:
            logger.error(f"Unexpected error in scale_nodegroup: {str(e)}")
            return False, str(e)

    async def get_nodegroup_status(self, nodegroup_name):
        """Get the current status of a nodegroup"""
        try:
            logger.info(f"[STATUS] Checking nodegroup '{nodegroup_name}'...")
            start_time = datetime.now()
            
            try:
                logger.info(f"[STATUS] Calling describe_nodegroup API...")
                response = self.eks_client.describe_nodegroup(
                    clusterName=self.cluster_name,
                    nodegroupName=nodegroup_name
                )
                end_time = datetime.now()
                elapsed = (end_time - start_time).total_seconds()
                logger.info(f"[STATUS] API call completed in {elapsed:.1f}s")
                
                nodegroup = response['nodegroup']
                status = nodegroup.get('status')
                
                # Log detailed status information
                logger.info(f"[STATUS] Current state: {status}")
                if 'statusMessage' in nodegroup:
                    logger.info(f"[STATUS] Status message: {nodegroup['statusMessage']}")
                    
                # Log health information
                health = nodegroup.get('health', {})
                logger.info(f"[STATUS] Health details:")
                logger.info(f"[STATUS] - Issues: {json.dumps(health.get('issues', []), default=str)}")
                
                # Log scaling information
                scaling = nodegroup.get('scalingConfig', {})
                logger.info(f"[STATUS] Scaling details:")
                logger.info(f"[STATUS] - Desired: {scaling.get('desiredSize')}")
                logger.info(f"[STATUS] - Min: {scaling.get('minSize')}")
                logger.info(f"[STATUS] - Max: {scaling.get('maxSize')}")
                
                # Log resources information
                resources = nodegroup.get('resources', {})
                logger.info(f"[STATUS] Resources:")
                logger.info(f"[STATUS] - AutoScaling groups: {json.dumps(resources.get('autoScalingGroups', []), default=str)}")
                logger.info(f"[STATUS] - Remote access config: {json.dumps(resources.get('remoteAccessConfig', {}), default=str)}")
                
                return status
                
            except self.eks_client.exceptions.ResourceNotFoundException:
                logger.info(f"[STATUS] Nodegroup '{nodegroup_name}' not found")
                return None
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_msg = e.response['Error']['Message']
                request_id = e.response['ResponseMetadata'].get('RequestId', 'N/A')
                logger.error(f"[STATUS] AWS error during status check:")
                logger.error(f"[STATUS] Error Code: {error_code}")
                logger.error(f"[STATUS] Error Message: {error_msg}")
                logger.error(f"[STATUS] Request ID: {request_id}")
                logger.error(f"[STATUS] Full error response: {json.dumps(e.response, default=str)}")
                raise
                
        except Exception as e:
            logger.error(f"[STATUS] Unexpected error during status check: {str(e)}")
            logger.error(f"[STATUS] Error type: {type(e).__name__}")
            logger.error(f"[STATUS] Stack trace:", exc_info=True)
            raise

    async def list_scalable_nodegroups(self):
        """List nodegroups that can be scaled with their current sizes and limits"""
        try:
            logger.info(f"Listing scalable nodegroups in cluster {self.cluster_name}")
            
            # Get all nodegroups
            try:
                response = self.eks_client.list_nodegroups(clusterName=self.cluster_name)
                logger.info(f"Found nodegroups: {response['nodegroups']}")
            except ClientError as e:
                logger.error(f"Error listing nodegroups: {str(e)}")
                return False, f"Error listing nodegroups: {str(e)}"

            scalable_groups = []
            for ng_name in response['nodegroups']:
                try:
                    ng_info = self.eks_client.describe_nodegroup(
                        clusterName=self.cluster_name,
                        nodegroupName=ng_name
                    )['nodegroup']
                    
                    # Get scaling configuration
                    scaling = {
                        'name': ng_name,
                        'current_size': ng_info['scalingConfig']['desiredSize'],
                        'min_size': ng_info['scalingConfig']['minSize'],
                        'max_size': ng_info['scalingConfig']['maxSize'],
                        'instance_types': ng_info.get('instanceTypes', ['unknown']),
                        'status': ng_info['status']
                    }
                    
                    scalable_groups.append(scaling)
                    logger.info(f"Added scaling info for nodegroup {ng_name}")
                except ClientError as e:
                    logger.error(f"Error getting nodegroup {ng_name} details: {str(e)}")
                    continue
            
            return True, scalable_groups
        except Exception as e:
            logger.error(f"Unexpected error in list_scalable_nodegroups: {str(e)}")
            return False, str(e)

    async def create_nodegroup(self, nodegroup_name, instance_type, desired_size, min_size, max_size, tags=None, capacity_type='ON_DEMAND'):
        """
        Create a new nodegroup with specified configuration
        
        Args:
            nodegroup_name (str): Name of the nodegroup
            instance_type (str): EC2 instance type
            desired_size (int): Desired number of nodes
            min_size (int): Minimum number of nodes
            max_size (int): Maximum number of nodes
            tags (dict): Optional tags to apply
            capacity_type (str): Either 'ON_DEMAND' or 'SPOT'
        """
        try:
            # Log initial request details
            logger.info(f"Creating nodegroup with following parameters:")
            logger.info(f"Cluster: {self.cluster_name}")
            logger.info(f"Nodegroup name: {nodegroup_name}")
            logger.info(f"Instance type: {instance_type}")
            logger.info(f"Capacity type: {capacity_type}")
            logger.info(f"Sizes - Desired: {desired_size}, Min: {min_size}, Max: {max_size}")
            
            # Log IAM role info
            logger.info(f"Using IAM role ARN: {self.node_role_arn}")
            
            # Log subnets being used
            logger.info(f"Using subnets: {self.subnets}")
            
            # Validate capacity type
            if capacity_type not in ['ON_DEMAND', 'SPOT']:
                return False, "Capacity type must be either 'ON_DEMAND' or 'SPOT'"
            
            config = {
                'clusterName': self.cluster_name,
                'nodegroupName': nodegroup_name,
                'scalingConfig': {
                    'minSize': min_size,
                    'maxSize': max_size,
                    'desiredSize': desired_size
                },
                'subnets': self.subnets,
                'instanceTypes': [instance_type],
                'nodeRole': self.node_role_arn,
                'capacityType': capacity_type
            }
            
            if tags:
                config['tags'] = tags
                
            # Log the full configuration being sent
            logger.info(f"Full nodegroup configuration: {json.dumps(config, indent=2)}")
            
            try:
                # Attempt to create nodegroup
                logger.info("Calling EKS CreateNodegroup API...")
                response = self.eks_client.create_nodegroup(**config)
                logger.info(f"Successfully initiated nodegroup creation: {response}")
                
                # Wait for creation to complete
                success, message = await self.wait_for_nodegroup_status(nodegroup_name, 'ACTIVE')
                if success:
                    return True, f"Successfully created nodegroup {nodegroup_name}"
                else:
                    return False, f"Error waiting for creation: {message}"
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_msg = e.response['Error']['Message']
                request_id = e.response.get('ResponseMetadata', {}).get('RequestId', 'N/A')
                
                logger.error(f"AWS API Error Details:")
                logger.error(f"Error Code: {error_code}")
                logger.error(f"Error Message: {error_msg}")
                logger.error(f"Request ID: {request_id}")
                logger.error(f"Full error response: {json.dumps(e.response, default=str)}")
                
                if error_code == 'AccessDeniedException':
                    logger.error("IAM Permission Issue Detected:")
                    logger.error(f"Action: eks:CreateNodegroup")
                    account_id = self.get_account_id()
                    if account_id:
                        logger.error(f"Resource: arn:aws:eks:{AWS_REGION}:{account_id}:cluster/{self.cluster_name}")
                    else:
                        logger.error(f"Resource: arn:aws:eks:{AWS_REGION}:*:cluster/{self.cluster_name}")
                    logger.error("Required IAM permissions:")
                    logger.error("- eks:CreateNodegroup")
                    logger.error("- iam:PassRole (for the node role)")
                    logger.error("Please check your IAM user/role permissions")
                
                return False, f"Error creating nodegroup: {str(e)}"
                
        except Exception as e:
            logger.error(f"Unexpected error in create_nodegroup: {str(e)}")
            return False, f"Unexpected error: {str(e)}"

    async def create_performance_nodegroup(self, nodegroup_name, config=None, status_callback=None):
        """Create a performance nodegroup"""
        try:
            # Check if nodegroup already exists
            status = await self.get_nodegroup_status(nodegroup_name)
            if status is not None:
                msg = f"❌ Nodegroup '{nodegroup_name}' đã tồn tại (status: {status})"
                logger.warning(msg)
                return False, msg

            logger.info(f"Creating performance nodegroup: {nodegroup_name}")
            
            # Set default configuration
            default_config = {
                'ami_type': 'AL2023_x86_64_STANDARD',  # Latest Amazon Linux 2023
                'instance_types': ['c7i.xlarge'],      # Latest compute-optimized instance
                'min_size': 1,
                'max_size': 1,
                'desired_size': 1,
                'capacity_type': 'ON_DEMAND',
                'disk_size': 50,
                'labels': {
                    'component': 'performance-test'
                },
                'taints': [{
                    'key': 'component',
                    'value': 'performance-test',
                    'effect': 'NO_SCHEDULE'
                }]
            }

            # Update default config with any provided overrides
            if config:
                default_config.update(config)
        
            config = default_config

            # Get cost estimates
            success, cost_data = await self.estimate_nodegroup_cost(
                config['instance_types'][0],
                config['desired_size'],
                config['capacity_type']
            )
        
            if not success:
                return False, self.format_bot_message(False, cost_data)
        
            # Add creation time and channel to tags
            if 'tags' not in config:
                config['tags'] = {}
            config['tags'].update({
                'created_at': datetime.now(timezone.utc).isoformat(),
                'created_in_channel': str(config.get('channel_id', ''))
            })

            # Prepare EKS nodegroup configuration
            eks_config = {
                'clusterName': self.cluster_name,
                'nodegroupName': nodegroup_name,
                'scalingConfig': {
                    'minSize': config['min_size'],
                    'maxSize': config['max_size'],
                    'desiredSize': config['desired_size']
                },
                'subnets': self.subnets,
                'instanceTypes': config['instance_types'],
                'nodeRole': self.node_role_arn,
                'capacityType': config['capacity_type'],
                'amiType': config['ami_type'],
                'diskSize': config['disk_size'],
                'labels': config['labels'],
                'tags': config['tags']
            }

            # Add taints if specified
            if config['taints']:
                eks_config['taints'] = config['taints']

            # Create the nodegroup
            try:
                logger.info(f"Creating nodegroup with config: {json.dumps(eks_config, default=str)}")
                response = self.eks_client.create_nodegroup(**eks_config)
                logger.info(f"Create nodegroup response: {json.dumps(response, default=str)}")
            
                if status_callback:
                    await status_callback("CREATING")
            
                # Wait for nodegroup to become active with status updates
                waiter = self.eks_client.get_waiter('nodegroup_active')
                last_status = None
            
                try:
                    start_time = time.time()
                    max_wait_time = 20 * 60  # 20 minutes timeout
                
                    while True:
                        if time.time() - start_time > max_wait_time:
                            raise Exception("Timeout waiting for nodegroup to become active")
                    
                        try:
                            current_status = await self.get_nodegroup_status(nodegroup_name)
                            if current_status != last_status:
                                logger.info(f"Nodegroup status changed: {current_status}")
                                if status_callback:
                                    await status_callback(current_status)
                                last_status = current_status
                            
                            if current_status == "ACTIVE":
                                break
                            elif current_status in ["CREATE_FAILED", "DELETE_FAILED", "DEGRADED"]:
                                raise Exception(f"Nodegroup entered failed state: {current_status}")
                            
                        except ClientError as e:
                            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                                raise Exception("Nodegroup was unexpectedly deleted")
                            raise e
                        
                        await asyncio.sleep(30)
                    
                except Exception as e:
                    logger.error(f"Error waiting for nodegroup: {str(e)}")
                    if "timeout" in str(e).lower():
                        return False, f"⏳ Quá trình tạo nodegroup '{nodegroup_name}' đang mất nhiều thời gian hơn dự kiến. Vui lòng kiểm tra trạng thái sau."
                    return False, f"❌ Lỗi khi tạo nodegroup: {str(e)}"
            
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_msg = e.response['Error']['Message']
                logger.error(f"AWS ClientError in create_nodegroup:")
                logger.error(f"Error Code: {error_code}")
                logger.error(f"Error Message: {error_msg}")
            
                if error_code == 'ResourceInUseException':
                    return False, f"❌ Không thể tạo nodegroup '{nodegroup_name}' vì tên đã được sử dụng"
                elif error_code == 'ResourceLimitExceeded':
                    return False, f"❌ Đã vượt quá giới hạn tài nguyên khi tạo nodegroup"
                elif error_code == 'InvalidParameterException':
                    return False, f"❌ Tham số không hợp lệ khi tạo nodegroup: {error_msg}"
                else:
                    raise e
        
        except Exception as e:
            logger.error(f"Unexpected error in create_performance_nodegroup: {str(e)}")
            return False, f"❌ Lỗi không mong muốn: {str(e)}"

    async def delete_performance_nodegroup(self, nodegroup_name):
        """Delete a performance nodegroup"""
        try:
            logger.info(f"[DELETE] ====== Starting deletion process ======")
            logger.info(f"[DELETE] Nodegroup: {nodegroup_name}")
            logger.info(f"[DELETE] Cluster: {self.cluster_name}")
            logger.info(f"[DELETE] Region: {self.eks_client.meta.region_name}")
            logger.info(f"[DELETE] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Get current nodegroup status
            try:
                logger.info(f"[DELETE] Step 1: Checking current nodegroup status...")
                current_status = await self.get_nodegroup_status(nodegroup_name)
                
                if current_status is None:
                    logger.warning(f"[DELETE] Nodegroup not found: {nodegroup_name}")
                    return False, f"❌ Không tìm thấy nodegroup '{nodegroup_name}'"
                    
                logger.info(f"[DELETE] Current status: {current_status}")
                
                # Get detailed nodegroup info for debugging
                try:
                    logger.info(f"[DELETE] Getting detailed nodegroup info...")
                    nodegroup_info = self.eks_client.describe_nodegroup(
                        clusterName=self.cluster_name,
                        nodegroupName=nodegroup_name
                    )['nodegroup']
                    logger.info(f"[DELETE] Nodegroup details:")
                    logger.info(f"[DELETE] - ARN: {nodegroup_info.get('nodegroupArn')}")
                    logger.info(f"[DELETE] - Instance Types: {nodegroup_info.get('instanceTypes', [])}")
                    logger.info(f"[DELETE] - Scaling Config: {json.dumps(nodegroup_info.get('scalingConfig', {}), default=str)}")
                    logger.info(f"[DELETE] - Health: {json.dumps(nodegroup_info.get('health', {}), default=str)}")
                    logger.info(f"[DELETE] - Resources: {json.dumps(nodegroup_info.get('resources', {}), default=str)}")
                    logger.info(f"[DELETE] - Labels: {json.dumps(nodegroup_info.get('labels', {}), default=str)}")
                    logger.info(f"[DELETE] - Tags: {json.dumps(nodegroup_info.get('tags', {}), default=str)}")
                    logger.info(f"[DELETE] - Launch Template: {json.dumps(nodegroup_info.get('launchTemplate', {}), default=str)}")
                    logger.info(f"[DELETE] - Status: {nodegroup_info.get('status')}")
                    if 'statusMessage' in nodegroup_info:
                        logger.info(f"[DELETE] - Status Message: {nodegroup_info.get('statusMessage')}")
                    logger.info(f"[DELETE] - Created At: {nodegroup_info.get('createdAt')}")
                    logger.info(f"[DELETE] - Modified At: {nodegroup_info.get('modifiedAt')}")
                except Exception as e:
                    logger.warning(f"[DELETE] Could not get detailed nodegroup info: {str(e)}")
                    logger.warning(f"[DELETE] Error type: {type(e).__name__}")
                    logger.warning(f"[DELETE] Stack trace:", exc_info=True)
                
                # Check if already deleting
                if current_status == "DELETING":
                    logger.info(f"[DELETE] Nodegroup is already in DELETING state")
                    return True, f"⏳ Nodegroup '{nodegroup_name}' đang trong quá trình xóa"
                
                # Check for invalid states
                invalid_states = ["CREATE_FAILED", "DELETE_FAILED", "DEGRADED"]
                if current_status in invalid_states:
                    logger.error(f"[DELETE] Cannot delete nodegroup in state: {current_status}")
                    return False, f"❌ Không thể xóa nodegroup '{nodegroup_name}' do đang trong trạng thái {current_status}"
                
                # Step 2: Scale down the nodegroup first
                logger.info(f"[DELETE] Step 2: Scaling down nodegroup...")
                try:
                    scaling_config = nodegroup_info.get('scalingConfig', {})
                    current_size = scaling_config.get('desiredSize', 0)
                    logger.info(f"[DELETE] Current scaling config:")
                    logger.info(f"[DELETE] - Desired Size: {scaling_config.get('desiredSize')}")
                    logger.info(f"[DELETE] - Min Size: {scaling_config.get('minSize')}")
                    logger.info(f"[DELETE] - Max Size: {scaling_config.get('maxSize')}")
                    
                    if current_size > 0:
                        logger.info(f"[DELETE] Scaling down from {current_size} to 0")
                        update_response = self.eks_client.update_nodegroup_config(
                            clusterName=self.cluster_name,
                            nodegroupName=nodegroup_name,
                            scalingConfig={
                                'minSize': 0,
                                'maxSize': scaling_config.get('maxSize', 1),
                                'desiredSize': 0
                            }
                        )
                        logger.info(f"[DELETE] Scale down response: {json.dumps(update_response, default=str)}")
                        
                        # Wait for scale down
                        logger.info(f"[DELETE] Waiting 30 seconds for scale down...")
                        await asyncio.sleep(30)
                        
                        # Verify scale down
                        verify_info = self.eks_client.describe_nodegroup(
                            clusterName=self.cluster_name,
                            nodegroupName=nodegroup_name
                        )['nodegroup']
                        new_size = verify_info.get('scalingConfig', {}).get('desiredSize', -1)
                        logger.info(f"[DELETE] New desired size after scale down: {new_size}")
                    else:
                        logger.info(f"[DELETE] No scale down needed, current size is already 0")
                        
                except Exception as e:
                    logger.warning(f"[DELETE] Error during scale down: {str(e)}")
                    logger.warning(f"[DELETE] Error type: {type(e).__name__}")
                    logger.warning(f"[DELETE] Stack trace:", exc_info=True)
                
                # Step 3: Delete nodegroup
                logger.info(f"[DELETE] Step 3: Sending delete request...")
                logger.info(f"[DELETE] Time before delete request: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                response = self.eks_client.delete_nodegroup(
                    clusterName=self.cluster_name,
                    nodegroupName=nodegroup_name
                )
                
                # Log response details
                logger.info(f"[DELETE] Delete request sent successfully")
                logger.info(f"[DELETE] Time after delete request: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"[DELETE] Response metadata: {json.dumps(response.get('ResponseMetadata', {}), default=str)}")
                logger.info(f"[DELETE] HTTP Status Code: {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
                logger.info(f"[DELETE] Request ID: {response.get('ResponseMetadata', {}).get('RequestId')}")
                logger.info(f"[DELETE] Full response: {json.dumps(response, default=str)}")
                
                # Step 4: Monitor deletion progress
                logger.info(f"[DELETE] Step 4: Monitoring deletion progress...")
                max_retries = 30  # 5 minutes total (10 second intervals)
                start_time = datetime.now()
                for i in range(max_retries):
                    current_time = datetime.now()
                    elapsed = (current_time - start_time).total_seconds()
                    logger.info(f"[DELETE] Check {i+1}/{max_retries} (Elapsed: {elapsed:.1f}s)")
                    
                    verify_status = await self.get_nodegroup_status(nodegroup_name)
                    logger.info(f"[DELETE] Status = {verify_status}")
                    
                    try:
                        verify_info = self.eks_client.describe_nodegroup(
                            clusterName=self.cluster_name,
                            nodegroupName=nodegroup_name
                        )['nodegroup']
                        
                        # Log more details about the nodegroup state
                        logger.info(f"[DELETE] Detailed status at check {i+1}:")
                        
                        # Resources state
                        resources = verify_info.get('resources', {})
                        asg_groups = resources.get('autoScalingGroups', [])
                        logger.info(f"[DELETE] - ASG Groups: {len(asg_groups)} groups")
                        for asg in asg_groups:
                            logger.info(f"[DELETE]   - Name: {asg.get('name')}")
                        
                        # Instance details
                        logger.info(f"[DELETE] - Instance Types: {verify_info.get('instanceTypes', [])}")
                        
                        # Scaling details
                        scaling = verify_info.get('scalingConfig', {})
                        logger.info(f"[DELETE] - Current Scaling:")
                        logger.info(f"[DELETE]   - Desired: {scaling.get('desiredSize')}")
                        logger.info(f"[DELETE]   - Min: {scaling.get('minSize')}")
                        logger.info(f"[DELETE]   - Max: {scaling.get('maxSize')}")
                        
                        # Health details
                        health = verify_info.get('health', {})
                        issues = health.get('issues', [])
                        if issues:
                            logger.info(f"[DELETE] - Health Issues Found: {len(issues)} issues")
                            for issue in issues:
                                logger.info(f"[DELETE]   - Code: {issue.get('code')}")
                                logger.info(f"[DELETE]   - Message: {issue.get('message')}")
                                logger.info(f"[DELETE]   - Resource IDs: {issue.get('resourceIds', [])}")
                        else:
                            logger.info(f"[DELETE] - No health issues reported")
                        
                        # Status message if any
                        if 'statusMessage' in verify_info:
                            logger.info(f"[DELETE] - Status Message: {verify_info['statusMessage']}")
                            
                        # Update info
                        if 'updateConfig' in verify_info:
                            logger.info(f"[DELETE] - Update Config: {json.dumps(verify_info['updateConfig'], default=str)}")
                            
                        # Taints if any
                        if 'taints' in verify_info:
                            logger.info(f"[DELETE] - Taints: {json.dumps(verify_info['taints'], default=str)}")
                    except ClientError as e:
                        if e.response['Error']['Code'] == 'ResourceNotFoundException':
                            logger.info(f"[DELETE] Nodegroup no longer exists")
                        else:
                            logger.warning(f"[DELETE] Error getting status details: {str(e)}")
                            logger.warning(f"[DELETE] Error type: {type(e).__name__}")
                            logger.warning(f"[DELETE] Full error: {json.dumps(e.response, default=str)}")
                    
                    if verify_status is None:
                        logger.info(f"[DELETE] Nodegroup successfully deleted")
                        logger.info(f"[DELETE] Total time: {elapsed:.1f}s")
                        return True, f"✅ Đã xóa nodegroup '{nodegroup_name}' thành công"
                        
                    if verify_status == "DELETE_FAILED":
                        logger.error(f"[DELETE] Deletion failed")
                        logger.error(f"[DELETE] Total time: {elapsed:.1f}s")
                        return False, f"❌ Xóa nodegroup '{nodegroup_name}' thất bại"
                        
                    if verify_status != "DELETING":
                        logger.error(f"[DELETE] Unexpected status during deletion: {verify_status}")
                        logger.error(f"[DELETE] Total time: {elapsed:.1f}s")
                        return False, f"❌ Trạng thái không mong muốn: {verify_status}"
                        
                    await asyncio.sleep(10)
                
                logger.error(f"[DELETE] Deletion monitoring timed out after {elapsed:.1f}s")
                return False, f"❌ Quá thời gian chờ xóa nodegroup '{nodegroup_name}'"
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_msg = e.response['Error']['Message']
                request_id = e.response['ResponseMetadata'].get('RequestId', 'N/A')
                logger.error(f"[DELETE] AWS error during deletion:")
                logger.error(f"[DELETE] Error Code: {error_code}")
                logger.error(f"[DELETE] Error Message: {error_msg}")
                logger.error(f"[DELETE] Request ID: {request_id}")
                logger.error(f"[DELETE] Full error response: {json.dumps(e.response, default=str)}")
                
                if error_code == 'ResourceInUseException':
                    logger.error(f"[DELETE] Resources still using the nodegroup")
                    return False, f"❌ Không thể xóa nodegroup '{nodegroup_name}' vì đang có resources đang sử dụng"
                elif error_code == 'ResourceNotFoundException':
                    logger.error(f"[DELETE] Nodegroup not found")
                    return False, f"❌ Không tìm thấy nodegroup '{nodegroup_name}'"
                else:
                    logger.error(f"[DELETE] Unexpected AWS error")
                    return False, f"❌ Lỗi khi xóa nodegroup: {error_msg}"
                    
        except Exception as e:
            logger.error(f"[DELETE] Unexpected error: {str(e)}")
            logger.error(f"[DELETE] Error type: {type(e).__name__}")
            logger.error(f"[DELETE] Stack trace:", exc_info=True)
            return False, f"❌ Lỗi không mong muốn: {str(e)}"

    async def estimate_nodegroup_cost(self, instance_type, desired_size, capacity_type='ON_DEMAND'):
        """
        Estimate monthly cost for a nodegroup using AWS Pricing API
        """
        try:
            # Initialize pricing client (only available in us-east-1)
            pricing = boto3.client('pricing', region_name='us-east-1')
            
            # Map AWS regions to pricing API location names
            region_map = {
                'ap-southeast-1': 'Asia Pacific (Singapore)',
                'us-east-1': 'US East (N. Virginia)',
                'us-west-2': 'US West (Oregon)',
                'ap-northeast-1': 'Asia Pacific (Tokyo)',
                'eu-west-1': 'EU (Ireland)',
                'eu-central-1': 'EU (Frankfurt)'
            }
            
            location = region_map.get(AWS_REGION, 'Asia Pacific (Singapore)')
            logger.info(f"Getting pricing for {instance_type} in {location}")
            
            # Query AWS Pricing API
            filters = [
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'}
            ]
            
            response = pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=filters,
                MaxResults=1
            )
            
            if not response.get('PriceList'):
                error_msg = f"No pricing found for {instance_type} in {location}"
                logger.error(error_msg)
                return False, error_msg
            
            # Parse pricing data
            try:
                price_data = json.loads(response['PriceList'][0])
                on_demand_terms = price_data.get('terms', {}).get('OnDemand', {})
                
                if not on_demand_terms:
                    error_msg = f"No OnDemand pricing terms found for {instance_type}"
                    logger.error(error_msg)
                    return False, error_msg
                
                # Get the first price dimension
                first_offer = list(on_demand_terms.values())[0]
                first_dimension = list(first_offer['priceDimensions'].values())[0]
                on_demand_price = float(first_dimension['pricePerUnit']['USD'])
                
                if on_demand_price <= 0:
                    error_msg = f"Invalid price (${on_demand_price}) found for {instance_type}"
                    logger.error(error_msg)
                    return False, error_msg
                
                logger.info(f"Found OnDemand price: ${on_demand_price}/hour")
                
                # Calculate hourly price based on capacity type
                if capacity_type == 'SPOT':
                    hourly_price = on_demand_price * 0.3  # Estimate 70% discount for SPOT
                    logger.info(f"Calculated SPOT price (70% discount): ${hourly_price}/hour")
                else:
                    hourly_price = on_demand_price
                
                # Calculate monthly cost (30.44 days average per month)
                monthly_cost = hourly_price * 24 * 30.44 * desired_size
                
                logger.info(f"Cost calculation results for {instance_type}:")
                logger.info(f"• Hourly per node: ${hourly_price:.3f}")
                logger.info(f"• Monthly total: ${monthly_cost:.2f}")
                logger.info(f"• Capacity type: {capacity_type}")
                logger.info(f"• Number of nodes: {desired_size}")
                
                return True, {
                    'hourly_per_node': round(hourly_price, 3),
                    'monthly_total': round(monthly_cost, 2),
                    'instance_type': instance_type,
                    'capacity_type': capacity_type
                }
                
            except (KeyError, IndexError, ValueError) as e:
                error_msg = f"Error parsing pricing data for {instance_type}: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
            
        except Exception as e:
            error_msg = f"Error getting pricing from AWS: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def compare_nodegroup_costs(self, instance_type, desired_size):
        """Compare costs between ON_DEMAND and SPOT for a nodegroup configuration"""
        try:
            # Get costs for both types
            on_demand_success, on_demand_cost = await self.estimate_nodegroup_cost(instance_type, desired_size, 'ON_DEMAND')
            if not on_demand_success:
                return False, on_demand_cost  # Return the error message
                
            spot_success, spot_cost = await self.estimate_nodegroup_cost(instance_type, desired_size, 'SPOT')
            if not spot_success:
                return False, spot_cost  # Return the error message
                
            savings = on_demand_cost['monthly_total'] - spot_cost['monthly_total']
            savings_percentage = (savings / on_demand_cost['monthly_total']) * 100 if on_demand_cost['monthly_total'] > 0 else 0
            
            comparison = {
                'instance_type': instance_type,
                'nodes': desired_size,
                'on_demand': {
                    'hourly_per_node': on_demand_cost['hourly_per_node'],
                    'monthly_total': on_demand_cost['monthly_total']
                },
                'spot': {
                    'hourly_per_node': spot_cost['hourly_per_node'],
                    'monthly_total': spot_cost['monthly_total']
                },
                'savings': {
                    'monthly': savings,
                    'percentage': savings_percentage
                }
            }
            
            return True, self.format_bot_message(True, comparison)
            
        except Exception as e:
            logger.error(f"Error comparing costs: {str(e)}", exc_info=True)
            return False, self.format_bot_message(False, str(e))

    def format_bot_message(self, success, data, nodegroup_name=None):
        """Format message for bot response"""
        if not success:
            return f"❌ Error: {data}"

        # For cost comparison only
        if nodegroup_name is None:
            return (
                f"💰 Cost Analysis:\n"
                f"• ON_DEMAND: ${data['on_demand']['monthly_total']:.2f}/month\n"
                f"• SPOT: ${data['spot']['monthly_total']:.2f}/month\n"
                f"• Save ${data['savings']['monthly']:.2f}/month with SPOT"
            )

        # For nodegroup creation
        cluster_name = self.cluster_name
        config = data['configuration']
        cost = data['cost_comparison']
        
        message = [
            f"✅ Creation Success",
            f"🔷 Cluster: {cluster_name}",
            f"📦 Nodegroup: {nodegroup_name}",
            f"� Capacity Type: {config['capacity_type']}",
            f"� Cost: ${cost['selected_cost']:.2f}/month"
        ]
        
        if config['capacity_type'] == 'ON_DEMAND':
            savings = cost['on_demand_monthly'] - cost['spot_monthly']
            message.append(f"💡 Tip: Save ${savings:.2f}/month with SPOT")
            
        return "\n".join(message)

    async def create_performance_test_pod(self):
        """Create a performance test pod"""
        try:
            logger.info("[Pod Creation] Starting performance test pod creation")
            
            # Get cluster info for API server
            logger.info("[Pod Creation] Getting cluster info")
            cluster = self.eks_client.describe_cluster(name=self.cluster_name)
            cluster_url = cluster['cluster']['endpoint']
            cluster_ca = cluster['cluster']['certificateAuthority']['data']
            logger.info(f"[Pod Creation] Cluster URL: {cluster_url}")
            
            # Get token
            logger.info("[Pod Creation] Getting caller identity")
            token_res = self.sts_client.get_caller_identity()
            cluster_arn = cluster['cluster']['arn']
            parts = cluster_arn.split(':')
            region = parts[3]
            account = parts[4]
            logger.info(f"[Pod Creation] Account: {account}, Region: {region}")
            logger.info(f"[Pod Creation] Caller Identity: {json.dumps(token_res, indent=2)}")
            
            # Configure client
            logger.info("[Pod Creation] Configuring Kubernetes client")
            configuration = client.Configuration()
            configuration.host = cluster_url
            configuration.verify_ssl = True
            
            # Write CA cert
            logger.info("[Pod Creation] Writing CA certificate")
            ca_file = self._write_ca_cert(cluster_ca)
            configuration.ssl_ca_cert = ca_file
            logger.info(f"[Pod Creation] CA cert written to: {ca_file}")
            
            # Get bearer token
            logger.info("[Pod Creation] Getting bearer token")
            bearer_token = self._get_bearer_token()
            configuration.api_key = {"authorization": f"Bearer {bearer_token}"}
            logger.info("[Pod Creation] Bearer token configured")
            
            # Create API client
            logger.info("[Pod Creation] Creating API client")
            api_client = client.ApiClient(configuration)
            v1 = client.CoreV1Api(api_client)
            
            # Create pod manifest
            logger.info("[Pod Creation] Creating pod manifest")
            pod_manifest = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": "performance-test"
                },
                "spec": {
                    "affinity": {
                        "nodeAffinity": {
                            "requiredDuringSchedulingIgnoredDuringExecution": {
                                "nodeSelectorTerms": [{
                                    "matchExpressions": [{
                                        "key": "component",
                                        "operator": "In",
                                        "values": ["performance-test"]
                                    }]
                                }]
                            }
                        }
                    },
                    "tolerations": [{
                        "key": "component",
                        "operator": "Equal",
                        "value": "performance-test",
                        "effect": "NoSchedule"
                    }],
                    "containers": [{
                        "name": "performance-test",
                        "image": "python:3",
                        "command": ["sleep", "infinity"]
                    }]
                }
            }
            logger.info(f"[Pod Creation] Pod manifest: {json.dumps(pod_manifest, indent=2)}")
            
            # Create pod
            logger.info("[Pod Creation] Creating pod in default namespace")
            try:
                response = v1.create_namespaced_pod(
                    body=pod_manifest,
                    namespace="default"
                )
                logger.info(f"[Pod Creation] Pod creation response: {response}")
            except Exception as e:
                logger.error(f"[Pod Creation] Pod creation failed: {str(e)}")
                if hasattr(e, 'body'):
                    logger.error(f"[Pod Creation] Error body: {e.body}")
                if hasattr(e, 'status'):
                    logger.error(f"[Pod Creation] Error status: {e.status}")
                if hasattr(e, 'reason'):
                    logger.error(f"[Pod Creation] Error reason: {e.reason}")
                raise e
            
            logger.info("[Pod Creation] Successfully created performance test pod")
            return True, "Performance test pod created successfully"
            
        except Exception as e:
            error_msg = f"Error creating performance test pod: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def _get_bearer_token(self):
        """Get bearer token for EKS authentication"""
        logger.info("[Bearer Token] Generating bearer token")
        try:
            # Get token using the EKS get_token method
            token = self.eks_client.get_token(
                clusterName=self.cluster_name
            )
            logger.info("[Bearer Token] Successfully got token from EKS")
            
            return token['token']
            
        except Exception as e:
            logger.error(f"[Bearer Token] Error generating token: {str(e)}")
            raise e

    def _write_ca_cert(self, ca_data):
        """Write cluster CA cert to temp file"""
        import base64
        import tempfile
        
        logger.info("[CA Cert] Writing cluster CA certificate")
        try:
            # Decode base64 CA cert
            ca_cert = base64.b64decode(ca_data)
            logger.info(f"[CA Cert] Decoded cert length: {len(ca_cert)} bytes")
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(delete=False) as temp:
                temp.write(ca_cert)
                logger.info(f"[CA Cert] Written to temp file: {temp.name}")
                return temp.name
        except Exception as e:
            logger.error(f"[CA Cert] Error writing cert: {str(e)}")
            raise e

    async def add_tags_to_nodegroup(self, nodegroup_name, tags):
        """Add tags to an existing nodegroup"""
        try:
            logger.info(f"Adding tags to nodegroup {nodegroup_name}: {tags}")
            arn = await self.get_nodegroup_arn(nodegroup_name)
            if not arn:
                return False, "Could not find nodegroup ARN"
            
            self.eks_client.tag_resource(
                resourceArn=arn,
                tags=tags
            )
            return True, "Tags added successfully"
        except Exception as e:
            logger.error(f"Error adding tags to nodegroup: {str(e)}")
            return False, str(e)
            
    async def get_nodegroup_arn(self, nodegroup_name):
        """Get the ARN of a nodegroup"""
        try:
            response = self.eks_client.describe_nodegroup(
                clusterName=self.cluster_name,
                nodegroupName=nodegroup_name
            )
            return response['nodegroup']['nodegroupArn']
        except Exception as e:
            logger.error(f"Error getting nodegroup ARN: {str(e)}")
            return None

    async def get_nodegroup_info(self, nodegroup_name):
        """Get detailed information about a nodegroup"""
        try:
            logger.info(f"[INFO] Entering get_nodegroup_info with nodegroup_name: {nodegroup_name}")
            
            response = self.eks_client.describe_nodegroup(
                clusterName=self.cluster_name,
                nodegroupName=nodegroup_name
            )
            
            logger.debug(f"[DEBUG] Full response from describe_nodegroup: {json.dumps(response, default=str)}")
            
            if 'nodegroup' in response:
                nodegroup = response['nodegroup']
                logger.info(f"[INFO] Successfully got nodegroup info: {json.dumps(nodegroup, default=str)}")
                return nodegroup
            
            logger.warning(f"[INFO] No nodegroup data found in response: {json.dumps(response, default=str)}")
            return None
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            logger.error(f"[INFO] AWS ClientError in get_nodegroup_info:")
            logger.error(f"[INFO] Error Code: {error_code}")
            logger.error(f"[INFO] Error Message: {error_msg}")
            
            if error_code == 'ResourceNotFoundException':
                logger.warning(f"[INFO] Nodegroup '{nodegroup_name}' not found")
                return None
                
            raise e
            
        except Exception as e:
            logger.error(f"[INFO] Error getting nodegroup info: {str(e)}")
            return None
        
        logger.info(f"[INFO] Exiting get_nodegroup_info")

    def get_nodegroup_running_time(self, nodegroup_name):
        """Get the running time of a nodegroup in hours"""
        try:
            response = self.eks_client.describe_nodegroup(
                clusterName=self.cluster_name,
                nodegroupName=nodegroup_name
            )
            
            # Get creation time of the nodegroup
            creation_time = response['nodegroup']['createdAt']
            current_time = datetime.now(timezone.utc)
            running_time = current_time - creation_time
            
            # Return running time in hours
            return running_time.total_seconds() / 3600
            
        except Exception as e:
            logger.error(f"Error getting nodegroup running time: {str(e)}")
            return None

    def is_performance_nodegroup(self, nodegroup_name):
        """Check if a nodegroup is a performance nodegroup based on its tags"""
        try:
            response = self.eks_client.describe_nodegroup(
                clusterName=self.cluster_name,
                nodegroupName=nodegroup_name
            )
            
            # Check tags
            tags = response['nodegroup'].get('tags', {})
            return tags.get('component') == 'performance-test'
            
        except Exception as e:
            logger.error(f"Error checking performance nodegroup: {str(e)}")
            return False