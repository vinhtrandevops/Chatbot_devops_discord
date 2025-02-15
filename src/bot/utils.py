import discord
from ..utils.logger import get_logger

logger = get_logger(__name__)

async def add_success_reaction(ctx_or_message):
    """Add a success reaction to a message"""
    try:
        if hasattr(ctx_or_message, 'message'):
            # If it's a Context object
            await ctx_or_message.message.add_reaction('✅')
        else:
            # If it's a Message object
            await ctx_or_message.add_reaction('✅')
    except Exception as e:
        logger.error(f"Error adding success reaction: {str(e)}")

async def add_error_reaction(ctx_or_message):
    """Add an error reaction to a message"""
    try:
        if hasattr(ctx_or_message, 'message'):
            # If it's a Context object
            await ctx_or_message.message.add_reaction('❌')
        else:
            # If it's a Message object
            await ctx_or_message.add_reaction('❌')
    except Exception as e:
        logger.error(f"Error adding error reaction: {str(e)}")

def create_embed(title, description=None, color=discord.Color.blue()):
    """Create a Discord embed with standard formatting"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    return embed

def format_instance_info(instance_details):
    """Format instance details for Discord embed"""
    if not instance_details:
        return None
        
    fields = [
        ("Instance ID", instance_details['instance_id'], True),
        ("Type", instance_details['instance_type'], True),
        ("State", instance_details['state'], True),
        ("Launch Time", instance_details['launch_time'].strftime("%Y-%m-%d %H:%M:%S"), False),
        ("Availability Zone", instance_details['az'], True),
        ("VPC ID", instance_details['vpc_id'], True),
        ("Private IP", instance_details['private_ip'], True),
        ("Public IP", instance_details['public_ip'], True),
        ("Platform", instance_details['platform'], True),
        ("Security Groups", "\n".join(instance_details['security_groups']) or "N/A", False),
    ]
    
    return fields