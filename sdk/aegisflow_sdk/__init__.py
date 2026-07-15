"""AegisFlow SDK — Python client with circuit breaker, retry, and fail-open.

Usage:
    from aegisflow_sdk import AegisFlow

    client = AegisFlow(
        api_key="agf_xxxxxxxx.yyyyyyyy",
        base_url="https://api.aegisflow.tech",
    )

    # OpenAI-compatible interface
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
    )

    # Streaming
    for chunk in client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
        stream=True,
    ):
        print(chunk)

    # Fail-open mode: bypasses gateway if unavailable
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
        fail_open=True,
    )
"""

from .client import AegisFlow
from .types import ChatCompletion, ChatCompletionChunk

__version__ = "0.1.0"
__all__ = ["AegisFlow", "ChatCompletion", "ChatCompletionChunk"]