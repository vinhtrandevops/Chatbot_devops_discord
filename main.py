import asyncio
import discord
from discord.ext import commands
from src.config import TOKEN
from src.bot.commands import EC2Commands, EKSCommands
from src.bot.events import BotEvents
from src.utils.logger import get_logger
from src.aws.eks import EKSManager

logger = get_logger(__name__)

class NodegroupButton(discord.ui.View):
    def __init__(self, action_type="create", timeout=180):
        super().__init__(timeout=timeout)
        self.value = None
        self.action_type = action_type

    @discord.ui.button(label='✅ Xác nhận', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label='❌ Hủy', style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self):
        self.value = False
        self.stop()

async def main():
    # Setup intents
    intents = discord.Intents.default()
    intents.message_content = True
    
    # Initialize bot
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    # Remove default help command
    bot.remove_command('help')
    
    @bot.command(name='eks-list')
    async def list_nodes(ctx):
        """List all nodegroups and their tags"""
        eks_manager = EKSManager()
        success, nodegroups = await eks_manager.list_nodegroups()
        
        if success:
            embed = discord.Embed(
                title="EKS Nodegroups Status",
                description=f"🔷 Cluster: **{eks_manager.cluster_name}**",
                color=discord.Color.blue()
            )
            
            for ng in nodegroups:
                field_value = f"Status: {ng['status']}\n"
                field_value += f"Size: {ng['size']} nodes (min: {ng['min_size']}, max: {ng['max_size']})\n"
                if ng['tags']:
                    field_value += "**Tags:**\n"
                    for key, value in ng['tags'].items():
                        field_value += f"• {key}: {value}\n"
                
                embed.add_field(
                    name=f"📦 {ng['name']}", 
                    value=field_value,
                    inline=False
                )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Error listing nodegroups: {nodegroups}")

    @bot.command(name='eks-tag')
    async def add_tags(ctx, nodegroup: str = None, *, tags: str = None):
        """Add tags to a nodegroup. Format: !eks-tag nodegroup-name key1=value1 key2=value2"""
        if nodegroup is None:
            await ctx.send("❌ Thiếu tên nodegroup. Sử dụng: `!eks-tag <tên_nodegroup> <key1=value1> [key2=value2 ...]`")
            return
        if tags is None:
            await ctx.send("❌ Thiếu tags. Sử dụng: `!eks-tag <tên_nodegroup> <key1=value1> [key2=value2 ...]`")
            return

        try:
            # Parse tags from space-separated key=value pairs
            tag_dict = dict(t.split('=') for t in tags.split())
            
            eks_manager = EKSManager()
            success, result = await eks_manager.add_nodegroup_tags(nodegroup, tag_dict)
            
            if success:
                embed = discord.Embed(
                    title="✅ Tags Added Successfully",
                    description=f"Added tags to nodegroup: {nodegroup} in cluster: {eks_manager.cluster_name}",
                    color=discord.Color.green()
                )
                for key, value in tag_dict.items():
                    embed.add_field(name=key, value=value)
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ Error adding tags: {result}")
        except ValueError:
            await ctx.send("❌ Invalid tag format. Use: `!eks-tag nodegroup-name key1=value1 key2=value2`")

    @bot.command(name='eks-untag')
    async def remove_tags(ctx, nodegroup: str = None, *, tags: str = None):
        """Remove tags from a nodegroup. Format: !eks-untag nodegroup-name tag1 tag2"""
        if nodegroup is None:
            await ctx.send("❌ Thiếu tên nodegroup. Sử dụng: `!eks-untag <tên_nodegroup> <key1> [key2 ...]`")
            return
        if tags is None:
            await ctx.send("❌ Thiếu tags. Sử dụng: `!eks-untag <tên_nodegroup> <key1> [key2 ...]`")
            return

        tag_keys = tags.split()
        eks_manager = EKSManager()
        success, result = await eks_manager.remove_nodegroup_tags(nodegroup, tag_keys)
        
        if success:
            embed = discord.Embed(
                title="✅ Tags Removed Successfully",
                description=f"Removed tags from nodegroup: {nodegroup} in cluster: {eks_manager.cluster_name}\nRemoved tags: {', '.join(tag_keys)}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Error removing tags: {result}")

    @bot.command(name='eks-scale')
    async def scale(ctx, nodegroup: str = None, size: int = None):
        """Scale a nodegroup to the specified size. Format: !eks-scale nodegroup-name desired_size"""
        if nodegroup is None:
            await ctx.send("❌ Thiếu tên nodegroup. Sử dụng: `!eks-scale <tên_nodegroup> <số_lượng_node>`")
            return
        if size is None:
            await ctx.send("❌ Thiếu số lượng node. Sử dụng: `!eks-scale <tên_nodegroup> <số_lượng_node>`")
            return

        eks_manager = EKSManager()
        success, result = await eks_manager.scale_nodegroup(nodegroup, size)
        
        if success:
            embed = discord.Embed(
                title="✅ Scaling Nodegroup",
                description=f"Scaled nodegroup: {nodegroup} in cluster: {eks_manager.cluster_name}",
                color=discord.Color.green()
            )
            embed.add_field(name="Previous Size", value=str(result['previous_size']))
            embed.add_field(name="New Size", value=str(result['new_size']))
            embed.add_field(name="Allowed Range", value=f"{result['min_size']}-{result['max_size']}")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Error scaling nodegroup: {result}")

    @bot.command(name='eks-status')
    async def nodegroup_status(ctx, nodegroup: str = None):
        """Get detailed status of a nodegroup. Format: !eks-status nodegroup-name"""
        if nodegroup is None:
            await ctx.send("❌ Thiếu tên nodegroup. Sử dụng: `!eks-status <tên_nodegroup>`")
            return

        eks_manager = EKSManager()
        success, result = await eks_manager.get_nodegroup_status(nodegroup)
        
        if success:
            embed = discord.Embed(
                title=f"Nodegroup Status: {result['nodegroup_name']} in cluster: {eks_manager.cluster_name}",
                description=f"Cluster: {result['cluster_name']}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Status", value=result['status'])
            embed.add_field(name="Current Size", value=str(result['current_size']))
            embed.add_field(name="Size Range", value=f"{result['min_size']}-{result['max_size']}")
            
            if result['tags']:
                tags_text = "\n".join([f"• {k}: {v}" for k, v in result['tags'].items()])
                embed.add_field(name="Tags", value=tags_text, inline=False)
                
            if result['health']:
                health_text = "\n".join([f"• {k}: {v}" for k, v in result['health'].items()])
                embed.add_field(name="Health", value=health_text, inline=False)
                
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Error getting status: {result}")

    @bot.command(name='eks-scalable')
    async def list_scalable(ctx):
        """List all nodegroups that can be scaled with their current sizes and limits"""
        eks_manager = EKSManager()
        success, nodegroups = await eks_manager.list_scalable_nodegroups()
        
        if success:
            embed = discord.Embed(
                title="🔄 Scalable EKS Nodegroups in cluster: " + eks_manager.cluster_name,
                description="Danh sách các nodegroup có thể scale",
                color=discord.Color.blue()
            )
            
            for ng in nodegroups:
                field_value = (
                    f"🔹 Current Size: **{ng['current_size']}** nodes\n"
                    f"🔸 Size Range: **{ng['min_size']}-{ng['max_size']}** nodes\n"
                    f"💻 Instance Types: {', '.join(ng['instance_types'])}\n"
                    f"📊 Status: {ng['status']}\n\n"
                    f"Scale command:\n"
                    f"`!eks-scale {ng['name']} <số_lượng_node>`"
                )
                
                embed.add_field(
                    name=f"📦 {ng['name']}", 
                    value=field_value,
                    inline=False
                )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Error listing scalable nodegroups: {nodegroups}")

    @bot.command(name='eks-create')
    async def create_nodegroup(ctx, nodegroup: str = None, instance_type: str = None, desired_size: int = None, 
                             min_size: int = None, max_size: int = None, capacity_type: str = 'ON_DEMAND', *, tags: str = None):
        """Create a new nodegroup with specified configuration and tags"""
        if any(param is None for param in [nodegroup, instance_type, desired_size, min_size, max_size]):
            example = (
                "❌ Thiếu thông tin. Sử dụng format:\n"
                "`!eks-create <tên_nodegroup> <instance_type> <desired_size> <min_size> <max_size> [ON_DEMAND|SPOT] [key1=value1 key2=value2 ...]`\n\n"
                "Ví dụ:\n"
                "`!eks-create prod-nodes t3.medium 3 2 5 ON_DEMAND environment=prod team=backend` (On-Demand Instances)\n"
                "`!eks-create spot-nodes t3.small 2 1 3 SPOT team=dev` (Spot Instances)\n"
                "`!eks-create basic-nodes t3.small 2 1 3` (Mặc định: On-Demand)"
            )
            await ctx.send(example)
            return

        # Validate capacity type
        capacity_type = capacity_type.upper()
        if capacity_type not in ['ON_DEMAND', 'SPOT']:
            await ctx.send("❌ Capacity type phải là 'ON_DEMAND' hoặc 'SPOT'")
            return

        # Parse tags if provided
        tag_dict = {}
        if tags:
            try:
                tag_dict = dict(t.split('=') for t in tags.split())
            except ValueError:
                await ctx.send("❌ Invalid tag format. Use: `key1=value1 key2=value2`")
                return

        eks_manager = EKSManager()
        
        # Get cost estimate
        success, cost_info = await eks_manager.estimate_nodegroup_cost(instance_type, int(desired_size), capacity_type)
        if not success:
            await ctx.send(f"❌ Error estimating cost: {cost_info}")
            return
            
        # Create confirmation message with cost estimate
        embed = discord.Embed(
            title="💰 Nodegroup Cost Estimate",
            description=(
                f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                f"📦 Nodegroup: **{nodegroup}**\n"
                f"💻 Instance Type: {instance_type}\n"
                f"🔢 Size: {desired_size} nodes ({min_size}-{max_size})\n"
                f"💰 Capacity Type: **{capacity_type}**\n\n"
                f"💵 Chi phí ước tính:\n"
                f"• Mỗi node/giờ: ${cost_info['hourly_per_node']}\n"
                f"• Tổng/tháng: **${cost_info['monthly_total']}**\n\n"
                "⚠️ Bạn có chắc chắn muốn tạo nodegroup này?"
            ),
            color=discord.Color.blue()
        )
        
        # Add confirmation buttons
        view = NodegroupButton(action_type="create")
        msg = await ctx.send(embed=embed, view=view)
        
        # Wait for button press
        await view.wait()
        
        if view.value is None:
            await msg.edit(content="❌ Hết thời gian xác nhận. Vui lòng thử lại.", view=None)
            return
        elif not view.value:
            await msg.edit(content="❌ Đã hủy tạo nodegroup.", view=None)
            return
            
        # User confirmed, proceed with creation
        await msg.edit(
            embed=discord.Embed(
                title="🔄 Creating Nodegroup",
                description=(
                    f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                    f"📦 Nodegroup: **{nodegroup}**\n"
                    f"💻 Instance Type: {instance_type}\n"
                    f"🔢 Size: {desired_size} nodes ({min_size}-{max_size})\n"
                    f"💰 Capacity Type: **{capacity_type}**\n"
                    "⌛ Đang tạo nodegroup... (có thể mất 10-15 phút)"
                ),
                color=discord.Color.gold()
            ),
            view=None
        )
        
        success, result = await eks_manager.create_nodegroup(
            nodegroup, instance_type, int(desired_size), 
            int(min_size), int(max_size), tag_dict, capacity_type
        )
        
        if success:
            # Wait for nodegroup creation
            success, status = await eks_manager.wait_for_nodegroup_status(nodegroup, 'ACTIVE')
            if success:
                await msg.edit(
                    embed=discord.Embed(
                        title="✅ Nodegroup Created Successfully",
                        description=(
                            f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                            f"📦 Nodegroup: **{nodegroup}**\n"
                            f"💻 Instance Type: {instance_type}\n"
                            f"🔢 Size: {desired_size} nodes ({min_size}-{max_size})\n"
                            f"💰 Capacity Type: **{capacity_type}**\n"
                            f"💵 Chi phí ước tính/tháng: **${cost_info['monthly_total']}**\n\n"
                            "✨ Nodegroup đã được tạo thành công!"
                        ),
                        color=discord.Color.green()
                    )
                )
            else:
                await msg.edit(
                    embed=discord.Embed(
                        title="❌ Creation Failed",
                        description=(
                            f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                            f"📦 Nodegroup: **{nodegroup}**\n"
                            f"💰 Capacity Type: **{capacity_type}**\n"
                            f"❌ Error: {status}"
                        ),
                        color=discord.Color.red()
                    )
                )
        else:
            await msg.edit(
                embed=discord.Embed(
                    title="❌ Creation Failed",
                    description=(
                        f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                        f"📦 Nodegroup: **{nodegroup}**\n"
                        f"💰 Capacity Type: **{capacity_type}**\n"
                        f"❌ Error: {result}"
                    ),
                    color=discord.Color.red()
                )
            )

    @bot.command(name='eks-delete')
    async def delete_nodegroup(ctx, nodegroup: str = None):
        """Delete a nodegroup"""
        if nodegroup is None:
            await ctx.send("❌ Thiếu tên nodegroup. Sử dụng: `!eks-delete <tên_nodegroup>`")
            return

        eks_manager = EKSManager()
        
        # Get nodegroup info for confirmation
        try:
            response = eks_manager.eks_client.describe_nodegroup(
                clusterName=eks_manager.cluster_name,
                nodegroupName=nodegroup
            )
            ng_info = response['nodegroup']
        except Exception as e:
            await ctx.send(f"❌ Error getting nodegroup info: {str(e)}")
            return
            
        # Create confirmation message
        embed = discord.Embed(
            title="⚠️ Delete Nodegroup Confirmation",
            description=(
                f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                f"📦 Nodegroup: **{nodegroup}**\n"
                f"💻 Instance Type: {ng_info['instanceTypes'][0]}\n"
                f"🔢 Current Size: {ng_info['scalingConfig']['desiredSize']} nodes\n"
                f"💰 Capacity Type: **{ng_info['capacityType']}**\n\n"
                "⚠️ **CẢNH BÁO**: Hành động này không thể hoàn tác!\n"
                "Bạn có chắc chắn muốn xóa nodegroup này?"
            ),
            color=discord.Color.red()
        )
        
        # Add confirmation buttons
        view = NodegroupButton(action_type="delete")
        msg = await ctx.send(embed=embed, view=view)
        
        # Wait for button press
        await view.wait()
        
        if view.value is None:
            await msg.edit(content="❌ Hết thời gian xác nhận. Vui lòng thử lại.", view=None)
            return
        elif not view.value:
            await msg.edit(content="❌ Đã hủy xóa nodegroup.", view=None)
            return
            
        # User confirmed, proceed with deletion
        await msg.edit(
            embed=discord.Embed(
                title="🔄 Deleting Nodegroup",
                description=(
                    f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                    f"📦 Nodegroup: **{nodegroup}**\n"
                    "⌛ Đang xóa nodegroup... (có thể mất 5-10 phút)"
                ),
                color=discord.Color.gold()
            ),
            view=None
        )
        
        success, result = await eks_manager.delete_nodegroup(nodegroup)
        
        if success:
            await msg.edit(
                embed=discord.Embed(
                    title="✅ Nodegroup Deleted Successfully",
                    description=(
                        f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                        f"📦 Nodegroup: **{nodegroup}**\n"
                        "✨ Nodegroup đã được xóa thành công!"
                    ),
                    color=discord.Color.green()
                )
            )
        else:
            await msg.edit(
                embed=discord.Embed(
                    title="❌ Deletion Failed",
                    description=(
                        f"🔷 Cluster: **{eks_manager.cluster_name}**\n"
                        f"📦 Nodegroup: **{nodegroup}**\n"
                        f"❌ Error: {result}"
                    ),
                    color=discord.Color.red()
                )
            )

    try:
        # Add cogs
        await bot.add_cog(EC2Commands(bot))
        await bot.add_cog(EKSCommands(bot))
        await bot.add_cog(BotEvents(bot))
        
        # Run bot
        logger.info("Starting bot...")
        await bot.start(TOKEN)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())