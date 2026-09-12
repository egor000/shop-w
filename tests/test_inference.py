import json

from shop.inference import VLLMProvider


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": json.dumps({
            "text": "Grounded answer", "products": [{"name": "Aurora Headphones", "url": "/products/aurora-headphones"}]
        })}}]}).encode()


def test_vllm_provider_parses_grounded_json(monkeypatch):
    monkeypatch.setattr("shop.inference.request.urlopen", lambda *args, **kwargs: _Response())
    answer = VLLMProvider("http://vllm.test", "qwen-test").answer("Which headphones?", None, timeout_seconds=2)
    assert answer.text == "Grounded answer"
    assert answer.products[0].url == "/products/aurora-headphones"
