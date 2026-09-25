"""Build the provider chain from the environment (default: mock -> mock-fallback)."""
from .config import FALLBACK_PROVIDER, PRIMARY_PROVIDER
from .external_providers import AnthropicProvider, OpenAIProvider
from .mock_provider import MockAIProvider, MockFallbackProvider

PROVIDERS = {
    "mock": MockAIProvider,
    "mock-primary": MockAIProvider,
    "mock-fallback": MockFallbackProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def build_chain(primary=None, fallback=None):
    primary = primary or PRIMARY_PROVIDER
    fallback = fallback or FALLBACK_PROVIDER
    chain = [PROVIDERS[primary]()]
    if fallback and fallback != primary:
        chain.append(PROVIDERS[fallback]())
    return chain
