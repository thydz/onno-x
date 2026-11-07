from onno_x.config import ModelSpec
from onno_x.providers.base import BaseProvider
from onno_x.providers.openai import OpenAIProvider
from onno_x.providers.anthropic import AnthropicProvider
from onno_x.providers.ollama import OllamaProvider


def get_provider(spec: ModelSpec) -> BaseProvider:
    provider = spec.provider.lower()
    if provider in ("openai", "vllm", "lmstudio", "groq"):
        return OpenAIProvider(spec)
    elif provider == "anthropic":
        return AnthropicProvider(spec)
    elif provider == "ollama":
        return OllamaProvider(spec)
    else:
        # Fallback to OpenAI-compatible
        return OpenAIProvider(spec)
