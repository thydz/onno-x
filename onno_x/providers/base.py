from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple
from onno_x.config import ModelSpec


class BaseProvider(ABC):
    def __init__(self, spec: ModelSpec):
        self.spec = spec

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Send messages and available tools.
        If on_chunk is provided, stream tokens in real-time.
        Returns (assistant_reply_text, list_of_tool_calls).
        Each tool call is: {"id": str, "name": str, "arguments": dict}
        """
        pass
