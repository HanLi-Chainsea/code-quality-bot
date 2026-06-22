import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]          # deploy/engine-integration
REPO = ROOT.parents[1]                                       # repo root
sys.path.insert(0, str(ROOT))                               # import cqb_patch
sys.path.insert(0, str(REPO / "review-engine"))            # import review_engine

# reuse the engine's fixture_repo / fixture_graph_dir
from review_engine_test_fixtures import *  # noqa  (created in Step 3)
