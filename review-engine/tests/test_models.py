from review_engine.models import ChangedFunction, Node, Finding

def test_changed_function_from_crg_dict():
    cf = ChangedFunction.from_crg({
        "qualified_name": "/r/util.py::add", "name": "add",
        "file_path": "/r/util.py", "line_start": 1, "line_end": 2,
        "language": "python", "is_test": False, "risk_score": 0.58,
    })
    assert cf.qualified_name == "/r/util.py::add"
    assert cf.line_start == 1 and cf.line_end == 2

def test_finding_roundtrip():
    f = Finding(severity="major", file="/r/util.py", line=1,
                title="signature change breaks caller", rationale="x",
                premise="main.run calls add(1,2) with 2 args")
    assert f.severity == "major"
    assert f.to_dict()["premise"].startswith("main.run")
