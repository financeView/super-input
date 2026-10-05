from unittest.mock import MagicMock, patch

import pytest
import requests

from rerank.cloud import CloudDecoder, CloudError, read_keychain_key


def test_decode_builds_openai_compatible_request():
    decoder = CloudDecoder("https://api.example.com/v1", "sk-test", "model-1")
    response = MagicMock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": "风景很美"}}]}
    with patch("rerank.cloud.requests.post", return_value=response) as post:
        output = decoder.decode("前文", ["fen", "jing"])
    assert output == "风景很美"
    kwargs = post.call_args.kwargs
    assert post.call_args.args[0] == "https://api.example.com/v1/chat/completions"
    assert kwargs["json"]["model"] == "model-1"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["json"]["messages"][0]["role"] == "system"


def test_retry_once_on_429_then_raise():
    decoder = CloudDecoder("https://api.example.com/v1", "sk-test", "model-1")
    response = MagicMock(status_code=429)
    with patch("rerank.cloud.requests.post", return_value=response) as post, patch("rerank.cloud.time.sleep"):
        with pytest.raises(CloudError):
            decoder.decode("前文", ["fen"])
    assert post.call_count == 2


def test_network_failure_retries_once():
    decoder = CloudDecoder("https://api.example.com/v1", "sk-test", "model-1")
    with patch("rerank.cloud.requests.post", side_effect=requests.Timeout), patch("rerank.cloud.time.sleep"), \
         pytest.raises(CloudError):
        decoder.decode("前文", ["fen"])


def test_non_https_base_url_is_rejected():
    with pytest.raises(ValueError, match="HTTPS"):
        CloudDecoder("http://example.com/v1", "sk-test", "model-1")


def test_keychain_missing_raises(monkeypatch):
    class Result:
        returncode, stdout = 44, ""
    monkeypatch.setattr("rerank.cloud.subprocess.run", lambda *args, **kwargs: Result())
    with pytest.raises(CloudError):
        read_keychain_key()
