import boto3
from ..config import (
    AWS_ACCESS_KEY_ID, 
    AWS_SECRET_ACCESS_KEY, 
    AWS_REGION,
    EC2_CONTROL_LEVELS
)
from ..utils.logger import get_logger
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
import asyncio

logger = get_logger(__name__)

class EC2Manager:
    def __init__(self):
        """Initialize EC2 manager with AWS credentials or IAM role"""
        try:
            # First try to create client without credentials (will use IAM role if available)
            logger.info("Attempting to initialize AWS clients using IAM role...")
            self.ec2_client = boto3.client('ec2', region_name=AWS_REGION)
            self.cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)
            
            # Test the connection by making a simple API call
            self.ec2_client.describe_instances(MaxResults=5)
            logger.info("Successfully initialized AWS clients using IAM role")
            
        except Exception as e:
            logger.info(f"IAM role not available or insufficient permissions: {str(e)}")
            logger.info("Falling back to access key authentication")
            
            if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
                raise Exception("No IAM role available and AWS credentials not configured")
                
            # Fall back to using access keys
            self.ec2_client = boto3.client('ec2',
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

        self._load_config()

        # Initialize scheduler
        self.schedules = {}
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.scheduler.start()

    def _load_config(self):
        """Load EC2 configuration from environment variables"""
        # Load configuration from environment variables
        self.timezone = os.getenv('TIMEZONE', 'Asia/Ho_Chi_Minh')
        self.schedule_check_interval = int(os.getenv('SCHEDULE_CHECK_INTERVAL', '60'))
        self.max_schedules_per_instance = int(os.getenv('MAX_SCHEDULES_PER_INSTANCE', '1'))
        self.schedule_retention_days = int(os.getenv('SCHEDULE_RETENTION_DAYS', '30'))
        self.default_start_time = os.getenv('DEFAULT_START_TIME', '09:00')
        self.default_stop_time = os.getenv('DEFAULT_STOP_TIME', '18:00')

        # Load full control instances
        full_control = os.getenv('EC2_FULL_CONTROL_INSTANCES', '')
        self.full_control_instances = {}
        if full_control:
            for instance in full_control.split(','):
                if instance:
                    name, instance_id = instance.split(':')
                    self.full_control_instances[name.strip()] = instance_id.strip()

        # Load metrics only instances
        metrics_only = os.getenv('EC2_METRICS_ONLY_INSTANCES', '')
        self.metrics_only_instances = {}
        if metrics_only:
            for instance in metrics_only.split(','):
                if instance:
                    name, instance_id = instance.split(':')
                    self.metrics_only_instances[name.strip()] = instance_id.strip()

        # Combined instances
        self.all_instances = {**self.full_control_instances, **self.metrics_only_instances}

    def is_full_control(self, instance_id: str) -> bool:
        """Check if an instance is full control"""
        # First check if the input is a name
        if instance_id in self.full_control_instances:
            return True
        # Then check if it's an ID
        return instance_id in self.full_control_instances.values()

    def get_instance_name(self, instance_id: str) -> str:
        """Get instance name from id"""
        for name, id in self.all_instances.items():
            if id == instance_id:
                return name
        return instance_id

    def get_instance_id(self, name: str) -> str:
        """Get instance id from name"""
        return self.all_instances.get(name)

    async def list_instances(self):
        """List all EC2 instances with their status"""
        results = []
        
        for name, instance_id in self.all_instances.items():
            try:
                # Get instance details
                response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
                instance = response['Reservations'][0]['Instances'][0]
                
                # Get instance name tag
                instance_name = ''
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        instance_name = tag['Value']
                        break
                
                status = instance['State']['Name']
                instance_type = "Full Control" if self.is_full_control(instance_id) else "Metrics Only"
                
                results.append({
                    'name': name,
                    'id': instance_id,
                    'status': status,
                    'type': instance_type,
                    'ec2_name': instance_name
                })
            except Exception as e:
                logger.error(f"Error getting status for {name}: {str(e)}")
                
        return results

    async def start_instance(self, instance_id: str):
        """Start an EC2 instance"""
        try:
            # Check if instance_id is actually a name
            if instance_id in self.all_instances:
                instance_id = self.all_instances[instance_id]

            # Check if instance is full control
            if not self.is_full_control(instance_id):
                return False, "Không có quyền start instance này"

            response = self.ec2_client.start_instances(InstanceIds=[instance_id])
            logger.info(f"Starting EC2 instance: {instance_id}")
            return True, f"Đang khởi động EC2 instance: {self.get_instance_name(instance_id)}"
        except Exception as e:
            logger.error(f"Error starting EC2 instance: {str(e)}")
            return False, f"Lỗi khi khởi động EC2 instance: {str(e)}"

    async def stop_instance(self, instance_id: str):
        """Stop an EC2 instance"""
        try:
            # Check if instance_id is actually a name
            if instance_id in self.all_instances:
                instance_id = self.all_instances[instance_id]

            # Check if instance is full control
            if not self.is_full_control(instance_id):
                return False, "Không có quyền stop instance này"

            response = self.ec2_client.stop_instances(InstanceIds=[instance_id])
            logger.info(f"Stopping EC2 instance: {instance_id}")
            return True, f"Đang tắt EC2 instance: {self.get_instance_name(instance_id)}"
        except Exception as e:
            logger.error(f"Error stopping EC2 instance: {str(e)}")
            return False, f"Lỗi khi tắt EC2 instance: {str(e)}"

    async def get_instance_status(self, instance_id: str):
        """Get status of an EC2 instance"""
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            status = response['Reservations'][0]['Instances'][0]['State']['Name']
            return status
        except Exception as e:
            logger.error(f"Error getting EC2 status: {str(e)}")
            return "unknown"

    async def get_instance_metrics(self, instance_id: str):
        """Get metrics for an EC2 instance"""
        try:
            end_time = datetime.datetime.utcnow()
            start_time = end_time - datetime.timedelta(hours=1)

            metrics = {
                'CPU': {
                    'MetricName': 'CPUUtilization',
                    'Unit': 'Percent'
                },
                'NetworkIn': {
                    'MetricName': 'NetworkIn',
                    'Unit': 'Bytes'
                },
                'NetworkOut': {
                    'MetricName': 'NetworkOut',
                    'Unit': 'Bytes'
                },
                'DiskReadOps': {
                    'MetricName': 'DiskReadOps',
                    'Unit': 'Count'
                },
                'DiskWriteOps': {
                    'MetricName': 'DiskWriteOps',
                    'Unit': 'Count'
                }
            }

            results = {}
            for metric_name, metric_info in metrics.items():
                response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',
                    MetricName=metric_info['MetricName'],
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,
                    Statistics=['Average']
                )

                if response['Datapoints']:
                    latest = max(response['Datapoints'], key=lambda x: x['Timestamp'])
                    value = latest['Average']
                    
                    if metric_info['Unit'] == 'Bytes':
                        value = f"{value / (1024 * 1024):.2f} MB"
                    elif metric_info['Unit'] == 'Percent':
                        value = f"{value:.1f}%"
                    else:
                        value = f"{value:.1f}"
                        
                    results[metric_name] = value
                else:
                    results[metric_name] = 'N/A'

            return True, results
        except Exception as e:
            logger.error(f"Error getting EC2 metrics: {str(e)}")
            return False, f"Lỗi khi lấy metrics: {str(e)}"

    async def add_schedule(self, instance_id, server_name, start_time=None, stop_time=None):
        """Add a schedule for an EC2 instance"""
        try:
            logger.info(f"Adding schedule - Instance: {server_name} ({instance_id}) | Start: {start_time} | Stop: {stop_time}")
            
            # Use default times if not provided
            start_time = start_time or self.default_start_time
            stop_time = stop_time or self.default_stop_time
            logger.info(f"Using times - Start: {start_time} | Stop: {stop_time} (default times used if None provided)")

            # Validate instance
            exists = await self.instance_exists(instance_id)
            logger.info(f"Instance existence check - ID: {instance_id} | Exists: {exists}")
            if not exists:
                logger.warning(f"Instance not found: {instance_id}")
                return False, "Instance không tồn tại"

            # Check schedule limit
            if len(self.schedules) >= self.max_schedules_per_instance:
                logger.warning(f"Schedule limit reached for instance {instance_id} - Current: {len(self.schedules)} | Max: {self.max_schedules_per_instance}")
                return False, f"Đã đạt giới hạn {self.max_schedules_per_instance} schedule cho mỗi instance"

            # Parse times
            try:
                logger.info(f"Parsing time values - Start: {start_time} | Stop: {stop_time}")
                start_hour, start_minute = map(int, start_time.split(':'))
                stop_hour, stop_minute = map(int, stop_time.split(':'))
                
                # Validate hour and minute ranges
                if not (0 <= start_hour <= 23 and 0 <= start_minute <= 59):
                    logger.warning(f"Invalid start time - Hour: {start_hour} | Minute: {start_minute}")
                    return False, "Giờ bật không hợp lệ. Giờ phải từ 00-23, phút phải từ 00-59"
                if not (0 <= stop_hour <= 23 and 0 <= stop_minute <= 59):
                    logger.warning(f"Invalid stop time - Hour: {stop_hour} | Minute: {stop_minute}")
                    return False, "Giờ tắt không hợp lệ. Giờ phải từ 00-23, phút phải từ 00-59"
                    
                # Convert to minutes for comparison
                start_minutes = start_hour * 60 + start_minute
                stop_minutes = stop_hour * 60 + stop_minute
                logger.info(f"Time comparison - Start minutes: {start_minutes} | Stop minutes: {stop_minutes}")
                
                # Ensure stop time is after start time
                if stop_minutes <= start_minutes:
                    logger.warning(f"Invalid time range - Stop time must be after start time")
                    return False, "Giờ tắt phải sau giờ bật"
                    
            except ValueError as e:
                logger.error(f"Time parsing error: {str(e)}")
                return False, "Format thởi gian không hợp lệ. Sử dụng HH:MM"

            # Calculate expiration
            expiration_date = datetime.datetime.now() + datetime.timedelta(days=self.schedule_retention_days)
            logger.info(f"Schedule expiration set to: {expiration_date}")

            # Remove existing schedule if any
            if instance_id in self.schedules:
                logger.info(f"Removing existing schedule for instance {instance_id}")
                self.scheduler.remove_job(f"start_{instance_id}")
                self.scheduler.remove_job(f"stop_{instance_id}")

            # Add start job
            logger.info(f"Adding start job - Hour: {start_hour} | Minute: {start_minute}")
            self.scheduler.add_job(
                self.start_instance,
                'cron',
                hour=start_hour,
                minute=start_minute,
                id=f"start_{instance_id}",
                args=[instance_id],
                timezone=self.timezone,
                replace_existing=True
            )

            # Add stop job
            logger.info(f"Adding stop job - Hour: {stop_hour} | Minute: {stop_minute}")
            self.scheduler.add_job(
                self.stop_instance,
                'cron',
                hour=stop_hour,
                minute=stop_minute,
                id=f"stop_{instance_id}",
                args=[instance_id],
                timezone=self.timezone,
                replace_existing=True
            )

            # Store schedule info
            self.schedules[instance_id] = {
                'server_name': server_name,
                'start_time': start_time,
                'stop_time': stop_time,
                'timezone': self.timezone,
                'created_at': datetime.datetime.now().isoformat(),
                'expires_at': expiration_date.isoformat()
            }
            logger.info(f"Schedule stored successfully for instance {instance_id}")

            return True, f"Schedule đã được thiết lập cho instance {server_name}"

        except Exception as e:
            logger.error(f"Error setting schedule: {str(e)}", exc_info=True)
            return False, f"Lỗi khi thiết lập schedule: {str(e)}"

    async def remove_schedule(self, instance_id):
        """Remove schedule for an EC2 instance"""
        try:
            if instance_id not in self.schedules:
                return False, "Không tìm thấy schedule cho instance này"

            self.scheduler.remove_job(f"start_{instance_id}")
            self.scheduler.remove_job(f"stop_{instance_id}")
            del self.schedules[instance_id]

            return True, "Schedule đã được xóa"
        except Exception as e:
            logger.error(f"Error removing schedule: {str(e)}")
            return False, f"Lỗi khi xóa schedule: {str(e)}"

    async def get_schedule(self, instance_id):
        """Get schedule information for an EC2 instance"""
        return self.schedules.get(instance_id)

    async def list_schedules(self):
        """List all schedules"""
        return self.schedules

    async def cleanup_expired_schedules(self):
        """Clean up expired schedules"""
        now = datetime.datetime.now()
        expired = []
        
        for instance_id, schedule in self.schedules.items():
            expiration = datetime.datetime.fromisoformat(schedule['expires_at'])
            if now > expiration:
                expired.append(instance_id)
        
        for instance_id in expired:
            await self.remove_schedule(instance_id)

    async def instance_exists(self, instance_id: str) -> bool:
        """Check if an EC2 instance exists"""
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            return len(response['Reservations']) > 0
        except self.ec2_client.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                return False
            raise e

    async def get_account_billing(self):
        """Get AWS account billing information for the current month"""
        try:
            # Create Cost Explorer client
            ce = boto3.client(
                'ce',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name='us-east-1'  # Cost Explorer is only available in us-east-1
            )
            
            # Get start and end dates for current month
            now = datetime.datetime.now()
            start_of_month = datetime.datetime(now.year, now.month, 1)
            
            logger.info(f"Getting billing information from {start_of_month.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")
            
            # Get total costs with service breakdown
            logger.info("Calling Cost Explorer API...")
            response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_of_month.strftime('%Y-%m-%d'),
                    'End': now.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'}
                ]
            )
            
            logger.info(f"Response structure: {list(response.keys())}")
            logger.debug(f"Full response: {response}")
            
            if 'ResultsByTime' not in response:
                logger.error(f"ResultsByTime not found in response. Response keys: {list(response.keys())}")
                return False, "Invalid response format from Cost Explorer API"
                
            if not response['ResultsByTime']:
                logger.warning("ResultsByTime is empty")
                return False, "No billing data available for the current month"
                
            result = response['ResultsByTime'][0]
            logger.info(f"Result structure: {list(result.keys())}")
            logger.debug(f"Full result: {result}")
            
            # Get total cost
            if 'Total' not in result:
                logger.error(f"Total not found in result. Result keys: {list(result.keys())}")
                return False, "Missing total cost information"
                
            total_data = result['Total']
            logger.info(f"Total data structure: {total_data}")
            
            # Try to get cost from Groups if Total is empty
            if not total_data and 'Groups' in result:
                logger.info("Total is empty, calculating from Groups")
                total = 0
                currency = 'USD'  # Default currency
                
                for group in result['Groups']:
                    try:
                        cost = float(group['Metrics']['UnblendedCost']['Amount'])
                        total += cost
                        currency = group['Metrics']['UnblendedCost']['Unit']
                        logger.debug(f"Added cost from group: ${cost:.2f} {currency}")
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Error processing group cost: {str(e)}")
                        continue
            
                logger.info(f"Calculated total from groups: ${total:.2f} {currency}")
            else:
                if 'UnblendedCost' not in total_data:
                    logger.error(f"UnblendedCost not found in Total. Total keys: {list(total_data.keys())}")
                    return False, "Missing UnblendedCost information"
                    
                total = float(total_data['UnblendedCost']['Amount'])
                currency = total_data['UnblendedCost']['Unit']
                
            logger.info(f"Total cost: ${total:.2f} {currency}")
            
            # Get service-wise costs
            services = {}
            for group in result.get('Groups', []):
                try:
                    service_name = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    if cost > 0:  # Only include services with costs
                        services[service_name] = round(cost, 2)
                        logger.debug(f"Service cost: {service_name} = ${cost:.2f}")
                except (KeyError, ValueError) as e:
                    logger.warning(f"Error processing group {group}: {str(e)}")
                    continue
            
            # Sort services by cost
            sorted_services = dict(sorted(services.items(), key=lambda x: x[1], reverse=True))
            logger.info(f"Found {len(sorted_services)} services with costs")
            
            return True, {
                'start_date': start_of_month.strftime('%Y-%m-%d'),
                'end_date': now.strftime('%Y-%m-%d'),
                'total_cost': f"{total:.2f}",
                'currency': currency,
                'services': sorted_services
            }
                
        except Exception as e:
            logger.error(f"Error getting billing information: {str(e)}")
            logger.exception("Full traceback:")
            return False, f"Error getting billing information: {str(e)}"

    async def get_instance_state(self, instance_id: str):
        """Get state of an EC2 instance
        
        Returns:
            tuple: (success: bool, state: str)
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            state = response['Reservations'][0]['Instances'][0]['State']['Name']
            logger.info(f"Got instance state for {instance_id}: {state}")
            return True, state
        except Exception as e:
            logger.error(f"Error getting instance state: {str(e)}")
            return False, str(e)

    async def wait_for_state(self, instance_id: str, target_state: str, timeout: int = 300):
        """Wait for instance to reach target state
        
        Args:
            instance_id: EC2 instance ID
            target_state: Desired state ('running', 'stopped', etc)
            timeout: Maximum seconds to wait
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            start_time = datetime.datetime.now()
            while (datetime.datetime.now() - start_time).seconds < timeout:
                success, current_state = await self.get_instance_state(instance_id)
                logger.info(f"Waiting for state - Instance: {instance_id} | Current: {current_state} | Target: {target_state}")
                
                if not success:
                    return False, f"Lỗi khi kiểm tra trạng thái: {current_state}"
                
                if current_state == target_state:
                    return True, f"Instance đã {target_state}"
                    
                # Valid transition states
                if target_state == "stopped" and current_state == "stopping":
                    await asyncio.sleep(5)
                    continue
                    
                if target_state == "running" and current_state == "pending":
                    await asyncio.sleep(5)
                    continue
                    
                # Invalid states
                if current_state in ["terminated", "shutting-down"]:
                    return False, f"Instance trong trạng thái không hợp lệ: {current_state}"
                
                # Other transitional states
                if current_state in ["stopping", "pending"]:
                    await asyncio.sleep(5)
                    continue
                    
                await asyncio.sleep(5)
                
            return False, f"Timeout khi chờ instance {target_state}"
            
        except Exception as e:
            logger.error(f"Error waiting for state: {str(e)}")
            return False, f"Lỗi khi chờ trạng thái: {str(e)}"