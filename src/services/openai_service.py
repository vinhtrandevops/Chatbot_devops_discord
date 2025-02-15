from .deepseek import AIService
import aiohttp
import json
from ..config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_MAX_TOKENS,
    OPENAI_TEMPERATURE
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

class OpenAIService(AIService):
    """Service để tương tác với OpenAI API"""
    
    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables")
        
        self.api_key = OPENAI_API_KEY
        self.model = OPENAI_MODEL
        self.base_url = "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def ask(self, question: str, context: str = "") -> str:
        """Gửi câu hỏi tới OpenAI API

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

            logger.info(f"Sending request to OpenAI API - Model: {self.model}")
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
                        "max_tokens": OPENAI_MAX_TOKENS,
                        "temperature": OPENAI_TEMPERATURE
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content']
                    else:
                        error_text = await response.text()
                        error_data = json.loads(error_text)
                        
                        logger.error(f"OpenAI API error: {error_text}")
                        raise Exception(f"OpenAI API error: {error_data.get('error', {}).get('message', 'Unknown error')}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error when calling OpenAI API: {str(e)}")
            raise Exception("Failed to connect to OpenAI API. Please try again later.") from e
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI API response: {str(e)}")
            raise Exception("Received invalid response from OpenAI API. Please try again later.") from e
        
        except Exception as e:
            logger.error(f"Unexpected error in OpenAI service: {str(e)}")
            raise Exception("An unexpected error occurred. Please try again later.") from e

    async def get_ec2_help(self, topic: str) -> str:
        """Get help about a specific EC2 topic

        Args:
            topic (str): The EC2 topic to get help about

        Returns:
            str: Detailed help information about the topic
        """
        context = "You are an AWS EC2 expert. Provide detailed, technical, but easy to understand information about the requested EC2 topic."
        question = f"Can you explain about {topic} in AWS EC2? Include examples and best practices where relevant."
        return await self.ask(question, context)

    async def troubleshoot_ec2(self, problem: str) -> str:
        """Get troubleshooting help for an EC2 problem

        Args:
            problem (str): The EC2 problem to troubleshoot

        Returns:
            str: Troubleshooting steps and solutions
        """
        context = "You are an AWS EC2 expert. Provide step-by-step troubleshooting guidance for EC2 issues."
        question = f"How do I troubleshoot this EC2 issue: {problem}? Please provide step-by-step instructions."
        return await self.ask(question, context)