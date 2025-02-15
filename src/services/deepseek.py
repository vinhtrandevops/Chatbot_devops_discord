from abc import ABC, abstractmethod
import aiohttp
import json
from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_TEMPERATURE
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

class AIService(ABC):
    """Base class for AI services"""
    
    @abstractmethod
    async def ask(self, question: str, context: str = "") -> str:
        """Send a question to the AI service
        
        Args:
            question (str): The question to ask
            context (str, optional): Additional context. Defaults to "".
            
        Returns:
            str: The AI's response
        """
        pass

class DeepSeekService(AIService):
    """Service để tương tác với DeepSeek API"""
    
    def __init__(self):
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY is not set in environment variables")
        
        self.api_key = DEEPSEEK_API_KEY
        self.model = DEEPSEEK_MODEL
        self.base_url = "https://api.deepseek.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def ask(self, question: str, context: str = "") -> str:
        """Gửi câu hỏi tới DeepSeek API

        Args:
            question (str): Câu hỏi của người dùng
            context (str, optional): Context bổ sung. Defaults to "".

        Returns:
            str: Câu trả lời từ AI

        Raises:
            Exception: Nếu có lỗi khi gọi API
        """
        try:
            system_prompt = """You are a friendly and helpful AI assistant in a Discord server. Your responses should be:
            1. Clear and concise, but with a touch of personality
            2. Well-formatted using Discord markdown (**, *, `, etc.)
            3. Include relevant emojis where appropriate
            4. Break down complex explanations into bullet points or numbered lists
            5. Use code blocks for code examples
            6. Be encouraging and supportive
            
            Remember to:
            - Use appropriate technical terms but explain them when needed
            - Be conversational but professional
            - Show enthusiasm when users learn or accomplish something
            - Offer follow-up suggestions when relevant"""
            
            if context:
                system_prompt += f"\nContext: {context}"

            logger.info(f"Sending request to DeepSeek API - Model: {self.model}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": question}
                        ],
                        "max_tokens": DEEPSEEK_MAX_TOKENS,
                        "temperature": DEEPSEEK_TEMPERATURE,
                        "stream": False
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content']
                    else:
                        error_text = await response.text()
                        error_data = json.loads(error_text)
                        
                        # Handle insufficient balance error specifically
                        if response.status == 402 or (error_data.get('error', {}).get('message') == 'Insufficient Balance'):
                            logger.error("DeepSeek API: Insufficient Balance error")
                            raise Exception("DeepSeek API account has insufficient balance. Please contact the administrator to recharge the account.")
                        
                        logger.error(f"DeepSeek API error: {error_text}")
                        raise Exception(f"DeepSeek API returned status {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error when calling DeepSeek API: {str(e)}")
            raise Exception("Failed to connect to DeepSeek API. Please try again later.") from e
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse DeepSeek API response: {str(e)}")
            raise Exception("Received invalid response from DeepSeek API. Please try again later.") from e
        
        except Exception as e:
            if "insufficient balance" in str(e).lower():
                raise e
            logger.error(f"Unexpected error in DeepSeek service: {str(e)}")
            raise Exception("An unexpected error occurred. Please try again later.") from e

    async def get_ec2_help(self, topic: str) -> str:
        """Lấy thông tin trợ giúp về EC2 từ DeepSeek"""
        context = """
        Topics can include:
        - EC2 instance types and their use cases
        - EC2 pricing models
        - EC2 security best practices
        - EC2 networking and VPC
        - EC2 storage options
        - EC2 monitoring and maintenance
        """
        
        question = f"Can you explain about {topic} in EC2? Please provide detailed information and best practices."
        return await self.ask(question, context)

    async def troubleshoot_ec2(self, problem: str) -> str:
        """Giúp troubleshoot vấn đề EC2"""
        context = """
        Common EC2 issues include:
        - Connection problems
        - Performance issues
        - Storage problems
        - Network connectivity
        - Security group configurations
        """
        
        question = f"How to troubleshoot this EC2 issue: {problem}? Please provide step-by-step guidance."
        return await self.ask(question, context)