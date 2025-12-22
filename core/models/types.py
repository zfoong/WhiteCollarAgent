from enum import Enum

class InterfaceType(str, Enum):
    LLM = "llm"
    VLM = "vlm"
    EMBEDDING = "embedding"
