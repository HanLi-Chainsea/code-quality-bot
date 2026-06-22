# Re-use the exact fixtures from review-engine/tests/conftest.py
import sys, pathlib, importlib.util

_engine_tests = pathlib.Path(__file__).resolve().parents[3] / "review-engine" / "tests"
_spec = importlib.util.spec_from_file_location(
    "_engine_conftest", str(_engine_tests / "conftest.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

fixture_repo = _mod.fixture_repo          # noqa: F401
fixture_graph_dir = _mod.fixture_graph_dir  # noqa: F401
