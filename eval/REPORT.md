# Bake-off decision report — Track 1 (local), 2026-06-03
LLM = MiniMax (MiniMax-Text-01) via self-hosted LiteLLM proxy. Samples: Spring PetClinic (Java), a TS sample, a Python sample.

| Tool | Role | Free self-host? | Works w/ MiniMax? | Maintained? | Result |
|------|------|-----------------|-------------------|-------------|--------|
| **PR-Agent** (Qodo Merge OSS) | code review | ✅ yes (Apache-2.0) | ✅ yes (via LiteLLM `openai/minimax`) | ✅ yes | ✅ **ADOPT for review** — caught real bugs (missing validation, float-money, URL injection) on a sample diff; ~1.5k tokens/review |
| **Diffblue Cover** | Java unit-test gen (non-LLM, symbolic) | ❌ **paid license** | n/a (no LLM) | ✅ yes (commercial) | ⚠️ **license gate** — image pulls & bundles JDK17, but `dcover create` refuses without a purchased license. Free tier = IntelliJ plugin only, not the automatable CLI. Evaluate via vendor trial. |
| **Qodo Cover** (cover-agent OSS) | LLM test-gen (TS/Java/Py) | ✅ installs (pip from git) | ❌ **no** out-of-box | ❌ **unmaintained** | ❌ **not usable now** — repo archived ("fork it"); ignores OPENAI_API_BASE/OPENAI_BASE_URL so it can't target the self-hosted MiniMax proxy without patching. |

## Decision
- **Code review → adopt PR-Agent** (free, self-hosted, MiniMax-backed, good quality). This is the safe MVP first ship.
- **Java unit-test gen → no free turnkey option today.** Diffblue is strong but commercial-licensed; Qodo Cover OSS is unmaintained + broken for self-hosted LLMs. **Decision: trial Diffblue (paid) for the heavy-Java need, OR fork/patch cover-agent to accept a custom LLM base-url, OR use PR-Agent's `/improve` + test-suggestions as a lighter stopgap.**
- **TS unit-test gen → same gap;** PR-Agent test-suggestions or a maintained alternative needed.

## Key insight
Review is solved cheaply (PR-Agent + MiniMax). **The real gap for your team = free, self-hostable, MiniMax-compatible autonomous *test generation* (esp. Java).** That gap is where a small custom build (e.g. a LangGraph/Aider agent on MiniMax that writes tests → opens a PR → PR-Agent reviews it) could be justified — but only after a Diffblue trial.

## Caveats / scope
- Track 2 (real GitLab MR auto-review) was deferred (user choice B) — PR-Agent's *in-MR* experience not yet tested, only local CLI.
- All tool gotchas + exact commands captured in JOURNAL.md and docs/.

## Track 2 update (real GitLab MR)
- **PR-Agent reviews a real GitLab MR and posts in-MR** (PR Reviewer Guide + effort label + line-linked focus areas) on a self-managed GitLab CE. Confirms the "turnkey in-MR auto-review for colleagues" experience.
- Webhook *auto-trigger* hit a GitLab CE local-URL validation quirk (works in prod with a real hostname); the review+post itself works via the CLI against the MR URL. Net: **PR-Agent is adoptable for self-hosted GitLab review.**
