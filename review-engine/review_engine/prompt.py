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
    parts = []
    if b.notes:
        parts.append("## 注意（context 取捨，可能未含完整檔案）\n"
                     + "\n".join(f"- {n}" for n in b.notes))
    parts += ["## 改動 diff", b.diff, "\n## 改動檔內容（大改動時為高風險函式片段）"]
    for path, src in b.changed_files.items():
        parts.append(f"### {path}\n{src}")
    if b.related:
        parts.append("\n## 相關上下游（caller/callee，用於判斷影響）")
        for qn, snip in b.related.items():
            parts.append(snip)
    return "\n".join(parts)

# Diverse review lenses. Running find once per lens (then union+dedup) surfaces deeper,
# senior-level issues that a single general pass misses — concurrency, breaking changes,
# behaviour regressions — and stabilises recall against the model's run-to-run variance.
FIND_LENSES = [
    "",  # general pass (the base instruction above)
    "本輪請特別聚焦【breaking change / 跨檔影響】：改動的函式簽章、回傳型別、查詢鍵（例如改用不同欄位查資料）、"
    "或契約語意是否會讓既有 caller 壞掉、查不到、或行為悄悄改變。順著 caller/callee 想清楚波及面。",
    "本輪請特別聚焦【並行 / 競態 / 順序】：TOCTOU（先檢查再使用/建立）、非原子的『查不到就新建』、"
    "重複建立、缺少冪等性、跨請求的競態。",
    "本輪請特別聚焦【行為變更 / 移除的邏輯】：這次刪掉或改掉的程式碼讓系統『不再做』什麼？"
    "（例如移除了快取、移除了某個挑選/回退邏輯、改了預設值），這些沉默的變更有什麼後果。",
]

def find_prompt(b: Bundle, lens: str = "") -> str:
    head = SYSTEM_FIND if not lens else f"{SYSTEM_FIND}\n\n【本輪視角】{lens}"
    return f"{head}\n\n{_render_context(b)}"

def consolidate_prompt(findings_summary: str) -> str:
    return (
        "以下是一份 code review 的多條發現。有些其實是【同一個根本原因】在不同位置或不同觸發點"
        "的重複描述（例如同一個邏輯改動在 5 個 if 分支各被報一次）。\n"
        "請把同根因的合併成一條，並在 members 裡列出它涵蓋的所有輸入編號；不同根因的保持獨立。\n"
        "規則：① 只合併真正同根因的；② 絕對不要刪掉任何獨立問題；"
        "③ 每一條輸入發現的編號都必須出現在某個 group 的 members 裡（寧可獨立成一組，也不要漏）。\n"
        "severity 取該組最嚴重的。用繁體中文，只輸出 JSON：\n"
        "{\"groups\":[{\"title\":..,\"severity\":\"blocker|major|minor\",\"rationale\":..,\"members\":[編號,..]}]}\n\n"
        f"## 發現清單（編號從 0 起）\n{findings_summary}"
    )

def verify_prompt(finding_title: str, premise: str, source: str) -> str:
    return (
        "你在對一條 code review 發現做『落地反證』。用繁體中文，只輸出 JSON。\n"
        f"發現：{finding_title}\n"
        f"它依賴的前提：{premise}\n"
        "下面是這條前提實際對應的源碼。請順著前提去讀真實源碼，判斷前提是否成立。\n"
        "只有當源碼【明確】反證前提時（例如該情況其實已被處理、或事實根本不是它講的那樣），"
        "才 confirmed=false。\n"
        "若源碼支持前提、或你無法從源碼確定，一律 confirmed=true（保留，讓資深工程師判斷）。\n"
        "原則：寧可保留讓人看，也不要誤殺一個真問題（不漏 > 不吵）。\n"
        f"\n## 實際源碼\n{source}\n\n"
        "輸出：{\"confirmed\": true|false, \"reason\": \"...\"}"
    )
