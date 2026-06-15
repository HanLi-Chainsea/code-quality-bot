from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class ChangedFunction:
    qualified_name: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    language: str = ""
    is_test: bool = False
    risk_score: float = 0.0

    @classmethod
    def from_crg(cls, d: dict) -> "ChangedFunction":
        return cls(
            qualified_name=d["qualified_name"], name=d["name"],
            file_path=d["file_path"], line_start=d["line_start"], line_end=d["line_end"],
            language=d.get("language", ""), is_test=d.get("is_test", False),
            risk_score=d.get("risk_score", 0.0),
        )

@dataclass
class Node:
    qualified_name: str
    kind: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str = ""

@dataclass
class Finding:
    severity: str            # "blocker" | "major" | "minor"
    file: str
    line: int
    title: str
    rationale: str
    premise: str = ""        # what off-diff fact the finding assumes (verified in stage 2)
    confirmed: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class Bundle:
    changed_files: dict = field(default_factory=dict)   # path -> full source
    related: dict = field(default_factory=dict)         # qualified_name -> source snippet
    diff: str = ""
    est_tokens: int = 0
