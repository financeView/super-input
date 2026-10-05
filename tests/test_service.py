import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rerank.scorer import rank_from_scores
from rerank.service import create_app, ensure_token

ROOT = Path(__file__).resolve().parents[1]


class FakeScorer:
    def __init__(self, gap=10.0):
        self.gap = gap

    def rank(self, prefix, candidates):
        scores = [self.gap if candidate == "风景很美" else 0.0 for candidate in candidates]
        order, best, confidence = rank_from_scores(scores)
        return order, best, confidence, scores


class FakeDecoder:
    def __init__(self, text="风景很美"):
        self.text = text
        self.calls = 0

    def decode(self, context, syllables):
        self.calls += 1
        return self.text


def _body(keys="fenjinghenmei", candidates=None):
    return {
        "session_id": "s1",
        "request_id": 1,
        "keys": keys,
        "preedit": "",
        "candidates": candidates if candidates is not None else ["分静很没", "风景很美", "风景很每"],
        "context": "登高望远",
        "trust": "T0",
    }


def _headers(token):
    return {"X-SuperInput-Protocol": "1", "Authorization": f"Bearer {token}"}


@pytest.fixture()
def running_client(tmp_path):
    token_path = tmp_path / "nested" / "token"
    app = create_app({
        "token_file": str(token_path),
        "min_syllables": 2,
        "l1_conf_threshold": 0.5,
        "timeout_ms": 1500,
        "model": "unused",
        "port": 47625,
        "schema": str(ROOT / "assets/superpinyin.schema.yaml"),
        "context_window": 200,
        "cloud": {"enabled": False, "base_url": "", "model": ""},
    })
    app.state.scorer = FakeScorer()
    app.state.decoder = FakeDecoder()
    app.state.ready = True
    with TestClient(app) as client:
        yield client, ensure_token(token_path)


def test_auth_required_on_both_endpoints(running_client):
    client, token = running_client
    assert client.post("/rerank", json=_body()).status_code == 401
    assert client.get("/health").status_code == 401


def test_protocol_version_checked(running_client):
    client, token = running_client
    response = client.post("/rerank", json=_body(), headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400


def test_health_reports_readiness(running_client):
    client, token = running_client
    assert client.get("/health", headers=_headers(token)).json() == {"ready": True, "protocol": "1"}


def test_below_minimum_syllable_count_uses_fastpath(running_client):
    client, token = running_client
    response = client.post("/rerank", json=_body("jin"), headers=_headers(token))
    assert response.status_code == 200 and response.json()["mode"] == "fastpath"


def test_l1_ranking_returns_candidate_index_and_order(running_client):
    client, token = running_client
    response = client.post("/rerank", json=_body(), headers=_headers(token))
    result = response.json()
    assert result["mode"] == "L1" and result["best"] == 1
    assert result["order"] == [1, 0, 2]


def test_l1_hard_timeout_returns_fastpath_and_records_timeout(running_client):
    import time

    client, token = running_client
    client.app.state.cfg["timeout_ms"] = 10

    class SlowScorer:
        def rank(self, prefix, candidates):
            time.sleep(0.08)
            return [0, 1, 2], 0, 1.0, [1.0, 0.0, -1.0]

    client.app.state.scorer = SlowScorer()
    response = client.post("/rerank", json=_body(), headers=_headers(token))
    assert response.status_code == 200 and response.json()["mode"] == "fastpath"
    assert list(client.app.state.policy._windows["s1"]) == [True]


def test_low_confidence_upgrade_only_accepts_valid_l2(running_client):
    client, token = running_client
    client.app.state.scorer = FakeScorer(gap=0.3)
    response = client.post("/rerank", json=_body(), headers=_headers(token))
    result = response.json()
    assert result["mode"] == "L2" and result["l2_text"] == "风景很美"


def test_invalid_l2_falls_back_to_l1(running_client):
    client, token = running_client
    client.app.state.scorer = FakeScorer(gap=0.3)
    client.app.state.decoder = FakeDecoder("风景🙂很美")
    response = client.post("/rerank", json=_body(), headers=_headers(token))
    assert response.json()["mode"] == "L1"
    assert response.json()["l2_text"] is None


def test_candidate_limit_is_enforced_by_request_model(running_client):
    client, token = running_client
    body = _body(candidates=["候选"] * 21)
    response = client.post("/rerank", json=body, headers=_headers(token))
    assert response.status_code == 422


def test_local_decode_timeout_returns_l1_and_records_timeout(running_client):
    import time

    client, token = running_client
    client.app.state.scorer = FakeScorer(gap=0.3)
    client.app.state.cfg["timeout_ms"] = 10

    class SlowDecoder:
        def decode(self, context, syllables):
            time.sleep(0.08)
            return "风景很美"

    client.app.state.decoder = SlowDecoder()
    response = client.post("/rerank", json=_body(), headers=_headers(token))
    assert response.status_code == 200 and response.json()["mode"] == "L1"
    assert client.app.state.policy.should_downgrade("s1") is False
    # The first timeout is recorded but does not meet the 3/5 downgrade gate.
    assert len(client.app.state.policy._windows["s1"]) == 1


def test_configured_cloud_l2_is_used_after_timeout_window(running_client, monkeypatch):
    client, token = running_client
    client.app.state.scorer = FakeScorer(gap=0.3)
    client.app.state.cfg["cloud"].update({
        "enabled": True, "base_url": "https://api.example.com/v1", "model": "m1",
    })
    for _ in range(3):
        client.app.state.policy.record("s1", True)
    monkeypatch.setattr("rerank.cloud.read_keychain_key", lambda: "test-key")
    monkeypatch.setattr("rerank.cloud.CloudDecoder.decode", lambda self, context, syllables: "风景很美")
    response = client.post("/rerank", json=_body(), headers=_headers(token))
    assert response.json()["mode"] == "L2"
    assert client.app.state.decoder.calls == 0


def test_token_file_is_private_and_stable(tmp_path):
    token_file = tmp_path / "token"
    first = ensure_token(token_file)
    second = ensure_token(token_file)
    assert first == second and len(first) >= 40
    assert os.stat(token_file).st_mode & 0o777 == 0o600
