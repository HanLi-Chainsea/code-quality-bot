# Production deploy (cloud GitLab + Mac mini)
The 2 services that run on the Mac mini. See ../docs/deploy-macmini.md for the full step-by-step.
- litellm → MiniMax (LLM gateway, budget-capped)
- pr-agent (GitLab webhook server, posts reviews into MRs)
GitLab CE is NOT here — you use your real cloud GitLab.
