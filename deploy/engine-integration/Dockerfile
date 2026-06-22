# Pin the SAME digest the prod compose uses, so the base stays controlled.
FROM codiumai/pr-agent@sha256:a5741a479f21d20a9bbeca7847a720f92ac6f427e8dc0920fefa039ecafd5e6f

# our engine + patches (build context = repo root)
COPY review-engine/review_engine /app/cqb/review_engine
COPY deploy/engine-integration/cqb_patch /app/cqb/cqb_patch
COPY deploy/engine-integration/NOTICE /app/cqb/NOTICE

# code-review-graph in an ISOLATED venv — its deps (newer starlette etc.) must NOT touch PR-Agent's
# python. review_engine only shells out to this binary, so isolation is complete.
RUN python -m venv /opt/crg-venv \
    && /opt/crg-venv/bin/pip install --no-cache-dir "code-review-graph==2.3.6"
ENV CQB_CRG_BIN=/opt/crg-venv/bin/code-review-graph
# review_engine + cqb_patch are pure-stdlib, importable from PR-Agent's python:
ENV PYTHONPATH=/app/cqb

# patched entrypoint: apply monkeypatches, then run the same webhook server
ENTRYPOINT ["python", "-m", "cqb_patch.bootstrap"]
