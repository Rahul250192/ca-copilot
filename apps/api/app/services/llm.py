import openai
from typing import List, Optional
from app.core.config import settings

class LLMService:
    @staticmethod
    async def generate_response(
        system_prompt: str,
        user_message: str,
        history: Optional[List[dict]] = None
    ) -> str:
        """
        Generate a response using OpenAI's wrapper.
        """
        if not settings.OPENAI_API_KEY:
            return "[WARNING: AI KEY MISSING] I am unable to connect to the real AI brain right now. Please configure your OPENAI_API_KEY."

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = await client.chat.completions.create(
                model="gpt-4o", # Using a high-quality model
                messages=messages,
                temperature=0.2,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[ERROR]: Failed to reach AI service: {str(e)}"
