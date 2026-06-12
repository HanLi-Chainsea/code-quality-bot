#!/usr/bin/env bash
set -euo pipefail
# create a known root API token (retries: rails may still be warming up)
for i in $(seq 1 10); do
  TOKEN=$(sg docker -c "docker exec cqb-gitlab gitlab-rails runner \"t=User.find_by_username('root').personal_access_tokens.create(scopes:['api','write_repository'],name:'cqb'); t.set_token('cqb-root-token'); t.save!; puts t.token\"" 2>/dev/null | tail -1)
  [ "$TOKEN" = "cqb-root-token" ] && break
  echo "  rails warming up ($i)..."; sleep 12
done
echo "root token: $TOKEN"
# create the petclinic project (idempotent)
curl -s --header "PRIVATE-TOKEN: cqb-root-token" -X POST "http://localhost:8929/api/v4/projects" -d "name=petclinic&visibility=private" >/dev/null || true
echo "project created"
