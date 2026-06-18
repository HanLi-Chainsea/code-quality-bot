# Pin the SAME digest the prod compose uses, so the base stays controlled.
FROM codiumai/pr-agent@sha256:a5741a479f21d20a9bbeca7847a720f92ac6f427e8dc0920fefa039ecafd5e6f

# our engine + patches (build context = repo root)
COPY review-engine/review_engine /app/cqb/review_engine
COPY deploy/engine-integration/cqb_patch /app/cqb/cqb_patch
COPY deploy/engine-integration/NOTICE /app/cqb/NOTICE

# code-review-graph + make our packages importable
RUN pip install --no-cache-dir "code-review-graph==2.3.6"
ENV PYTHONPATH=/app/cqb

# patched entrypoint: apply monkeypatches, then run the same webhook server
ENTRYPOINT ["python", "-m", "cqb_patch.bootstrap"]
