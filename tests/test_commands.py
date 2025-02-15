import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import discord
from discord.ext import commands
from src.bot.commands import EC2Commands

class TestEC2Commands(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = EC2Commands(self.bot)
        
    @patch('src.aws.ec2.EC2Manager')
    async def test_list_servers_command(self, mock_ec2_manager):
        # Setup mocks
        ctx = AsyncMock()
        mock_instance = mock_ec2_manager.return_value
        mock_instance.get_instance_state.return_value = ('running', None)
        
        # Test
        await self.cog.list_servers(ctx)
        
        # Assert
        ctx.send.assert_called_once()
        self.assertIsInstance(ctx.send.call_args[0][0], discord.Embed)
        
    @patch('src.aws.ec2.EC2Manager')
    async def test_start_command_success(self, mock_ec2_manager):
        # Setup mocks
        ctx = AsyncMock()
        mock_instance = mock_ec2_manager.return_value
        mock_instance.get_instance_state.return_value = ('stopped', None)
        mock_instance.start_instance.return_value = True
        
        # Test
        await self.cog.start(ctx, 'test-server')
        
        # Assert
        ctx.send.assert_called_with('✅ Đang khởi động server test-server...')
        
    @patch('src.aws.ec2.EC2Manager')
    async def test_start_command_already_running(self, mock_ec2_manager):
        # Setup mocks
        ctx = AsyncMock()
        mock_instance = mock_ec2_manager.return_value
        mock_instance.get_instance_state.return_value = ('running', None)
        
        # Test
        await self.cog.start(ctx, 'test-server')
        
        # Assert
        ctx.send.assert_called_with('⚠️ Server test-server đã đang chạy!')
        
    @patch('src.aws.ec2.EC2Manager')
    async def test_help_command(self, mock_ec2_manager):
        # Setup mocks
        ctx = AsyncMock()
        
        # Test
        await self.cog.help_command(ctx)
        
        # Assert
        ctx.send.assert_called_once()
        self.assertIsInstance(ctx.send.call_args[0][0], discord.Embed)

if __name__ == '__main__':
    unittest.main()