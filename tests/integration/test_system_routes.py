from fastapi.testclient import TestClient


def test_health_endpoint_returns_expected_contract(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "status": "ok",
            "service": "question-paraphrase-demo",
        },
        "error": None,
    }


def test_public_config_does_not_expose_secrets(client: TestClient) -> None:
    response = client.get("/config/public")
    payload = response.json()
    serialized_payload = response.text.lower()

    assert response.status_code == 200
    assert payload["data"] == {
        "paraphraseProvider": "local",
        "generationProvider": "mock",
        "embeddingModelName": "intfloat/multilingual-e5-small",
        "embeddingProvider": "mock_deterministic",
        "embeddingDimension": 384,
        "vectorTopK": 10,
    }
    assert "api_key" not in serialized_payload
    assert "apikey" not in serialized_payload
    assert "generation_api_key" not in serialized_payload
    assert "local_paraphrase_model" not in serialized_payload
    assert "qwen" not in serialized_payload


def test_unknown_route_uses_standard_error_contract(client: TestClient) -> None:
    response = client.get("/route-that-does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "NOT_FOUND",
            "message": "Không tìm thấy tài nguyên",
            "details": {"statusCode": 404},
        },
    }
