"""
OpenAI-Compatible LLM Provider Client
Generic client for any OpenAI-compatible API (OpenAI, DeepSeek, Claude via gateway, etc.)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("ai.providers.openai_compat")


class Message(BaseModel):
    """Chat message"""
    role: Literal["system", "user", "assistant"] = "user"
    content: str


class ChatRequest(BaseModel):
    """OpenAI chat completion request"""
    model: str
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int | None = None
    response_format: dict[str, str] | None = None


class ChatResponse(BaseModel):
    """OpenAI chat completion response"""
    id: str = ""
    model: str = ""
    choices: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    
    @property
    def content(self) -> str:
        """Extract message content from response"""
        if self.choices and len(self.choices) > 0:
            return self.choices[0].get("message", {}).get("content", "")
        return ""
    
    def parse_json(self) -> dict[str, Any]:
        """Parse JSON content (for structured outputs)"""
        content = self.content
        # Strip markdown code fences if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        return json.loads(content)


class LLMProviderError(Exception):
    """Base error for LLM provider issues"""
    pass


class TimeoutError(LLMProviderError):
    """Request timeout"""
    pass


class APIError(LLMProviderError):
    """API returned error status"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API error {status_code}: {message}")


class MalformedResponseError(LLMProviderError):
    """Response could not be parsed"""
    pass


class OpenAICompatClient:
    """
    Generic OpenAI-compatible LLM client
    
    Works with:
    - OpenAI
    - DeepSeek
    - Claude (via OpenAI-compatible gateway like openagentic.id)
    - Any provider that implements OpenAI's /chat/completions endpoint
    
    Usage:
        client = OpenAICompatClient(
            base_url="https://openagentic.id/api/v1",
            api_key="sk-..."
        )
        
        response = await client.chat(
            model="deepseek-v4-pro",
            messages=[
                Message(role="system", content="You are a helpful assistant."),
                Message(role="user", content="Hello!")
            ]
        )
        
        print(response.content)
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 15,
        max_retries: int = 2
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout=float(timeout)),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def close(self):
        """Close HTTP client"""
        await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def chat(
        self,
        model: str,
        messages: list[Message] | list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        retry_count: int = 0
    ) -> ChatResponse:
        """
        Call /chat/completions endpoint
        
        Args:
            model: Model name (e.g., "deepseek-v4-pro", "claude-sonnet-4.6")
            messages: List of Message objects or dicts
            temperature: Sampling temperature (0-1)
            max_tokens: Max tokens to generate
            response_format: e.g., {"type": "json_object"} for structured output
            retry_count: Internal retry counter
        
        Returns:
            ChatResponse with content and metadata
        
        Raises:
            TimeoutError: Request timed out
            APIError: API returned error status
            MalformedResponseError: Response could not be parsed
        """
        # Normalize messages
        if messages and isinstance(messages[0], dict):
            messages = [Message(**m) for m in messages]
        
        request = ChatRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format
        )
        
        logger.debug(f"Calling {model} with {len(messages)} messages")
        
        try:
            response = await self._client.post(
                "/chat/completions",
                json=request.model_dump(exclude_none=True)
            )
            
            # Handle error status codes
            if response.status_code >= 400:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", {}).get("message", response.text)
                except Exception:
                    pass
                
                # Retry on 5xx or rate limit
                if response.status_code >= 500 or response.status_code == 429:
                    if retry_count < self.max_retries:
                        wait_time = 2 ** retry_count  # exponential backoff
                        logger.warning(f"{model} returned {response.status_code}, retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        return await self.chat(
                            model=model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            response_format=response_format,
                            retry_count=retry_count + 1
                        )
                
                raise APIError(response.status_code, error_detail)
            
            # Parse response
            try:
                data = response.json()
                chat_response = ChatResponse(**data)
                
                tokens = chat_response.usage.get("total_tokens", 0)
                logger.info(f"{model} responded ({tokens} tokens)")
                
                return chat_response
            
            except Exception as e:
                raise MalformedResponseError(f"Failed to parse response: {e}")
        
        except httpx.TimeoutException as e:
            if retry_count < self.max_retries:
                logger.warning(f"{model} timed out, retrying...")
                return await self.chat(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    retry_count=retry_count + 1
                )
            raise TimeoutError(f"Request to {model} timed out after {self.timeout}s")
        
        except httpx.RequestError as e:
            raise LLMProviderError(f"Network error calling {model}: {e}")
    
    def message_hash(self, messages: list[Message] | list[dict]) -> str:
        """Generate hash of messages for caching"""
        content = json.dumps([m.model_dump() if isinstance(m, Message) else m for m in messages], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
