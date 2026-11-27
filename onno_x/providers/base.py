from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple
from onno_x.config import ModelSpec


class BaseProvider(ABC):
    def __init__(self, spec: ModelSpec):
        self.spec = spec
        # Set by chat() when the model stopped because it ran out of output
        # tokens. Without this the agent cannot tell a finished answer from a
        # truncated one, commits the fragment, and the build dies mid-file.
        self.last_truncated = False

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_chunk: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[Any] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Send messages and available tools.
        If on_chunk is provided, stream tokens in real-time.
        Returns (assistant_reply_text, list_of_tool_calls).
        Each tool call is: {"id": str, "name": str, "arguments": dict}
        """
        pass
