# Diffblue Cover — BUILD & USAGE   [STATUS: ⚠️ PAID LICENSE REQUIRED]
## BUILD
- Image `diffblue/cover-cli:latest` (803MB, bundles JDK17, dcover 2026.04.01) pulls freely.
## USAGE
- `bash runners/run-diffblue.sh <maven_project>` → runs `dcover create --maven`.
- Requires the project to COMPILE first (`mvn -DskipTests compile`).
## FINDING
- `dcover create` exits immediately requesting a PAID license (diffblue.com/pricing).
- The free Community Edition is an IntelliJ PLUGIN only — NOT the automatable CLI.
- Non-LLM (symbolic AI / formal verification) → deterministic, no MiniMax needed, strong for Java regression.
- TO EVALUATE: obtain a vendor trial license, set it per Diffblue docs, then re-run the runner.
