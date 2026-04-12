from typing import List, Optional

class LLMService:
    @staticmethod
    async def generate_response(
        system_prompt: str,
        user_message: str,
        history: Optional[List[dict]] = None
    ) -> str:
        """AI chat is disabled — no API keys configured."""
        return (
            "AI chat is currently unavailable. "
            "Please use the specific tools (Invoice Upload, Bank Statement Upload, etc.) "
            "for document processing — they work without AI using rule-based parsers."
        )
