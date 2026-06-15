from review_engine.models import Bundle
from review_engine import prompt

def test_find_prompt_has_guardrails_and_context():
    b = Bundle(changed_files={"/r/util.py": "def add(a,b,c): ..."},
               related={"/r/main.py::run": "def run(): add(1,2)"}, diff="--- diff ---")
    p = prompt.find_prompt(b)
    assert "blocker" in p and "major" in p and "minor" in p
    assert "擋下" in p or "block" in p.lower()            # block-worthy framing
    assert "def add(a,b,c)" in p and "def run" in p       # context inlined
    assert "JSON" in p                                     # structured output required

def test_verify_prompt_demands_grounding():
    p = prompt.verify_prompt(finding_title="add() breaks caller",
                             premise="main.run calls add with 2 args",
                             source="def run():\n    return add(1, 2, 3)")
    assert "前提" in p or "premise" in p.lower()
    assert "add(1, 2, 3)" in p                             # the real source is included
