from typing import List, Optional
from app.services.ai_client import call_ai_chat

class LLMService:
    @staticmethod
    async def generate_response(
        system_prompt: str,
        user_message: str,
        history: Optional[List[dict]] = None
    ) -> str:
        """Generate a response using AI (Claude → Gemini fallback)."""
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            return await call_ai_chat(
                system_prompt=system_prompt,
                messages=messages,
                temperature=0.2,
                max_tokens=1000,
            )
        except Exception as e:
            return f"[ERROR]: Failed to reach AI service: {str(e)}"
