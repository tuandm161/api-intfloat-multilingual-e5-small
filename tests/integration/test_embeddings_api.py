from fastapi.testclient import TestClient


def test_reindex_and_duplicate_search(client: TestClient) -> None:
    reindex = client.post("/embeddings/reindex").json()["data"]
    status = client.get("/embeddings/status").json()["data"]
    results = client.post(
        "/duplicates/search",
        json={"text": "Trong cấp cứu vì sao cần ưu tiên ABC?", "topK": 5, "excludeQuestionIds": ["Q001"]},
    ).json()["data"]["items"]
    assert reindex["embeddedCount"] == 108
    assert status["indexReady"] is True
    assert status["questionEmbeddingCount"] >= 108
    assert all(item["questionId"] != "Q001" for item in results)
    assert results == sorted(results, key=lambda item: item["similarity"], reverse=True)
