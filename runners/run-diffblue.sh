#!/usr/bin/env bash
# Diffblue Cover (dcover) autonomously writes JUnit tests for a compiled Maven project. No LLM.
# Usage: run-diffblue.sh <java_project_path>
set -euo pipefail
PROJ="${1:?java project path}"
mkdir -p eval/out
sg docker -c "docker run --rm \
  -v $(realpath "$PROJ"):/proj -w /proj \
  --entrypoint bash diffblue/cover-cli:latest \
  -c 'git config --global --add safe.directory /proj; dcover create --maven 2>&1'" 2>&1 | tee "eval/out/diffblue-$(basename "$PROJ").log"
