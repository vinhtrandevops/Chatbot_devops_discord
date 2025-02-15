import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables
logger.info("Loading environment variables...")
load_dotenv()

# Bot Configuration
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
NOTIFICATION_CHANNEL_ID = os.getenv('NOTIFICATION_CHANNEL_ID')

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'ap-southeast-1')

# EKS Configuration
EKS_CLUSTER_NAME = os.getenv('EKS_CLUSTER_NAME', 'snowee-staging')

# EC2 Configuration
EC2_FULL_CONTROL = os.getenv('EC2_FULL_CONTROL_INSTANCES', '')
EC2_METRICS_ONLY = os.getenv('EC2_METRICS_ONLY_INSTANCES', '')

EC2_INSTANCES = {}
EC2_CONTROL_LEVELS = {}

# Process full control instances
for instance in EC2_FULL_CONTROL.split(','):
    if instance:
        friendly_name, instance_id = instance.split(':')
        EC2_INSTANCES[friendly_name.strip()] = instance_id.strip()
        EC2_CONTROL_LEVELS[friendly_name.strip()] = 1

# Process metrics only instances
for instance in EC2_METRICS_ONLY.split(','):
    if instance:
        friendly_name, instance_id = instance.split(':')
        EC2_INSTANCES[friendly_name.strip()] = instance_id.strip()
        EC2_CONTROL_LEVELS[friendly_name.strip()] = 2

# RDS Configuration
RDS_FULL_CONTROL = os.getenv('RDS_FULL_CONTROL_INSTANCES', '')
RDS_METRICS_ONLY = os.getenv('RDS_METRICS_ONLY_INSTANCES', '')

RDS_INSTANCES = {}
RDS_CONTROL_LEVELS = {}

# Process full control instances
for instance in RDS_FULL_CONTROL.split(','):
    if instance:
        instance_id, friendly_name = instance.split(':')
        RDS_INSTANCES[friendly_name] = instance_id
        RDS_CONTROL_LEVELS[friendly_name] = 1

# Process metrics only instances
for instance in RDS_METRICS_ONLY.split(','):
    if instance:
        instance_id, friendly_name = instance.split(':')
        RDS_INSTANCES[friendly_name] = instance_id
        RDS_CONTROL_LEVELS[friendly_name] = 2

# Instance State Check Configuration
STATE_CHECK_INTERVAL = int(os.getenv('STATE_CHECK_INTERVAL', '10'))  # seconds
STATE_CHECK_TIMEOUT = int(os.getenv('STATE_CHECK_TIMEOUT', '300'))  # seconds

# AI Provider Configuration
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai')  # 'openai' or 'deepseek'
logger.info(f"Loaded AI_PROVIDER: {AI_PROVIDER}")

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '1000'))
OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
logger.info(f"Loaded OpenAI Model: {OPENAI_MODEL}")

# DeepSeek Configuration
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
DEEPSEEK_MAX_TOKENS = int(os.getenv('DEEPSEEK_MAX_TOKENS', '1000'))
DEEPSEEK_TEMPERATURE = float(os.getenv('DEEPSEEK_TEMPERATURE', '0.7'))

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'