from review_engine import llm

def test_llm_client_reads_env(monkeypatch):
    monkeypatch.setenv("REVIEWER_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("REVIEWER_API_KEY", "sk-test")
    c = llm.Client.from_env()
    assert c.base_url == "http://127.0.0.1:4000/v1"
    assert c.model == "reviewer"
