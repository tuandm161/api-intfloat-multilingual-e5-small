from fastapi.testclient import TestClient


def test_seeded_question_bank_and_detail(client: TestClient) -> None:
    listing = client.get("/questions", headers={"Accept": "application/json"}).json()["data"]
    detail = client.get("/questions/Q001", headers={"Accept": "application/json"}).json()["data"]
    assert listing["total"] == 108
    assert detail["correctAnswer"] == "B"
    assert detail["questionType"] == "ORIGINAL"


def test_question_search_and_filters(client: TestClient) -> None:
    response = client.get(
        "/questions",
        params={"search": "té ngã", "status": "APPROVED", "questionType": "ORIGINAL"},
        headers={"Accept": "application/json"},
    ).json()["data"]
    assert response["total"] == 1
    assert response["items"][0]["id"] == "Q006"


def test_invalid_answer_and_paraphrase_without_parent_are_rejected(client: TestClient) -> None:
    base = {
        "stem": "A valid question stem?", "optionA": "A", "optionB": "B",
        "optionC": "C", "optionD": "D", "correctAnswer": "X",
    }
    invalid_answer = client.post("/questions", json=base)
    assert invalid_answer.status_code == 422
    assert invalid_answer.json()["error"]["code"] == "VALIDATION_ERROR"
    base["correctAnswer"] = "A"
    base["questionType"] = "PARAPHRASE"
    no_parent = client.post("/questions", json=base)
    assert no_parent.status_code == 400
    assert no_parent.json()["error"]["code"] == "VALIDATION_ERROR"


def test_semantically_duplicate_questions_can_coexist_in_bank(client: TestClient) -> None:
    original = client.get(
        "/questions/Q001", headers={"Accept": "application/json"}
    ).json()["data"]
    response = client.post(
        "/questions",
        json={
            "stem": f"  {original['stem']}  ",
            "optionA": "Phương án mới A",
            "optionB": "Phương án mới B",
            "optionC": "Phương án mới C",
            "optionD": "Phương án mới D",
            "correctAnswer": "A",
        },
    )

    assert response.status_code == 201
    assert client.get(
        "/questions", headers={"Accept": "application/json"}
    ).json()["data"]["total"] == 109


def test_semantically_similar_question_is_saved_to_bank(client: TestClient) -> None:
    response = client.post(
        "/questions",
        json={
            "stem": "Trong chăm sóc cấp tính, ưu tiên ABC để làm gì?",
            "optionA": "Phương án A",
            "optionB": "Phương án B",
            "optionC": "Phương án C",
            "optionD": "Phương án D",
            "correctAnswer": "A",
        },
    )

    assert response.status_code == 201


def test_new_question_is_embedded_immediately(client: TestClient) -> None:
    before = client.get("/embeddings/status").json()["data"][
        "questionEmbeddingCount"
    ]
    response = client.post(
        "/questions",
        json={
            "stem": "Người bệnh cần uống đủ nước mỗi ngày nhằm mục đích gì?",
            "optionA": "Hỗ trợ duy trì cân bằng dịch",
            "optionB": "Làm tăng nguy cơ mất nước",
            "optionC": "Thay thế hoàn toàn dinh dưỡng",
            "optionD": "Không có tác dụng sinh lý",
            "correctAnswer": "A",
        },
    )

    assert response.status_code == 201
    created = response.json()["data"]
    after = client.get("/embeddings/status").json()["data"][
        "questionEmbeddingCount"
    ]
    matches = client.post(
        "/duplicates/search",
        json={"text": created["stem"], "topK": 1},
    ).json()["data"]["items"]
    assert after == before + 1
    assert matches[0]["questionId"] == created["id"]
