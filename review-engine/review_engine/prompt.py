from .models import Bundle

SYSTEM_FIND = (
    "你是一位資深工程師在 review 一個 merge request。用繁體中文。\n"
    "只報你願意『因此擋下這個 merge』的問題：真 bug、資料正確性、安全、並行/競態、"
    "錯誤處理缺失、會破壞 caller 的 breaking change。\n"
    "不要報純風格、命名、格式、個人偏好。寧缺勿濫。\n"
    "每條發現必須標 severity（blocker / major / minor），並寫出 premise："
    "這條發現假設了哪些『diff 以外』的事實（例如某 caller 怎麼呼叫、某值不可能為 null）。\n"
    "只輸出 JSON：{\"findings\":[{\"severity\":..,\"file\":..,\"line\":..,\"title\":..,"
    "\"rationale\":..,\"premise\":..}]}。沒有問題就回 {\"findings\":[]}。"
)

def _render_context(b: Bundle) -> str:
    parts = ["## 改動 diff", b.diff, "\n## 改動檔（全文）"]
    for path, src in b.changed_files.items():
        parts.append(f"### {path}\n{src}")
    if b.related:
        parts.append("\n## 相關上下游（caller/callee，用於判斷影響）")
        for qn, snip in b.related.items():
            parts.append(snip)
    return "\n".join(parts)

def find_prompt(b: Bundle) -> str:
    return f"{SYSTEM_FIND}\n\n{_render_context(b)}"

def verify_prompt(finding_title: str, premise: str, source: str) -> str:
    return (
        "你在對一條 code review 發現做『落地反證』。用繁體中文，只輸出 JSON。\n"
        f"發現：{finding_title}\n"
        f"它依賴的前提：{premise}\n"
        "下面是這條前提實際對應的源碼。請順著前提去讀真實源碼，判斷前提是否成立。\n"
        "如果源碼顯示『其實已經處理了／情況不是它講的那樣』，前提不成立 → confirmed=false。\n"
        "不確定就 confirmed=false（寧可放過）。\n"
        f"\n## 實際源碼\n{source}\n\n"
        "輸出：{\"confirmed\": true|false, \"reason\": \"...\"}"
    )
