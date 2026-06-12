#!/usr/bin/env bash
# Qodo Cover (cover-agent, open-source) augments a test file to raise coverage, via an LLM.
# Usage: run-qodo-cover.sh <project_dir> <source_file> <test_file> <test_command>
set -euo pipefail
PROJ="${1:?project dir}"; SRC="${2:?source file}"; TST="${3:?test file}"; TESTCMD="${4:?test command}"
KEY=$(grep '^LITELLM_MASTER_KEY=' .env | cut -d= -f2-)
mkdir -p eval/out
sg docker -c "docker run --rm --network code-quality-bot_default \
  -e OPENAI_API_BASE=http://cqb-litellm:4000 -e OPENAI_BASE_URL=http://cqb-litellm:4000 -e OPENAI_API_KEY=$KEY \
  -v $(realpath "$PROJ"):/proj -w /proj \
  --entrypoint bash python:3.12-slim -c '
    apt-get update -qq && apt-get install -y -qq git >/dev/null 2>&1
    pip install -q git+https://github.com/qodo-ai/qodo-cover.git pytest coverage 2>&1 | tail -2
    cover-agent --source-file-path \"$SRC\" --test-file-path \"$TST\" \
      --code-coverage-report-path coverage.xml --coverage-type cobertura \
      --test-command \"$TESTCMD\" --model openai/minimax --max-iterations 3 2>&1
  '" 2>&1 | tee "eval/out/qodo-cover-$(basename "$PROJ").log"
