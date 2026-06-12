# Qodo Cover (cover-agent OSS) — BUILD & USAGE   [STATUS: ❌ UNMAINTAINED + broken for self-hosted LLM]
## BUILD
- No prebuilt image. In a `python:3.12-slim` container: `apt-get install -y git` then
  `pip install git+https://github.com/qodo-ai/qodo-cover.git pytest coverage`.
## USAGE (intended)
- `bash runners/run-qodo-cover.sh <project> <source_file> <test_file> "<test_command>"`
- Augments <test_file> to raise coverage; needs a cobertura coverage report + a seed test.
## FINDING
- Repo is NO LONGER MAINTAINED (README: "fork it if you wish to continue").
- cover-agent's LLM call gets `Connection refused` even though the same LiteLLM SDK reaches MiniMax fine
  with OPENAI_API_BASE (probe returns "Pong!"). It ignores OPENAI_API_BASE/OPENAI_BASE_URL → cannot target a
  self-hosted OpenAI-compatible proxy without patching the source.
- TO USE: fork + patch cover_agent to pass `api_base` to `litellm.completion`, OR point it at a cloud OpenAI key.
