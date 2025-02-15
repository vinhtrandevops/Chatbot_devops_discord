import time
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from ..config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    EC2_INSTANCES,
    EC2_CONTROL_LEVELS,
    RDS_INSTANCES,
    RDS_CONTROL_LEVELS,
    STATE_CHECK_INTERVAL,
    STATE_CHECK_TIMEOUT,
    AI_PROVIDER
)
from ..aws.ec2 import EC2Manager
from ..aws.rds import RDSManager
from ..aws.eks import EKSManager
from ..utils.logger import get_logger
from .utils import add_success_reaction, add_error_reaction, create_embed, format_instance_info
from ..services.deepseek import DeepSeekService
from ..services.openai_service import OpenAIService
import random
from datetime import datetime, timezone
import os
import json

logger = get_logger(__name__)

class EC2Commands(commands.Cog):
    """Commands for managing EC2 instances"""
    
    def __init__(self, bot):
        self.bot = bot
        self.ec2_manager = EC2Manager()
        self.rds_manager = RDSManager()
        # Initialize both services
        self.openai_service = OpenAIService()
        self.deepseek_service = DeepSeekService()
        # Set primary service based on config
        self.primary_service = self.openai_service if AI_PROVIDER == 'openai' else self.deepseek_service
        self.fallback_service = self.deepseek_service if AI_PROVIDER == 'openai' else self.openai_service
        logger.info(f"Using {AI_PROVIDER} as primary service with fallback")
        self.command_help = {
            "start": {
                "description": "Khởi động một EC2 instance",
                "usage": "!start <tên_server>",
                "example": "!start prod-server"
            },
            "stop": {
                "description": "Tắt một EC2 instance",
                "usage": "!stop <tên_server>",
                "example": "!stop prod-server"
            },
            "status": {
                "description": "Kiểm tra trạng thái của EC2 instance",
                "usage": "!status [tên_server]",
                "example": "!status\n!status prod-server"
            },
            "metrics": {
                "description": "Xem metrics của EC2 instance",
                "usage": "!metrics [tên_server]",
                "example": "!metrics\n!metrics prod-server"
            },
            "schedule": {
                "description": "Đặt lịch tự động start/stop EC2 instance",
                "usage": "!schedule <tên_server> <giờ_bật> <giờ_tắt>",
                "example": "!schedule prod-server 09:00 18:00"
            },
            "unschedule": {
                "description": "Xóa lịch tự động start/stop EC2 instance",
                "usage": "!unschedule <tên_server>",
                "example": "!unschedule prod-server"
            },
            "schedules": {
                "description": "Xem danh sách các lịch tự động",
                "usage": "!schedules",
                "example": "!schedules"
            },
            "rds-start": {
                "description": "Khởi động RDS instance (chỉ full control)",
                "usage": "!rds-start <tên_server>",
                "example": "!rds-start staging-db"
            },
            "rds-stop": {
                "description": "Tắt RDS instance (chỉ full control)",
                "usage": "!rds-stop <tên_server>",
                "example": "!rds-stop staging-db"
            },
            "rds-metrics": {
                "description": "Xem metrics của RDS instance",
                "usage": "!rds-metrics [tên_server]",
                "example": "!rds-metrics\n!rds-metrics prod-db"
            },
            "ask": {
                "description": "Hỏi AI assistant về AWS",
                "usage": "!ask <câu_hỏi>",
                "example": "!ask Làm sao để tối ưu chi phí EC2?"
            },
            "bill": {
                "description": "Xem chi phí AWS trong tháng hiện tại",
                "usage": "!bill",
                "example": "!bill"
            },
            "eks-list": {
                "description": "Liệt kê tất cả nodegroups và tags của chúng",
                "usage": "!eks-list",
                "example": "!eks-list"
            },
            "eks-tag": {
                "description": "Thêm tags cho một nodegroup",
                "usage": "!eks-tag <tên_nodegroup> <key1=value1> [key2=value2 ...]",
                "example": "!eks-tag nodegroup-1 environment=prod team=backend"
            },
            "eks-untag": {
                "description": "Xóa tags khỏi một nodegroup",
                "usage": "!eks-untag <tên_nodegroup> <key1> [key2 ...]",
                "example": "!eks-untag nodegroup-1 environment team"
            },
            "eks-scale": {
                "description": "Thay đổi kích thước của một nodegroup",
                "usage": "!eks-scale <tên_nodegroup> <số_lượng_node>",
                "example": "!eks-scale nodegroup-1 5"
            },
            "eks-status": {
                "description": "Xem trạng thái chi tiết của một nodegroup",
                "usage": "!eks-status <tên_nodegroup>",
                "example": "!eks-status nodegroup-1"
            },
            "eks-scalable": {
                "description": "Liệt kê các nodegroup có thể scale với thông tin chi tiết",
                "usage": "!eks-scalable",
                "example": "!eks-scalable"
            },
            "eks-create": {
                "description": "Tạo nodegroup mới với cấu hình và tags tùy chọn. Hỗ trợ ON_DEMAND hoặc SPOT instances.",
                "usage": "!eks-create <tên_nodegroup> <instance_type> <desired_size> <min_size> <max_size> [ON_DEMAND|SPOT] [key1=value1 key2=value2 ...]",
                "example": "!eks-create prod-nodes t3.medium 3 2 5 SPOT environment=prod team=backend"
            },
            "eks-delete": {
                "description": "Xóa một nodegroup",
                "usage": "!eks-delete <tên_nodegroup>",
                "example": "!eks-delete staging-nodes"
            },
        }

    async def cog_load(self):
        logger.info("EC2Commands cog loaded")

    async def wait_for_state(self, ctx, instance_id, target_state, server_name):
        """Chờ và cập nhật trạng thái cho đến khi instance đạt trạng thái mong muốn"""
        start_time = time.time()
        if target_state == "running":
            message = await ctx.send(f"⚡ **[INIT]** Khởi tạo instance `{server_name}`...")
        else:
            message = await ctx.send(f"⚡ **[SHUTDOWN]** Terminating instance `{server_name}`...")
        
        while time.time() - start_time < STATE_CHECK_TIMEOUT:
            state, _ = await self.ec2_manager.get_instance_state(instance_id)
            if state == target_state:
                if target_state == "running":
                    await message.edit(content=f"✅ **[SUCCESS]** Instance `{server_name}` đã khởi động | Status: Running")
                else:
                    await message.edit(content=f"✅ **[SUCCESS]** Instance `{server_name}` đã shutdown | Status: Stopped")
                return True
            elif state in ['pending', 'stopping']:
                status = "provisioning" if state == 'pending' else "terminating"
                await message.edit(content=f"🔄 **[IN_PROGRESS]** Instance `{server_name}` đang {status}... | Status: {state}")
            else:
                await message.edit(content=f"❌ **[ERROR]** Instance `{server_name}` trong trạng thái không mong muốn | Status: {state}")
                return False
            await asyncio.sleep(STATE_CHECK_INTERVAL)
        
        await message.edit(content=f"⚠️ **[TIMEOUT]** Operation timeout khi xử lý instance `{server_name}` | Target State: {target_state}")
        return False

    async def wait_for_rds_state(self, ctx, instance_id, target_state, server_name):
        """Chờ và cập nhật trạng thái cho đến khi RDS instance đạt trạng thái mong muốn"""
        start_time = time.time()
        state_map = {
            "available": "running",
            "stopped": "stopped"
        }
        
        if target_state == "available":
            message = await ctx.send(f"⚡ **[INIT]** Khởi tạo RDS instance `{server_name}`...")
        else:
            message = await ctx.send(f"⚡ **[SHUTDOWN]** Stopping RDS instance `{server_name}`...")
        
        while time.time() - start_time < STATE_CHECK_TIMEOUT:
            success, state = await self.rds_manager.get_instance_status(instance_id)
            if not success:
                await message.edit(content=f"❌ **[ERROR]** Không thể lấy trạng thái của instance `{server_name}`")
                return False
                
            if state == target_state:
                if target_state == "available":
                    await message.edit(content=f"✅ **[SUCCESS]** RDS instance `{server_name}` đã khởi động | Status: Running")
                else:
                    await message.edit(content=f"✅ **[SUCCESS]** RDS instance `{server_name}` đã shutdown | Status: Stopped")
                return True
            elif state in ['starting', 'stopping']:
                status = "provisioning" if state == 'starting' else "terminating"
                await message.edit(content=f"🔄 **[IN_PROGRESS]** RDS instance `{server_name}` đang {status}... | Status: {state}")
            else:
                await message.edit(content=f"❌ **[ERROR]** RDS instance `{server_name}` trong trạng thái không mong muốn | Status: {state}")
                return False
            await asyncio.sleep(STATE_CHECK_INTERVAL)
        
        await message.edit(content=f"⚠️ **[TIMEOUT]** Operation timeout khi xử lý RDS instance `{server_name}` | Target State: {target_state}")
        return False

    @commands.command(name="list_servers")
    async def list_servers(self, ctx):
        """Hiển thị danh sách EC2 instances"""
        logger.info(f"Command: list_servers | User: {ctx.author} | Channel: {ctx.channel}")
        
        try:
            instances = await self.ec2_manager.list_instances()
            
            if not instances:
                embed = discord.Embed(
                    title="❌ Không tìm thấy EC2 instances",
                    description="Không có EC2 instance nào được cấu hình.\nVui lòng kiểm tra file .env",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
                
            embed = discord.Embed(
                title="📋 Danh sách EC2 Instances",
                description="Thông tin cơ bản về các EC2 instances",
                color=discord.Color.blue()
            )
            
            for instance in instances:
                name = instance['name']
                status = instance['status']
                instance_type = instance['type']
                instance_id = instance['id']
                ec2_name = instance['ec2_name']
                
                emoji = "🟢" if status == "running" else "🔴" if status == "stopped" else "🟡"
                value = (
                    f"**Status:** {status}\n"
                    f"**Type:** {instance_type}\n"
                    f"**ID:** `{instance_id}`\n"
                    f"**EC2 Name:** {ec2_name or 'N/A'}"
                )
                
                embed.add_field(
                    name=f"{emoji} {name}",
                    value=value,
                    inline=False
                )
            
            embed.set_footer(text="Sử dụng !status <tên> để xem chi tiết hơn")
            await ctx.send(embed=embed)
            await add_success_reaction(ctx)
            
        except Exception as e:
            error_msg = f"Lỗi khi lấy thông tin EC2: {str(e)}"
            logger.error(error_msg)
            
            embed = discord.Embed(
                title="❌ Lỗi",
                description=error_msg,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="start")
    async def start(self, ctx, server_name: str = None):
        """Khởi động EC2 instance"""
        try:
            if not server_name:
                await self.list_servers(ctx)
                return
                
            if server_name not in EC2_INSTANCES:
                await ctx.send(f"❌ **[ERROR]** EC2 instance `{server_name}` không tồn tại")
                await add_error_reaction(ctx)
                return

            instance_id = EC2_INSTANCES[server_name]
            
            # Check current status first
            status_success, current_state = await self.ec2_manager.get_instance_state(instance_id)
            if not status_success:
                await ctx.send(f"❌ **[ERROR]** Không thể lấy trạng thái của instance `{server_name}`")
                await add_error_reaction(ctx)
                return
                
            # Show current status
            status_message = await ctx.send(f"ℹ️ **[STATUS]** Instance `{server_name}` hiện đang {current_state}")
            
            # Already running
            if current_state == "running":
                await status_message.edit(content=f"ℹ️ **[STATUS]** Instance `{server_name}` đã running sẵn rồi!")
                await add_success_reaction(ctx)
                return
            
            # Start if not running
            success, message = await self.ec2_manager.start_instance(instance_id)
            if not success:
                await status_message.edit(content=f"❌ **[ERROR]** {message}")
                await add_error_reaction(ctx)
                return
            
            # Wait and update status
            while True:
                success, current_state = await self.ec2_manager.get_instance_state(instance_id)
                if not success:
                    await status_message.edit(content=f"❌ **[ERROR]** Lỗi khi kiểm tra trạng thái")
                    await add_error_reaction(ctx)
                    return
                
                if current_state == "running":
                    await status_message.edit(content=f"✅ **[SUCCESS]** Instance `{server_name}` đã running thành công!")
                    await add_success_reaction(ctx)
                    return
                    
                await status_message.edit(content=f"ℹ️ **[STATUS]** Instance `{server_name}` đang {current_state}...")
                await asyncio.sleep(5)
            
        except Exception as e:
            error_msg = f"Lỗi khi start EC2 instance: {str(e)}"
            logger.error(error_msg)
            await ctx.send(f"❌ **[ERROR]** {error_msg}")
            await add_error_reaction(ctx)

    @commands.command(name="stop")
    async def stop(self, ctx, server_name: str = None):
        """Tắt EC2 instance"""
        try:
            if not server_name:
                await self.list_servers(ctx)
                return
                
            if server_name not in EC2_INSTANCES:
                await ctx.send(f"❌ **[ERROR]** EC2 instance `{server_name}` không tồn tại")
                await add_error_reaction(ctx)
                return

            if EC2_CONTROL_LEVELS[server_name] != 1:
                await ctx.send(f"❌ **[ERROR]** Không có quyền stop instance `{server_name}`")
                await add_error_reaction(ctx)
                return
                
            instance_id = EC2_INSTANCES[server_name]
            
            # Check current status first
            status_success, current_state = await self.ec2_manager.get_instance_state(instance_id)
            if not status_success:
                await ctx.send(f"❌ **[ERROR]** Không thể lấy trạng thái của instance `{server_name}`")
                await add_error_reaction(ctx)
                return
            
            # Show current status
            status_message = await ctx.send(f"ℹ️ **[STATUS]** Instance `{server_name}` hiện đang {current_state}")
            
            # Already stopped
            if current_state == "stopped":
                await status_message.edit(content=f"ℹ️ **[STATUS]** Instance `{server_name}` đã stopped sẵn rồi!")
                await add_success_reaction(ctx)
                return
            
            # Stop if not stopped
            success, message = await self.ec2_manager.stop_instance(instance_id)
            if not success:
                await status_message.edit(content=f"❌ **[ERROR]** {message}")
                await add_error_reaction(ctx)
                return
            
            # Wait and update status
            while True:
                success, current_state = await self.ec2_manager.get_instance_state(instance_id)
                if not success:
                    await status_message.edit(content=f"❌ **[ERROR]** Lỗi khi kiểm tra trạng thái")
                    await add_error_reaction(ctx)
                    return
                
                if current_state == "stopped":
                    await status_message.edit(content=f"✅ **[SUCCESS]** Instance `{server_name}` đã stopped thành công!")
                    await add_success_reaction(ctx)
                    return
                    
                await status_message.edit(content=f"ℹ️ **[STATUS]** Instance `{server_name}` đang {current_state}...")
                await asyncio.sleep(5)
            
        except Exception as e:
            error_msg = f"Lỗi khi stop EC2 instance: {str(e)}"
            logger.error(error_msg)
            await ctx.send(f"❌ **[ERROR]** {error_msg}")
            await add_error_reaction(ctx)

    @commands.command(name="status")
    async def status(self, ctx, server_name: str = None):
        """Xem trạng thái chi tiết của EC2 instance"""
        logger.info(f"Command: status {server_name} | User: {ctx.author} | Channel: {ctx.channel}")
        
        try:
            if server_name is None:
                # Nếu không chỉ định tên, hiển thị status của tất cả instances
                instances = await self.ec2_manager.list_instances()
                if not instances:
                    await ctx.send("❌ Không tìm thấy EC2 instance nào")
                    return
                    
                embed = discord.Embed(
                    title="📊 Trạng thái EC2 Instances",
                    color=discord.Color.blue()
                )
                
                for instance in instances:
                    name = instance['name']
                    status = instance['status']
                    instance_type = instance['type']
                    instance_id = instance['id']
                    ec2_name = instance['ec2_name']
                    
                    emoji = "🟢" if status == "running" else "🔴" if status == "stopped" else "🟡"
                    value = (
                        f"**Status:** {status}\n"
                        f"**Type:** {instance_type}\n"
                        f"**EC2 Name:** {ec2_name or 'N/A'}"
                    )
                    
                    embed.add_field(
                        name=f"{emoji} {name}",
                        value=value,
                        inline=True
                    )
                    
            else:
                # Lấy instance ID từ tên
                instance_id = self.ec2_manager.get_instance_id(server_name)
                if not instance_id:
                    await ctx.send(f"❌ Không tìm thấy instance: {server_name}")
                    return
                
                # Lấy thông tin chi tiết
                response = self.ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
                instance = response['Reservations'][0]['Instances'][0]
                
                # Lấy Name tag
                instance_name = ''
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        instance_name = tag['Value']
                        break
                
                status = instance['State']['Name']
                instance_type = "Full Control" if self.ec2_manager.is_full_control(instance_id) else "Metrics Only"
                
                embed = discord.Embed(
                    title=f"� Chi tiết EC2 Instance: {server_name}",
                    color=discord.Color.blue()
                )
                
                emoji = "🟢" if status == "running" else "🔴" if status == "stopped" else "🟡"
                
                # Thông tin cơ bản
                basic_info = (
                    f"**Status:** {status}\n"
                    f"**Type:** {instance_type}\n"
                    f"**EC2 Name:** {instance_name or 'N/A'}\n"
                    f"**Instance ID:** `{instance_id}`"
                )
                embed.add_field(name=f"{emoji} Thông tin cơ bản", value=basic_info, inline=False)
                
                # Thông tin kỹ thuật
                tech_info = (
                    f"**Instance Type:** {instance['InstanceType']}\n"
                    f"**Platform:** {instance.get('Platform', 'Linux/UNIX')}\n"
                    f"**Availability Zone:** {instance['Placement']['AvailabilityZone']}\n"
                    f"**Private IP:** {instance.get('PrivateIpAddress', 'N/A')}\n"
                    f"**Public IP:** {instance.get('PublicIpAddress', 'N/A')}"
                )
                embed.add_field(name="🔧 Thông tin kỹ thuật", value=tech_info, inline=False)
                
                # Security Groups
                sg_info = "\n".join([f"- {sg['GroupName']} ({sg['GroupId']})" for sg in instance.get('SecurityGroups', [])])
                if sg_info:
                    embed.add_field(name="🔒 Security Groups", value=sg_info, inline=False)
                
                # Volumes
                volumes_info = "\n".join([
                    f"- {vol['DeviceName']}: {vol.get('Ebs', {}).get('VolumeId', 'N/A')}"
                    for vol in instance.get('BlockDeviceMappings', [])
                ])
                if volumes_info:
                    embed.add_field(name="💾 EBS Volumes", value=volumes_info, inline=False)
                
                # Launch time
                launch_time = instance['LaunchTime'].strftime("%Y-%m-%d %H:%M:%S")
                embed.set_footer(text=f"Launch Time: {launch_time}")
            
            await ctx.send(embed=embed)
            await add_success_reaction(ctx)
            
        except Exception as e:
            error_msg = f"Lỗi khi lấy trạng thái EC2: {str(e)}"
            logger.error(error_msg)
            
            embed = discord.Embed(
                title="❌ Lỗi",
                description=error_msg,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="help")
    async def help(self, ctx, command=None):
        """Hiển thị hướng dẫn sử dụng bot"""
        logger.info(f"Command: help {command} | User: {ctx.author} | Channel: {ctx.channel}")
        
        if command:
            # Hiển thị help cho một command cụ thể
            command_info = self.command_help.get(command)
            if not command_info:
                await ctx.send(f"❌ Không tìm thấy command: {command}")
                return
                
            embed = discord.Embed(
                title=f"� Help: !{command}",
                description=command_info['description'],
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Cách dùng",
                value=f"```{command_info['usage']}```",
                inline=False
            )
            embed.add_field(
                name="Ví dụ",
                value=f"```{command_info['example']}```",
                inline=False
            )
            
        else:
            # Hiển thị tổng quan các commands
            embed = discord.Embed(
                title="🤖 Hướng dẫn sử dụng Bot",
                description="Sử dụng `!help <command>` để xem chi tiết từng lệnh",
                color=discord.Color.blue()
            )
            
            # EC2 Commands - Full Control
            ec2_full = (
                "`!start <tên>` Start instance\n"
                "`!stop <tên>` Stop instance"
            )
            embed.add_field(
                name="🎮 EC2 Control",
                value=ec2_full,
                inline=True
            )
            
            # EC2 Commands - View
            ec2_view = (
                "`!list_servers` List instances\n"
                "`!status [tên]` Check status\n"
                "`!metrics [tên]` View metrics"
            )
            embed.add_field(
                name="� EC2 Monitor",
                value=ec2_view,
                inline=True
            )
            
            # EC2 Commands - Schedule
            ec2_schedule = (
                "`!schedule <tên> <giờ_bật> <giờ_tắt>` Set auto start/stop\n"
                "`!unschedule <tên>` Remove schedule\n"
                "`!schedules` List all schedules"
            )
            embed.add_field(
                name="⏰ EC2 Schedule",
                value=ec2_schedule,
                inline=True
            )
            
            # RDS Commands - Full Control
            rds_full = (
                "`!rds-start <tên>` Start instance\n"
                "`!rds-stop <tên>` Stop instance"
            )
            embed.add_field(
                name="🎮 RDS Control",
                value=rds_full,
                inline=True
            )
            
            # RDS Commands - View
            rds_view = (
                "`!rds-list` List instances\n"
                "`!rds-status [tên]` Check status\n"
                "`!rds-metrics [tên]` View metrics"
            )
            embed.add_field(
                name="📊 RDS Monitor",
                value=rds_view,
                inline=True
            )
            
            # EKS Commands
            eks_commands = (
                "`!eks-list` List nodegroups\n"
                "`!eks-scalable` List các nodegroup có thể scale\n"
                "`!eks-create <tên_nodegroup> <instance_type> <desired_size> <min_size> <max_size> [ON_DEMAND|SPOT] [key1=value1 key2=value2 ...]` Tạo nodegroup mới\n"
                "`!eks-delete <tên_nodegroup>` Xóa nodegroup\n"
                "`!eks-tag <tên_nodegroup> <key1=value1> [key2=value2 ...]` Add tags\n"
                "`!eks-untag <tên_nodegroup> <key1> [key2 ...]` Remove tags\n"
                "`!eks-scale <tên_nodegroup> <số_lượng_node>` Scale nodegroup\n"
                "`!eks-status <tên_nodegroup>` Check nodegroup status"
            )
            embed.add_field(
                name="📈 EKS Management",
                value=eks_commands,
                inline=True
            )

            # EKS Performance Commands
            eks_perf = (
                "`!eks setup-performance-for-dev` Tạo nodegroup cho dev\n"
                "`!eks delete-performance` Xóa performance nodegroup"
            )
            embed.add_field(
                name="🚀 EKS Performance",
                value=eks_perf,
                inline=True
            )
            
            # Support Commands
            support = (
                "`!help` Show this help\n"
                "`!help <command>` Command details"
            )
            embed.add_field(
                name="💡 Support",
                value=support,
                inline=True
            )
            
            # Notes
            notes = (
                "**Full Control:** Start/Stop instances\n"
                "**Monitor:** View status & metrics\n"
                "**Schedule:** Auto start/stop at set times\n"
                "**[tên]:** Optional parameter"
            )
            embed.add_field(
                name="📝 Notes",
                value=notes,
                inline=True
            )
            
        await ctx.send(embed=embed)
        await add_success_reaction(ctx)

    @commands.command(name="ask")
    async def ask(self, ctx, *, question: str):
        """Hỏi AI assistant về AWS EC2"""
        logger.info(f"Command: ask | User: {ctx.author} | Question: {question}")
        
        async with ctx.typing():
            try:
                response = await self.get_ai_response('ask', question)
                
                embed = discord.Embed(
                    title="🤖 AI Assistant",
                    description=response,
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Asked by {ctx.author}")
                
                await ctx.send(embed=embed)
                await add_success_reaction(ctx)
            except Exception as e:
                error_msg = "❌ Both AI services are currently unavailable. Please try again later."
                logger.error(f"Both AI services failed: {str(e)}")
                await ctx.send(error_msg)
                await add_error_reaction(ctx)

    @commands.command(name="ec2help")
    async def ec2_help(self, ctx, *, topic: str):
        """Nhận trợ giúp chi tiết về một chủ đề EC2"""
        logger.info(f"Command: ec2help | User: {ctx.author} | Topic: {topic}")
        
        async with ctx.typing():
            try:
                response = await self.get_ai_response('get_ec2_help', topic)
                
                embed = discord.Embed(
                    title=f"📚 EC2 Help: {topic}",
                    description=response,
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Requested by {ctx.author}")
                
                await ctx.send(embed=embed)
                await add_success_reaction(ctx)
            except Exception as e:
                error_msg = "❌ Both AI services are currently unavailable. Please try again later."
                logger.error(f"Both AI services failed: {str(e)}")
                await ctx.send(error_msg)
                await add_error_reaction(ctx)

    @commands.command(name="troubleshoot")
    async def troubleshoot(self, ctx, *, problem: str):
        """Nhận hướng dẫn xử lý sự cố EC2"""
        logger.info(f"Command: troubleshoot | User: {ctx.author} | Problem: {problem}")
        
        async with ctx.typing():
            try:
                response = await self.get_ai_response('troubleshoot_ec2', problem)
                
                embed = discord.Embed(
                    title="🔧 EC2 Troubleshooting",
                    description=response,
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Requested by {ctx.author}")
                
                await ctx.send(embed=embed)
                await add_success_reaction(ctx)
            except Exception as e:
                error_msg = "❌ Both AI services are currently unavailable. Please try again later."
                logger.error(f"Both AI services failed: {str(e)}")
                await ctx.send(error_msg)
                await add_error_reaction(ctx)

    @commands.command(name="metrics")
    async def metrics(self, ctx, server_name: str = None):
        """Xem metrics của EC2 instance"""
        logger.info(f"Command: metrics {server_name} | User: {ctx.author} | Channel: {ctx.channel}")
        
        try:
            if server_name is None:
                await ctx.send("❌ Vui lòng nhập tên instance. Ví dụ: `!metrics staging-server`")
                return
                
            # Lấy instance ID từ tên
            instance_id = self.ec2_manager.get_instance_id(server_name)
            if not instance_id:
                await ctx.send(f"❌ Không tìm thấy instance: {server_name}")
                return
                
            # Lấy metrics
            success, metrics = await self.ec2_manager.get_instance_metrics(instance_id)
            if not success:
                await ctx.send(f"❌ {metrics}")  # metrics chứa error message
                return
                
            embed = discord.Embed(
                title=f"📊 Metrics: {server_name}",
                color=discord.Color.blue()
            )
            
            # CPU
            cpu_value = metrics.get('CPU', 'N/A')
            embed.add_field(
                name="💻 CPU Usage",
                value=cpu_value,
                inline=True
            )
            
            # Network
            network_in = metrics.get('NetworkIn', 'N/A')
            network_out = metrics.get('NetworkOut', 'N/A')
            network_value = f"In: {network_in}\nOut: {network_out}"
            embed.add_field(
                name="🌐 Network",
                value=network_value,
                inline=True
            )
            
            # Disk
            disk_read = metrics.get('DiskReadOps', 'N/A')
            disk_write = metrics.get('DiskWriteOps', 'N/A')
            disk_value = f"Read: {disk_read}\nWrite: {disk_write}"
            embed.add_field(
                name="💾 Disk Operations",
                value=disk_value,
                inline=True
            )
            
            # Add timestamp
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            embed.set_footer(text=f"Last updated: {current_time}")
            
            await ctx.send(embed=embed)
            await add_success_reaction(ctx)
            
        except Exception as e:
            error_msg = f"Lỗi khi lấy metrics EC2: {str(e)}"
            logger.error(error_msg)
            
            embed = discord.Embed(
                title="❌ Lỗi",
                description=error_msg,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="bill")
    async def bill(self, ctx):
        """Hiển thị chi phí AWS trong tháng hiện tại"""
        logger.info(f"Command: bill | User: {ctx.author} | Channel: {ctx.channel}")
        
        try:
            success, result = await self.ec2_manager.get_account_billing()
            
            if not success:
                await ctx.send(f"❌ {result}")
                return
                
            embed = discord.Embed(
                title="💰 Chi Phí AWS",
                description=f"Từ {result['start_date']} đến {result['end_date']}",
                color=discord.Color.blue()
            )
            
            # Tổng Chi Phí
            embed.add_field(
                name="💵 Tổng Chi Phí",
                value=f"${result['total_cost']} {result['currency']}",
                inline=False
            )
            
            # Service Icons
            service_icons = {
                'EC2': '💻',
                'Elastic Compute Cloud': '💻',
                'RDS': '🗄️',
                'Relational Database': '🗄️',
                'Load Balancing': '⚖️',
                'CloudWatch': '📊',
                'Container': '📦',
                'Lambda': '⚡',
                'Simple Storage Service': '💾',
                'S3': '💾',
                'Tax': '💰',
                'Kinesis': '📈',
                'Virtual Private Cloud': '🔒',
                'Key Management': '🔑',
                'Interactive Video': '🎥',
                'Registry': '📦',
            }
            
            # Format each service with icon
            services = result['services']
            sorted_services = dict(sorted(services.items(), key=lambda x: x[1], reverse=True))
            
            for service_name, cost in sorted_services.items():
                # Find matching icon
                icon = '🔸'  # default icon
                for key, value in service_icons.items():
                    if key.lower() in service_name.lower():
                        icon = value
                        break
                
                # Clean up service name
                display_name = service_name.replace('Amazon ', '').replace('AWS ', '')
                if ' - ' in display_name:
                    display_name = display_name.split(' - ')[0]
                
                # Add field for each service
                embed.add_field(
                    name=f"{icon} {display_name}",
                    value=f"${cost:.2f} {result['currency']}",
                    inline=True
                )
            
            await ctx.send(embed=embed)
            await add_success_reaction(ctx)
            
        except Exception as e:
            error_msg = f"Lỗi khi lấy thông tin chi phí: {str(e)}"
            logger.error(error_msg)
            await ctx.send(f"❌ {error_msg}")

    @commands.command(name="rds-start")
    async def rds_start(self, ctx, server_name: str):
        """Start RDS instance
        Example: !rds-start snowee-db"""
        try:
            if server_name not in RDS_INSTANCES:
                await ctx.send(f"❌ **[ERROR]** RDS instance `{server_name}` không tồn tại")
                await add_error_reaction(ctx)
                return

            if RDS_CONTROL_LEVELS[server_name] != 1:
                await ctx.send(f"❌ **[ERROR]** Không có quyền start instance `{server_name}`")
                await add_error_reaction(ctx)
                return
                
            instance_id = RDS_INSTANCES[server_name]
            
            # Check current status first
            success, message = await self.rds_manager.start_instance(instance_id)
            
            if success:
                # Wait for the instance to be available
                success = await self.wait_for_rds_state(ctx, instance_id, "available", server_name)
                if success:
                    await add_success_reaction(ctx)
                else:
                    await add_error_reaction(ctx)
            else:
                await ctx.send(f"❌ **[ERROR]** {message}")
                await add_error_reaction(ctx)
                
        except Exception as e:
            error_msg = f"Lỗi khi start RDS instance: {str(e)}"
            logger.error(error_msg)
            await ctx.send(f"❌ {error_msg}")
            await add_error_reaction(ctx)

    @commands.command(name="rds-stop")
    async def rds_stop(self, ctx, server_name: str):
        """Stop RDS instance
        Example: !rds-stop snowee-db"""
        try:
            if server_name not in RDS_INSTANCES:
                await ctx.send(f"❌ **[ERROR]** RDS instance `{server_name}` không tồn tại")
                await add_error_reaction(ctx)
                return

            if RDS_CONTROL_LEVELS[server_name] != 1:
                await ctx.send(f"❌ **[ERROR]** Không có quyền stop instance `{server_name}`")
                await add_error_reaction(ctx)
                return
                
            instance_id = RDS_INSTANCES[server_name]
            success, message = await self.rds_manager.stop_instance(instance_id)
            
            if success:
                # Wait for the instance to be stopped
                success = await self.wait_for_rds_state(ctx, instance_id, "stopped", server_name)
                if success:
                    await add_success_reaction(ctx)
                else:
                    await add_error_reaction(ctx)
            else:
                await ctx.send(f"❌ **[ERROR]** {message}")
                await add_error_reaction(ctx)
                
        except Exception as e:
            error_msg = f"Lỗi khi stop RDS instance: {str(e)}"
            logger.error(error_msg)
            await ctx.send(f"❌ {error_msg}")
            await add_error_reaction(ctx)

    @commands.command(name="rds-status")
    async def rds_status(self, ctx, server_name: str):
        """Get RDS instance status
        Example: !rds-status snowee-db"""
        try:
            instance_id = await self.get_rds_instance_id(server_name)
            if not instance_id:
                await ctx.send(f"❌ **[ERROR]** RDS instance `{server_name}` không tồn tại")
                await add_error_reaction(ctx)
                return

            success, status = await self.rds_manager.get_instance_status(instance_id)
            if success:
                embed = discord.Embed(
                    title="ℹ️ **[RDS STATUS]**",
                    description=f"```yaml\nInstance: {server_name}\nStatus: {status}\n```",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
                await add_success_reaction(ctx)
            else:
                await ctx.send(f"❌ **[ERROR]** {status}")
                await add_error_reaction(ctx)

        except Exception as e:
            logger.error(f"Error in rds_status command: {str(e)}")
            await ctx.send(f"❌ **[ERROR]** Lỗi khi lấy trạng thái RDS: {str(e)}")
            await add_error_reaction(ctx)

    async def get_rds_instance_id(self, server_name: str) -> str:
        """Get RDS instance ID from server name"""
        if server_name not in RDS_INSTANCES:
            return None
        return RDS_INSTANCES[server_name]

    @commands.command(name="rds-list")
    async def rds_list(self, ctx):
        """List all RDS instances
        Example: !rds-list"""
        try:
            success, instances = await self.rds_manager.list_all_instances()
            
            if success:
                if not instances:
                    await ctx.send("📝 **[INFO]** Không có RDS instance nào")
                    return

                embed = discord.Embed(
                    title="📋 **[RDS INSTANCES]**",
                    description="Danh sách các RDS instances",
                    color=discord.Color.blue()
                )

                # Group instances by control level
                full_control = []
                metrics_only = []
                
                for friendly_name, instance_id in RDS_INSTANCES.items():
                    control_level = RDS_CONTROL_LEVELS[friendly_name]
                    instance_info = next((i for i in instances if i['identifier'] == instance_id), None)
                    
                    if instance_info:
                        instance_info['friendly_name'] = friendly_name
                        if control_level == 1:
                            full_control.append(instance_info)
                        else:
                            metrics_only.append(instance_info)

                # Add Full Control instances
                if full_control:
                    embed.add_field(
                        name="🎮 Full Control (Start/Stop/Metrics)",
                        value="```\nInstances có thể start/stop và xem metrics```",
                        inline=False
                    )
                    for instance in full_control:
                        status_emoji = "🟢" if instance['status'] == 'available' else "🔴" if instance['status'] == 'stopped' else "🟡"
                        embed.add_field(
                            name=f"{status_emoji} {instance['friendly_name']}",
                            value=f"```yaml\n"
                                  f"ID: {instance['identifier']}\n"
                                  f"Status: {instance['status']}\n"
                                  f"Engine: {instance['engine']}\n"
                                  f"Size: {instance['size']}\n"
                                  f"Storage: {instance['storage']}\n"
                                  f"Endpoint: {instance['endpoint']}\n```",
                            inline=False
                        )

                # Add Metrics Only instances
                if metrics_only:
                    embed.add_field(
                        name="📊 Metrics Only",
                        value="```\nInstances chỉ có thể xem metrics```",
                        inline=False
                    )
                    for instance in metrics_only:
                        status_emoji = "🟢" if instance['status'] == 'available' else "🔴" if instance['status'] == 'stopped' else "🟡"
                        embed.add_field(
                            name=f"{status_emoji} {instance['friendly_name']}",
                            value=f"```yaml\n"
                                  f"ID: {instance['identifier']}\n"
                                  f"Status: {instance['status']}\n"
                                  f"Engine: {instance['engine']}\n"
                                  f"Size: {instance['size']}\n"
                                  f"Storage: {instance['storage']}\n"
                                  f"Endpoint: {instance['endpoint']}\n```",
                            inline=False
                        )

                current_time = datetime.now().strftime("%H:%M:%S")
                embed.set_footer(text=f"System Time: {current_time} | Timezone: {self.ec2_manager.timezone}")
                
                await ctx.send(embed=embed)
                await add_success_reaction(ctx)
            else:
                await ctx.send(f"❌ **[ERROR]** {instances}")
                await add_error_reaction(ctx)

        except Exception as e:
            logger.error(f"Error in rds_list command: {str(e)}")
            await ctx.send(f"❌ **[ERROR]** Lỗi khi lấy danh sách RDS: {str(e)}")
            await add_error_reaction(ctx)

    @commands.command(name="rds-metrics")
    async def rds_metrics(self, ctx, server_name: str = None):
        """Get RDS instance metrics
        Example: !rds-metrics [server_name]"""
        try:
            if server_name:
                # Show metrics for specific instance
                if server_name not in RDS_INSTANCES:
                    await ctx.send(f"❌ **[ERROR]** RDS instance `{server_name}` không tồn tại")
                    await add_error_reaction(ctx)
                    return

                instance_id = RDS_INSTANCES[server_name]
                success, metrics = await self.rds_manager.get_instance_metrics(instance_id)
                
                if success:
                    embed = await self.create_rds_metrics_embed(server_name, instance_id, metrics)
                    await ctx.send(embed=embed)
                    await add_success_reaction(ctx)
                else:
                    await ctx.send(f"❌ **[ERROR]** {metrics}")
                    await add_error_reaction(ctx)
            else:
                # Show metrics for all instances
                main_embed = discord.Embed(
                    title="📊 **[RDS METRICS]** - All Instances",
                    color=discord.Color.blue()
                )

                for friendly_name, instance_id in RDS_INSTANCES.items():
                    success, metrics = await self.rds_manager.get_instance_metrics(instance_id)
                    if success:
                        # Add status
                        status_success, status = await self.rds_manager.get_instance_status(instance_id)
                        if status_success:
                            status_emoji = "🟢" if status == 'available' else "🔴" if status == 'stopped' else "🟡"
                            metrics_text = (
                                f"{status_emoji} Status: {status}\n"
                                f"CPU Usage: {metrics.get('CPU', 'N/A')}\n"
                                f"Memory Free: {metrics.get('Memory', 'N/A')}\n"
                                f"Storage Free: {metrics.get('Storage', 'N/A')}\n"
                                f"IOPS: {metrics.get('IOPS', 'N/A')}\n"
                                f"Connections: {metrics.get('Connections', 'N/A')}"
                            )
                            main_embed.add_field(
                                name=f"📊 {friendly_name}",
                                value=f"```yaml\n{metrics_text}\n```",
                                inline=False
                            )

                current_time = datetime.now().strftime("%H:%M:%S")
                main_embed.set_footer(text=f"System Time: {current_time} | Timezone: {self.ec2_manager.timezone}")
                
                await ctx.send(embed=main_embed)
                await add_success_reaction(ctx)

        except Exception as e:
            logger.error(f"Error in rds_metrics command: {str(e)}")
            await ctx.send(f"❌ **[ERROR]** Lỗi khi lấy metrics: {str(e)}")
            await add_error_reaction(ctx)

    async def create_rds_metrics_embed(self, server_name: str, instance_id: str, metrics: dict) -> discord.Embed:
        """Create embed for RDS metrics"""
        embed = discord.Embed(
            title=f"📊 **[RDS METRICS]** - {server_name}",
            color=discord.Color.blue()
        )

        # Add status
        status_success, status = await self.rds_manager.get_instance_status(instance_id)
        if status_success:
            status_emoji = "🟢" if status == 'available' else "🔴" if status == 'stopped' else "🟡"
            embed.add_field(
                name="Status",
                value=f"{status_emoji} {status}",
                inline=False
            )

        # Add metrics
        metrics_text = (
            f"```yaml\n"
            f"CPU Usage: {metrics.get('CPU', 'N/A')}\n"
            f"Memory Free: {metrics.get('Memory', 'N/A')}\n"
            f"Storage Free: {metrics.get('Storage', 'N/A')}\n"
            f"IOPS: {metrics.get('IOPS', 'N/A')}\n"
            f"Connections: {metrics.get('Connections', 'N/A')}\n"
            f"```"
        )
        embed.add_field(
            name="Performance Metrics",
            value=metrics_text,
            inline=False
        )

        current_time = datetime.now().strftime("%H:%M:%S")
        embed.set_footer(text=f"System Time: {current_time} | Timezone: {self.ec2_manager.timezone}")

        return embed

    @commands.command(name="schedule")
    async def schedule(self, ctx, server_name: str, start_time: str = None, stop_time: str = None):
        """Set schedule for EC2 instance
        Example: !schedule snowee-bastion 09:00 18:00"""
        try:
            logger.info(f"Schedule command received - User: {ctx.author} | Server: {server_name} | Start: {start_time} | Stop: {stop_time}")
            
            # Get instance ID
            instance_id = await self.get_instance_id(server_name)
            logger.info(f"Looking up instance ID for {server_name} - Result: {instance_id}")
            
            if not instance_id:
                logger.warning(f"Instance not found: {server_name} | Available instances: {list(EC2_INSTANCES.keys())}")
                await ctx.send(f"❌ **[ERROR]** Instance `{server_name}` không tồn tại")
                await add_error_reaction(ctx)
                return

            success, message = await self.ec2_manager.add_schedule(instance_id, server_name, start_time, stop_time)
            logger.info(f"Add schedule result - Success: {success} | Message: {message}")
            
            if success:
                schedule = await self.ec2_manager.get_schedule(instance_id)
                logger.info(f"Retrieved schedule for {server_name}: {schedule}")
                
                embed = discord.Embed(
                    title="⏰ **[SCHEDULE CREATED]**",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="Configuration",
                    value=f"```yaml\nInstance:\n"
                         f"  Name: {server_name}\n"
                         f"  Start: {schedule['start_time']}\n"
                         f"  Stop: {schedule['stop_time']}\n"
                         f"  Timezone: {schedule['timezone']}\n"
                         f"  Expires: {schedule['expires_at']}\n```",
                    inline=False
                )
                embed.set_footer(text="Schedule đã được thiết lập thành công")
                await ctx.send(embed=embed)
                await add_success_reaction(ctx)
            else:
                await ctx.send(f"❌ **[ERROR]** {message}")
                await add_error_reaction(ctx)

        except Exception as e:
            logger.error(f"Error in schedule command: {str(e)}", exc_info=True)
            await ctx.send(f"❌ **[ERROR]** Lỗi khi thiết lập schedule: {str(e)}")
            await add_error_reaction(ctx)

    @commands.command(name="unschedule")
    async def unschedule(self, ctx, server_name: str):
        """Remove schedule for EC2 instance
        Example: !unschedule snowee-bastion"""
        try:
            instance_id = await self.get_instance_id(server_name)
            if not instance_id:
                await ctx.send(f"❌ **[ERROR]** Instance `{server_name}` không tồn tại")
                await add_error_reaction(ctx)
                return

            success, message = await self.ec2_manager.remove_schedule(instance_id)
            
            if success:
                embed = discord.Embed(
                    title="⏰ **[SCHEDULE REMOVED]**",
                    description=f"```yaml\nInstance: {server_name}\nStatus: Schedule removed\n```",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
                await add_success_reaction(ctx)
            else:
                await ctx.send(f"❌ **[ERROR]** {message}")
                await add_error_reaction(ctx)

        except Exception as e:
            logger.error(f"Error in unschedule command: {str(e)}")
            await ctx.send(f"❌ **[ERROR]** Lỗi khi xóa schedule: {str(e)}")
            await add_error_reaction(ctx)

    @commands.command(name="schedules")
    async def list_schedules(self, ctx):
        """List all EC2 instance schedules
        Example: !schedules"""
        try:
            schedules = await self.ec2_manager.list_schedules()
            
            if not schedules:
                await ctx.send("📝 **[INFO]** Không có schedule nào được thiết lập")
                return

            embed = discord.Embed(
                title="⏰ **[SCHEDULE LIST]**",
                description="Danh sách các schedule đã thiết lập",
                color=discord.Color.blue()
            )

            for instance_id, schedule in schedules.items():
                embed.add_field(
                    name=f"📋 {schedule['server_name']}",
                    value=f"```yaml\nStart: {schedule['start_time']}\nStop: {schedule['stop_time']}\nTimezone: {schedule['timezone']}\n```",
                    inline=True
                )

            current_time = datetime.now().strftime("%H:%M:%S")
            embed.set_footer(text=f"System Time: {current_time} | Timezone: {self.ec2_manager.timezone}")
            
            await ctx.send(embed=embed)
            await add_success_reaction(ctx)

        except Exception as e:
            logger.error(f"Error in list_schedules command: {str(e)}")
            await ctx.send(f"❌ **[ERROR]** Lỗi khi lấy danh sách schedule: {str(e)}")
            await add_error_reaction(ctx)

    async def get_instance_id(self, server_name: str) -> str:
        """Get instance ID from server name"""
        if server_name not in EC2_INSTANCES:
            return None
        return EC2_INSTANCES[server_name]

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle messages that mention the bot"""
        if message.author == self.bot.user:
            return
            
        if self.bot.user.mentioned_in(message):
            try:
                # Get appropriate response based on message content
                response = await self.process_message(message)
                
                # Create embed with DevOps styling
                embed = discord.Embed(
                    title="🔧 AWS Infrastructure Management",
                    description=response,
                    color=discord.Color.blue()
                )
                
                # Add system status footer
                current_time = datetime.now().strftime("%H:%M:%S")
                embed.set_footer(text=f"System Time: {current_time} | Status: Operational")
                
                await message.channel.send(embed=embed)
                await message.add_reaction('✅')
                
            except Exception as e:
                logger.error(f"Error processing mention: {str(e)}")
                error_msg = (
                    "❌ **System Alert**\n"
                    "```yaml\nError:\n"
                    "  Type: Request Processing\n"
                    "  Action: Check logs\n"
                    "  Status: Failed\n```"
                )
                await message.channel.send(error_msg)
                await message.add_reaction('❌')

    async def process_message(self, message):
        """Process message content and return appropriate response"""
        content_lower = message.content.lower()
        
        if "rds" in content_lower:
            # Get instances by control level
            full_control = [name for name, level in RDS_CONTROL_LEVELS.items() if level == 1]
            metrics_only = [name for name, level in RDS_CONTROL_LEVELS.items() if level == 2]
            
            return (
                "🗄️ **[RDS MANAGEMENT]**\n"
                "```yaml\nCommands:\n"
                "  !rds-list:\n"
                "    usage: !rds-list\n"
                "    action: List all RDS instances\n"
                "  !rds-metrics:\n"
                "    usage: !rds-metrics [instance]\n"
                "    action: Get instance metrics\n"
                "  !rds-start:\n"
                "    usage: !rds-start <instance>\n"
                "    action: Start RDS instance\n"
                "    note: Only for full control instances\n"
                "  !rds-stop:\n"
                "    usage: !rds-stop <instance>\n"
                "    action: Stop RDS instance\n"
                "    note: Only for full control instances\n"
                "  !rds-status:\n"
                "    usage: !rds-status <instance>\n"
                "    action: Get instance status\n\n"
                "Available Instances:\n"
                "  Full Control (Start/Stop/Metrics):\n"
                f"    {', '.join(full_control) if full_control else 'None'}\n"
                "  Metrics Only:\n"
                f"    {', '.join(metrics_only) if metrics_only else 'None'}\n```"
            )
        
        # Default response
        return (
            "🛠️ **[INFRASTRUCTURE MANAGEMENT]**\n"
            "```yaml\nAvailable Services:\n"
            "  Instance Management:\n"
            "    - Provisioning\n"
            "    - Configuration\n"
            "    - Lifecycle control\n"
            "  Monitoring:\n"
            "    - Performance metrics\n"
            "    - Health checks\n"
            "    - Alert management\n"
            "  Resource Optimization:\n"
            "    - Cost analysis\n"
            "    - Usage tracking\n"
            "    - Scaling operations\n\n"
            "Documentation: Use !help\n"
            "Support: Tag @bot with queries```"
        )

class EKSCommands(commands.Cog):
    """Commands for managing EKS clusters"""
    
    def __init__(self, bot):
        self.bot = bot
        self.eks_manager = EKSManager()
        self.notification_minutes = int(os.getenv('EKS_PERF_NOTIFICATION_MINUTES', '5'))
        # Maximum running time in hours before sending warning
        self.max_running_hours = float(os.getenv('EKS_PERF_MAX_HOURS', '4'))
        self.notified_nodegroups = set()
        
        # Performance nodegroup configuration from environment variables
        self.perf_config = {
            'instance_types': [os.getenv('EKS_PERF_INSTANCE_TYPE', 'c6i.2xlarge')],
            'min_size': int(os.getenv('EKS_PERF_MIN_SIZE', '1')),
            'max_size': int(os.getenv('EKS_PERF_MAX_SIZE', '3')),
            'desired_size': int(os.getenv('EKS_PERF_DESIRED_SIZE', '2')),
            'disk_size': int(os.getenv('EKS_PERF_DISK_SIZE', '100'))
        }
        
        # Start monitoring task
        self.monitor_performance_nodes.start()
        
        self.command_help = {
            "setup-performance-for-dev": {
                "description": "Tạo nodegroup cho môi trường dev với cấu hình tối ưu hiệu năng",
                "usage": "!eks setup-performance-for-dev [--spot]",
                "example": "!eks setup-performance-for-dev --spot"
            },
            "delete-performance": {
                "description": "Xóa performance nodegroup",
                "usage": "!eks delete-performance",
                "example": "!eks delete-performance"
            },
            "list": {
                "description": "Liệt kê tất cả nodegroups và tags của chúng",
                "usage": "!eks list",
                "example": "!eks list"
            },
            "scalable": {
                "description": "Liệt kê các nodegroup có thể scale với thông tin chi tiết",
                "usage": "!eks scalable",
                "example": "!eks scalable"
            },
            "create": {
                "description": "Tạo nodegroup mới với cấu hình và tags tùy chọn. Hỗ trợ ON_DEMAND hoặc SPOT instances.",
                "usage": "!eks create <tên_nodegroup> <instance_type> <desired_size> <min_size> <max_size> [ON_DEMAND|SPOT] [key1=value1 key2=value2 ...]",
                "example": "!eks create prod-nodes t3.medium 3 2 5 SPOT environment=prod team=backend"
            },
            "delete": {
                "description": "Xóa một nodegroup",
                "usage": "!eks delete <tên_nodegroup>",
                "example": "!eks delete staging-nodes"
            },
            "tag": {
                "description": "Thêm tags cho một nodegroup",
                "usage": "!eks tag <tên_nodegroup> <key1=value1> [key2=value2 ...]",
                "example": "!eks tag nodegroup-1 environment=prod team=backend"
            },
            "untag": {
                "description": "Xóa tags khỏi một nodegroup",
                "usage": "!eks untag <tên_nodegroup> <key1> [key2 ...]",
                "example": "!eks untag nodegroup-1 environment team"
            },
            "scale": {
                "description": "Thay đổi kích thước của một nodegroup",
                "usage": "!eks scale <tên_nodegroup> <số_lượng_node>",
                "example": "!eks scale nodegroup-1 5"
            },
            "status": {
                "description": "Xem trạng thái chi tiết của một nodegroup",
                "usage": "!eks status <tên_nodegroup>",
                "example": "!eks status nodegroup-1"
            },
        }

    @tasks.loop(minutes=5)  # Check every 5 minutes
    async def monitor_performance_nodes(self):
        """Monitor performance nodegroups and send notifications if they run too long"""
        try:
            # Get all nodegroups
            nodegroups = self.eks_manager.eks_client.list_nodegroups(
                clusterName=self.eks_manager.cluster_name
            )['nodegroups']
            
            for nodegroup in nodegroups:
                if self.eks_manager.is_performance_nodegroup(nodegroup):
                    running_time = self.eks_manager.get_nodegroup_running_time(nodegroup)
                    
                    if running_time and running_time >= self.max_running_hours and nodegroup not in self.notified_nodegroups:
                        # Send notification to all channels the bot is in
                        for guild in self.bot.guilds:
                            for channel in guild.text_channels:
                                try:
                                    embed = discord.Embed(
                                        title="⚠️ Performance Nodegroup Warning",
                                        description=f"Performance nodegroup `{nodegroup}` has been running for {running_time:.1f} hours.\nConsider deleting it if no longer needed using `!eks delete-performance`",
                                        color=discord.Color.yellow()
                                    )
                                    await channel.send(embed=embed)
                                except Exception as e:
                                    logger.error(f"Error sending notification to channel {channel.name}: {str(e)}")
                        
                        # Add to notified set to prevent spam
                        self.notified_nodegroups.add(nodegroup)
                    
                    # Remove from notified set if nodegroup is deleted or running time is reset
                    elif running_time and running_time < self.max_running_hours:
                        self.notified_nodegroups.discard(nodegroup)
                        
        except Exception as e:
            logger.error(f"Error in performance nodegroup monitor: {str(e)}")

    @monitor_performance_nodes.before_loop
    async def before_monitor(self):
        """Wait until the bot is ready before starting the monitoring task"""
        await self.bot.wait_until_ready()

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.monitor_performance_nodes.cancel()

    @commands.group(name='eks')
    async def eks(self, ctx):
        """Quản lý EKS clusters"""
        if ctx.invoked_subcommand is None:
            await ctx.send("❌ Invalid EKS command. Use !help eks for usage info.")

    @eks.command(name='setup-performance-for-dev')
    async def setup_performance_for_dev(self, ctx):
        """Tạo nodegroup cho môi trường dev với cấu hình tối ưu hiệu năng"""
        logger.info(f"Command: setup-performance-for-dev | User: {ctx.author} | Channel: {ctx.channel}")
        
        # Log current configuration
        logger.info("Current Performance Config:")
        logger.info(f"Instance Type: {self.perf_config['instance_types'][0]}")
        logger.info(f"Min Size: {self.perf_config['min_size']}")
        logger.info(f"Max Size: {self.perf_config['max_size']}")
        logger.info(f"Desired Size: {self.perf_config['desired_size']}")
        logger.info(f"Disk Size: {self.perf_config['disk_size']}")
        
        try:
            # Get cost comparison
            logger.info("Getting cost comparison for nodegroup")
            success, cost_message = await self.eks_manager.compare_nodegroup_costs(
                self.perf_config['instance_types'][0],
                self.perf_config['desired_size']
            )
            if not success:
                logger.error(f"Failed to get cost comparison: {cost_message}")
                await add_error_reaction(ctx.message)
                await ctx.send(cost_message)
                return

            logger.info("Creating instance type selection message")
            # Create embed with options
            embed = create_embed(
                title="Performance Nodegroup Options",
                description=(
                    f"Cấu hình Performance Nodegroup:\n"
                    f"• Instance type: `{self.perf_config['instance_types'][0]}`\n"
                    f"• Min nodes: `{self.perf_config['min_size']}`\n"
                    f"• Max nodes: `{self.perf_config['max_size']}`\n"
                    f"• Desired nodes: `{self.perf_config['desired_size']}`\n"
                    f"• Disk size: `{self.perf_config['disk_size']}GB`\n\n"
                    "**ON_DEMAND**\n"
                    "✓ Luôn sẵn sàng, không bị interrupt\n"
                    "✓ Phù hợp cho workload quan trọng\n"
                    "× Giá cao hơn\n\n"
                    "**SPOT**\n"
                    "✓ Tiết kiệm chi phí đáng kể\n"
                    "✓ Phù hợp cho dev/test environment\n"
                    "× Có thể bị interrupt với thông báo 2 phút\n\n"
                    f"{cost_message}\n\n"
                    "Chọn loại instance bên dưới:"
                )
            )

            # Create buttons for instance type selection
            view = discord.ui.View()
            on_demand_button = discord.ui.Button(label="ON_DEMAND", style=discord.ButtonStyle.primary)
            spot_button = discord.ui.Button(label="SPOT", style=discord.ButtonStyle.success)

            async def button_callback(interaction, capacity_type):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("Bạn không có quyền sử dụng nút này!", ephemeral=True)
                    return

                # Disable all buttons
                for item in view.children:
                    item.disabled = True
                await msg.edit(view=view)

                await interaction.response.send_message(f"Bạn đã chọn {capacity_type}. Xác nhận lựa chọn của bạn:")

                # Create confirmation view
                confirm_view = discord.ui.View()
                confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.success)
                cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger)

                async def confirm_callback(confirm_interaction):
                    if confirm_interaction.user != ctx.author:
                        await confirm_interaction.response.send_message("Bạn không có quyền sử dụng nút này!", ephemeral=True)
                        return

                    # Disable confirmation buttons
                    for item in confirm_view.children:
                        item.disabled = True
                    await confirm_msg.edit(view=confirm_view)

                    await confirm_interaction.response.defer()

                    # Send initial status message
                    status_msg = await ctx.send("⏳ Đang bắt đầu tạo performance nodegroup...")

                    # Create nodegroup with selected capacity type
                    config = self.perf_config.copy()
                    config['capacity_type'] = capacity_type
                    config['channel_id'] = ctx.channel.id

                    # Map AWS nodegroup states to user-friendly messages
                    status_messages = {
                        'CREATING': "⏳ Đang tạo...",
                        'UPDATING': "⏳ Đang cập nhật...",
                        'ACTIVE': "✅ Hoạt động",
                        'CREATE_FAILED': "❌ Tạo thất bại",
                    }

                    # Start creation with progress monitoring
                    success, message = await self.eks_manager.create_performance_nodegroup(
                        'perf-dev',
                        config,
                        status_callback=lambda status: status_msg.edit(
                            content=status_messages.get(status, f"⏳ Đang xử lý... (Trạng thái: {status})")
                        ) if status else None
                    )
                    
                    if success:
                        await add_success_reaction(ctx.message)
                        await status_msg.edit(content=message)
                        
                        # Create performance test pod
                        pod_msg = await ctx.send("⏳ Đang tạo performance test pod...")
                        pod_success, pod_message = await self.eks_manager.create_performance_test_pod()
                        
                        if pod_success:
                            await pod_msg.edit(content="✅ Đã tạo performance test pod thành công!")
                            logger.info("Successfully created performance test pod")
                            
                            # Send summary message
                            summary = (
                                "✅ Performance Environment đã sẵn sàng!\n\n"
                                f"• Nodegroup: `perf-dev`\n"
                                f"• Instance Type: `{config['instance_types'][0]}`\n"
                                f"• Capacity Type: `{capacity_type}`\n"
                                f"• Nodes: `{config['desired_size']}`\n\n"
                                "🔔 Bạn sẽ nhận được thông báo trước khi nodegroup bị xóa."
                            )
                            await ctx.send(summary)
                        else:
                            await pod_msg.edit(content=f"❌ Lỗi khi tạo performance test pod: {pod_message}")
                            logger.error(f"Failed to create performance test pod: {pod_message}")
                    else:
                        await add_error_reaction(ctx.message)
                        await status_msg.edit(content=f"❌ {message}")

                async def cancel_callback(cancel_interaction):
                    if cancel_interaction.user != ctx.author:
                        await cancel_interaction.response.send_message("Bạn không có quyền sử dụng nút này!", ephemeral=True)
                        return

                    # Disable confirmation buttons
                    for item in confirm_view.children:
                        item.disabled = True
                    await confirm_msg.edit(view=confirm_view)

                    await cancel_interaction.response.defer()
                    await ctx.send("❌ Đã hủy tạo nodegroup.")

                confirm_button.callback = confirm_callback
                cancel_button.callback = cancel_callback
                confirm_view.add_item(confirm_button)
                confirm_view.add_item(cancel_button)

                confirm_msg = await ctx.send("Bạn có chắc chắn muốn tiếp tục?", view=confirm_view)

            on_demand_button.callback = lambda i: button_callback(i, "ON_DEMAND")
            spot_button.callback = lambda i: button_callback(i, "SPOT")

            view.add_item(on_demand_button)
            view.add_item(spot_button)

            msg = await ctx.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error in setup_performance_for_dev: {str(e)}", exc_info=True)
            await add_error_reaction(ctx.message)
            await ctx.send(f"❌ Lỗi không mong muốn: {str(e)}")

    @eks.command(name='delete-performance')
    async def delete_performance(self, ctx):
        """Xóa performance nodegroup"""
        logger.info(f"[DELETE] ====== Delete Performance Command Started ======")
        logger.info(f"[DELETE] User: {ctx.author}")
        logger.info(f"[DELETE] Channel: {ctx.channel}")
        logger.info(f"[DELETE] Guild: {ctx.guild}")
        
        try:
            # Get nodegroup name from config or use default
            nodegroup_name = os.getenv('EKS_PERF_NODEGROUP_NAME', 'perf-dev')
            logger.info(f"[DELETE] Target nodegroup: {nodegroup_name}")
            
            # Create confirmation buttons
            view = discord.ui.View()
            confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.danger)
            cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)

            async def confirm_callback(interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("Bạn không có quyền sử dụng nút này!", ephemeral=True)
                    return

                logger.info(f"[DELETE] User {interaction.user} confirmed deletion")
                # Disable all buttons
                for item in view.children:
                    item.disabled = True
                await msg.edit(view=view)

                await interaction.response.defer()
                
                # Check if nodegroup exists first
                logger.info("[DELETE] Checking nodegroup status...")
                status = await self.eks_manager.get_nodegroup_status(nodegroup_name)
                logger.info(f"[DELETE] Initial nodegroup status: {status}")
                
                if status is None:
                    logger.warning(f"[DELETE] Nodegroup '{nodegroup_name}' not found")
                    await ctx.send(f"❌ Không tìm thấy nodegroup '{nodegroup_name}'")
                    return
            
                # Get initial nodegroup info for summary
                try:
                    logger.info("[DELETE] Getting nodegroup info for summary...")
                    nodegroup_info = await self.eks_manager.get_nodegroup_info(nodegroup_name)
                    if nodegroup_info:
                        logger.info(f"[DELETE] Nodegroup info: {json.dumps(nodegroup_info, default=str)}")
                        summary = (
                            f"ℹ️ Thông tin nodegroup sẽ xóa:\n"
                            f"• Tên: `{nodegroup_name}`\n"
                            f"• Instance Types: `{', '.join(nodegroup_info.get('instanceTypes', ['N/A']))}`\n"
                            f"• Số lượng nodes: `{nodegroup_info.get('scalingConfig', {}).get('desiredSize', 'N/A')}`\n"
                            f"• Trạng thái: `{nodegroup_info.get('status', 'N/A')}`\n"
                            f"• Tạo lúc: `{nodegroup_info.get('createdAt', 'N/A')}`"
                        )
                        await ctx.send(summary)
                except Exception as e:
                    logger.error(f"[DELETE] Error getting nodegroup info: {str(e)}")
            
                # Start deletion process
                status_msg = await ctx.send(f"⏳ Bắt đầu xóa nodegroup '{nodegroup_name}'...")
                success, message = await self.eks_manager.delete_performance_nodegroup(nodegroup_name)
                
                if not success:
                    logger.error(f"[DELETE] Failed to initiate deletion: {message}")
                    await status_msg.edit(content=message)
                    return
                
                # Monitor deletion progress with timeout
                start_time = time.time()
                max_wait_time = 20 * 60  # 20 minutes timeout
                last_status = None
                check_interval = 10  # Check every 10 seconds
                
                logger.info(f"[DELETE] Starting deletion monitoring loop...")
                while True:
                    current_time = time.time()
                    if current_time - start_time > max_wait_time:
                        error_msg = f"❌ Quá thời gian chờ xóa nodegroup (20 phút)"
                        logger.error(f"[DELETE] Timeout reached")
                        await status_msg.edit(content=error_msg)
                        return
                    
                    # Get current status
                    current_status = await self.eks_manager.get_nodegroup_status(nodegroup_name)
                    logger.info(f"[DELETE] Current status: {current_status}")
                    
                    # Status changed
                    if current_status != last_status:
                        logger.info(f"[DELETE] Status changed: {last_status} -> {current_status}")
                        last_status = current_status
                        # Update Discord message with new status
                        status_text = status_messages.get(current_status, f"⚠️ {current_status}")
                        await status_msg.edit(content=f"{status_text} - Nodegroup: {nodegroup_name}")
                    
                    if current_status is None:
                        # Nodegroup no longer exists - deletion successful
                        logger.info("[DELETE] Nodegroup no longer exists - deletion successful")
                        await status_msg.edit(content=f"✅ Đã xóa thành công nodegroup '{nodegroup_name}'")
                        return
                    
                    elif current_status == 'DELETE_FAILED':
                        error_msg = f"❌ Xóa nodegroup '{nodegroup_name}' thất bại"
                        logger.error(f"[DELETE] Deletion failed")
                        await status_msg.edit(content=error_msg)
                        return
                    
                    elif current_status == 'DEGRADED':
                        error_msg = f"⚠️ Nodegroup '{nodegroup_name}' trong trạng thái không ổn định"
                        logger.warning(f"[DELETE] Nodegroup in degraded state")
                        await status_msg.edit(content=error_msg)
                        return
                    
                    # Sleep before next check
                    logger.info(f"[DELETE] Waiting {check_interval} seconds before next status check...")
                    await asyncio.sleep(check_interval)

            async def cancel_callback(cancel_interaction):
                if cancel_interaction.user != ctx.author:
                    await cancel_interaction.response.send_message("Bạn không có quyền sử dụng nút này!", ephemeral=True)
                    return

                # Disable confirmation buttons
                for item in view.children:
                    item.disabled = True
                await msg.edit(view=view)

                await cancel_interaction.response.defer()
                await ctx.send("❌ Đã hủy xóa nodegroup.")

            confirm_button.callback = confirm_callback
            cancel_button.callback = cancel_callback
            view.add_item(confirm_button)
            view.add_item(cancel_button)

            msg = await ctx.send(
                f"⚠️ Bạn có chắc chắn muốn xóa nodegroup '{nodegroup_name}' không?\n"
                "❗ Lưu ý: Quá trình này không thể hoàn tác sau khi bắt đầu.",
                view=view
            )
            logger.info("[DELETE] Sent deletion confirmation dialog")

        except Exception as e:
            logger.error(f"[DELETE] Unexpected error in delete_performance command:")
            logger.error(f"[DELETE] {str(e)}")
            logger.error("[DELETE] Stack trace:", exc_info=True)
            await ctx.send(f"❌ Lỗi không mong muốn: {str(e)}")
            await add_error_reaction(ctx.message)

    @eks.command(name='help')
    async def help(self, ctx):
        """Show help for EKS commands"""
        embed = create_embed(
            title="EKS Commands Help",
            description="Các lệnh quản lý EKS clusters",
            fields=[{
                'name': command,
                'value': f"{info['description']}\nUsage: {info['usage']}\nExample: {info['example']}"
            } for command, info in self.command_help.items()]
        )
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(EC2Commands(bot))
    bot.add_cog(EKSCommands(bot))