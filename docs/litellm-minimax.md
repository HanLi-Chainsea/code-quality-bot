# LiteLLM → MiniMax — BUILD & USAGE
## BUILD
1. `litellm/config.yaml` defines model `minimax` → `openai/MiniMax-Text-01`, api_base `https://api.minimax.io/v1`, key from `MINIMAX_API_KEY`.
2. `.env`: `MINIMAX_API_KEY=<sk-cp-...>`, `LITELLM_MASTER_KEY=sk-cqb-localdev`.
3. `sg docker -c "docker compose up -d litellm"` → proxy on :4000 (container `cqb-litellm`).
## USAGE
- Health: `curl localhost:4000/health/liveliness` → 200.
- Completion: `curl localhost:4000/v1/chat/completions -H "Authorization: Bearer sk-cqb-localdev" -H "Content-Type: application/json" -d '{"model":"minimax","messages":[{"role":"user","content":"pong"}]}'`.
- From other containers on `code-quality-bot_default`: base url `http://cqb-litellm:4000`, model `minimax` (or `openai/minimax` for litellm SDK clients).
## Notes
- MiniMax key only valid on `api.minimax.io` (NOT api.minimaxi.com → 401). Budget cap = $50/30d in config.
