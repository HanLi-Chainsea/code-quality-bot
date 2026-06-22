import os, re, json, urllib.request
from dataclasses import dataclass

@dataclass
class Client:
    base_url: str
    api_key: str
    model: str = "reviewer"
    timeout: int = 300        # strong reasoning models (e.g. MiniMax-M3) are slow on real prompts
    extra_body: dict = None   # backend-specific knobs merged into every request body

    @classmethod
    def from_env(cls) -> "Client":
        # REVIEWER_EXTRA_BODY (JSON) lets a direct (non-LiteLLM) backend get extra request fields
        # without code changes — e.g. a local MLX/Qwen server needs
        # {"chat_template_kwargs":{"enable_thinking":false},"response_format":{"type":"json_object"}}
        # to skip its thinking preamble AND force valid (escaped) JSON. Empty/invalid -> ignored.
        try:
            extra = json.loads(os.environ.get("REVIEWER_EXTRA_BODY", "") or "{}")
        except json.JSONDecodeError:
            extra = {}
        return cls(
            base_url=os.environ.get("REVIEWER_BASE_URL", "http://127.0.0.1:4000/v1"),
            api_key=os.environ.get("REVIEWER_API_KEY", ""),
            model=os.environ.get("REVIEWER_MODEL", "reviewer"),
            extra_body=extra,
        )

    def complete(self, system_and_user: str, max_tokens: int = 2000) -> str:
        """Single-shot completion. Returns clean `content`. Our LiteLLM `reviewer` alias
        separates reasoning server-side (reasoning_split); we ALSO strip any inline
        <think>...</think> here so a non-LiteLLM backend can't leak reasoning into parsing."""
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": system_and_user}],
            "max_tokens": max_tokens,
            **(self.extra_body or {}),
        }).encode()
        req = urllib.request.Request(self.base_url.rstrip("/") + "/chat/completions",
            data=body, headers={"Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            d = json.load(r)
        content = d["choices"][0]["message"].get("content") or ""
        return re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
