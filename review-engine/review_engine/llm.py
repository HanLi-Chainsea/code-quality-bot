import os, re, json, urllib.request
from dataclasses import dataclass

@dataclass
class Client:
    base_url: str
    api_key: str
    model: str = "reviewer"

    @classmethod
    def from_env(cls) -> "Client":
        return cls(
            base_url=os.environ.get("REVIEWER_BASE_URL", "http://127.0.0.1:4000/v1"),
            api_key=os.environ.get("REVIEWER_API_KEY", ""),
            model=os.environ.get("REVIEWER_MODEL", "reviewer"),
        )

    def complete(self, system_and_user: str, max_tokens: int = 2000) -> str:
        """Single-shot completion. Returns clean `content`. Our LiteLLM `reviewer` alias
        separates reasoning server-side (reasoning_split); we ALSO strip any inline
        <think>...</think> here so a non-LiteLLM backend can't leak reasoning into parsing."""
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": system_and_user}],
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(self.base_url.rstrip("/") + "/chat/completions",
            data=body, headers={"Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
        content = d["choices"][0]["message"].get("content") or ""
        return re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
