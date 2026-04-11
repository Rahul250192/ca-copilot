"""
Centralized AI Client — Multi-Provider with Automatic Fallback
─────────────────────────────────────────────────────────────────
Priority: Claude (Anthropic) → Gemini (Google, free tier)

If Claude credits run out, automatically falls back to Gemini.
All AI calls in the app should go through this module.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Track which provider is active (avoids retrying Claude every call after it fails)
_provider_state = {"claude_exhausted": False}


def reset_provider_state():
    """Reset fallback state (e.g., after adding new Claude credits)."""
    _provider_state["claude_exhausted"] = False
    logger.info("AI provider state reset — will try Claude first again")


# ═══════════════════════════════════════════════════════
#  CLAUDE (Primary)
# ═══════════════════════════════════════════════════════

async def _call_claude(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 4000,
    temperature: float = 0.1,
) -> str:
    """Call Anthropic Claude API. Raises on credit exhaustion."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.content[0].text if response.content else ""
    if not text or not text.strip():
        raise ValueError("Claude returned empty response")
    return text


async def _call_claude_chat(
    system_prompt: str,
    messages: List[dict],
    max_tokens: int = 1000,
    temperature: float = 0.2,
) -> str:
    """Call Claude with conversation history."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        system=system_prompt,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.content[0].text


# ═══════════════════════════════════════════════════════
#  GEMINI (Free Fallback)
# ═══════════════════════════════════════════════════════

async def _call_gemini(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 4000,
    temperature: float = 0.1,
) -> str:
    """Call Google Gemini API (free tier) using new google-genai SDK."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GOOGLE_AI_API_KEY)

    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    text = response.text if response and response.text else ""
    if not text or not text.strip():
        logger.warning(f"Gemini returned empty response. Candidates: {getattr(response, 'candidates', 'N/A')}")
        raise ValueError("Gemini returned empty response (possible safety filter)")
    return text


async def _call_gemini_chat(
    system_prompt: str,
    messages: List[dict],
    max_tokens: int = 1000,
    temperature: float = 0.2,
) -> str:
    """Call Gemini with conversation history using new google-genai SDK."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GOOGLE_AI_API_KEY)

    # Convert messages to Gemini format
    gemini_contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        gemini_contents.append(types.Content(
            role=role,
            parts=[types.Part(text=msg["content"])],
        ))

    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=gemini_contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text


# ═══════════════════════════════════════════════════════
#  PUBLIC API — Auto-Fallback
# ═══════════════════════════════════════════════════════

def _is_credit_exhausted_error(e: Exception) -> bool:
    """Check if the error is a Claude credit-exhaustion error."""
    error_str = str(e).lower()
    return any(kw in error_str for kw in [
        "credit balance", "insufficient", "too low",
        "purchase credits", "billing", "quota",
    ])


async def call_ai(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 4000,
    temperature: float = 0.1,
) -> str:
    """
    Call AI with automatic fallback: Claude → Gemini.
    Returns the raw text response.
    """
    # Try Claude first (unless known to be exhausted)
    if settings.ANTHROPIC_API_KEY and not _provider_state["claude_exhausted"]:
        try:
            logger.info(f"AI call → trying Claude (input: {len(user_content)} chars)")
            result = await _call_claude(system_prompt, user_content, max_tokens, temperature)
            logger.info(f"AI call completed via Claude ({len(result)} chars)")
            return result
        except Exception as e:
            if _is_credit_exhausted_error(e):
                _provider_state["claude_exhausted"] = True
                logger.warning("⚠️ Claude credits exhausted — switching to Gemini fallback")
            else:
                logger.warning(f"Claude failed (non-credit error): {e} — trying Gemini")
                # Fall through to Gemini instead of raising

    # Fallback to Gemini
    if settings.GOOGLE_AI_API_KEY:
        try:
            logger.info(f"AI call → trying Gemini fallback (input: {len(user_content)} chars)")
            result = await _call_gemini(system_prompt, user_content, max_tokens, temperature)
            logger.info(f"AI call completed via Gemini ({len(result)} chars)")
            return result
        except Exception as e:
            logger.error(f"Gemini fallback also failed: {e}")
            raise

    raise ValueError(
        "No AI provider available. "
        "Claude credits exhausted and GOOGLE_AI_API_KEY not configured. "
        "Add Gemini key at: https://aistudio.google.com/apikey"
    )


async def call_ai_json(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 4000,
    temperature: float = 0.1,
) -> dict:
    """
    Call AI and parse JSON response. Handles markdown fences and repairs truncated JSON.
    """
    # Add JSON instruction to system prompt
    enhanced_prompt = system_prompt + "\n\nReturn ONLY valid JSON. No markdown fences, no extra text."

    raw = await call_ai(enhanced_prompt, user_content, max_tokens, temperature)

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to repair: remove trailing commas
        fixed = re.sub(r',\s*([\]}])', r'\1', raw)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed ({len(raw)} chars): {e}")
            raise ValueError(f"AI returned invalid JSON: {e}")


async def call_ai_chat(
    system_prompt: str,
    messages: List[dict],
    max_tokens: int = 1000,
    temperature: float = 0.2,
) -> str:
    """
    Chat-style AI call with history. Auto-fallback: Claude → Gemini.
    """
    if settings.ANTHROPIC_API_KEY and not _provider_state["claude_exhausted"]:
        try:
            return await _call_claude_chat(system_prompt, messages, max_tokens, temperature)
        except Exception as e:
            if _is_credit_exhausted_error(e):
                _provider_state["claude_exhausted"] = True
                logger.warning("⚠️ Claude credits exhausted — switching to Gemini for chat")
            else:
                raise

    if settings.GOOGLE_AI_API_KEY:
        return await _call_gemini_chat(system_prompt, messages, max_tokens, temperature)

    raise ValueError("No AI provider available.")


def get_active_provider() -> str:
    """Get the name of the currently active AI provider."""
    if settings.ANTHROPIC_API_KEY and not _provider_state["claude_exhausted"]:
        return "claude"
    if settings.GOOGLE_AI_API_KEY:
        return "gemini"
    return "none"
