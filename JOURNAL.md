# Implementation Journal
## 2026-06-03 — Task 1: scaffold
Created project skeleton, git init.

## 2026-06-03 — Task 2: LiteLLM->MiniMax
Proxy up on :4000 (container cqb-litellm). /v1/chat/completions returns "pong" via MiniMax (model=minimax). NOTE: compose network = code-quality-bot_default (not cqb_default); runners must use this name.
