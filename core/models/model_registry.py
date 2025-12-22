from .types import InterfaceType

MODEL_REGISTRY = {
    "openai": {
        InterfaceType.LLM: "gpt-4o",
        InterfaceType.VLM: "gpt-4o-2024-08-06",
        InterfaceType.EMBEDDING: "text-embedding-3-small",
    },
    "gemini": {
        InterfaceType.LLM: "gemini-2.5-flash",
        InterfaceType.VLM: "gemini-2.5-pro",
        InterfaceType.EMBEDDING: "text-embedding-004",
    },
    "byteplus": {
        InterfaceType.LLM: "kimi-k2-250711",
        InterfaceType.VLM: "seed-1-6-flash-250715",
        InterfaceType.EMBEDDING: "skylark-embedding-vision-250615",
    },
    "remote": {
        InterfaceType.LLM: "llama3",
        InterfaceType.VLM: "llava-v1.6",
        InterfaceType.EMBEDDING: "nomic-embed-text",
    },
}
