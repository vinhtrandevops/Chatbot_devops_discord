import discord
from discord.ext import commands
from ..utils.logger import get_logger

logger = get_logger(__name__)

class BotEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Event khi bot sẵn sàng"""
        logger.info(f'Bot logged in as {self.bot.user}')
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="🖥️ EC2 Instances | !help"
            ),
            status=discord.Status.online
        )

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Event xử lý lỗi commands"""
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("❌ Không tìm thấy lệnh. Sử dụng !help để xem các lệnh có sẵn.")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Bạn không có quyền sử dụng lệnh này.")
        else:
            logger.error(f"Error in command {ctx.command}: {error}")
            await ctx.send(f"❌ Đã xảy ra lỗi: {str(error)}")

    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Event khi có command được gọi"""
        logger.info(
            f"Command executed: {ctx.command} | "
            f"User: {ctx.author} | "
            f"Channel: {ctx.channel} | "
            f"Guild: {ctx.guild}"
        )