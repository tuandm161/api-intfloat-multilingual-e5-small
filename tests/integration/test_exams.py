from fastapi.testclient import TestClient


def create_exam(client: TestClient) -> dict:
    response = client.post(
        "/exams",
        json={"title": "Đề kiểm tra thử", "description": "Kiểm tra chống trùng"},
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_exam_pages_and_question_management(client: TestClient) -> None:
    exam = create_exam(client)
    assert client.get("/exams", headers={"Accept": "text/html"}).status_code == 200
    detail = client.get(f"/exams/{exam['id']}", headers={"Accept": "text/html"})
    assert detail.status_code == 200
    assert "Thêm câu từ ngân hàng" in detail.text
    assert "multilingual E5" in detail.text

    added = client.post(
        f"/exams/{exam['id']}/questions", json={"questionId": "Q001"}
    )
    assert added.status_code == 201
    current = client.get(
        f"/exams/{exam['id']}", headers={"Accept": "application/json"}
    ).json()["data"]
    assert current["questionCount"] == 1
    assert current["questions"][0]["id"] == "Q001"

    removed = client.delete(f"/exams/{exam['id']}/questions/Q001")
    assert removed.status_code == 200
    assert client.get(
        f"/exams/{exam['id']}", headers={"Accept": "application/json"}
    ).json()["data"]["questionCount"] == 0


def test_semantic_duplicate_is_blocked_only_inside_same_exam(
    client: TestClient,
) -> None:
    similar = client.post(
        "/questions",
        json={
            "stem": "Trong chăm sóc cấp tính, ưu tiên ABC để làm gì?",
            "optionA": "A",
            "optionB": "B",
            "optionC": "C",
            "optionD": "D",
            "correctAnswer": "A",
        },
    )
    assert similar.status_code == 201
    similar_id = similar.json()["data"]["id"]

    first_exam = create_exam(client)
    second_exam = create_exam(client)
    assert client.post(
        f"/exams/{first_exam['id']}/questions", json={"questionId": "Q001"}
    ).status_code == 201

    blocked = client.post(
        f"/exams/{first_exam['id']}/questions", json={"questionId": similar_id}
    )
    assert blocked.status_code == 409
    details = blocked.json()["error"]["details"]
    assert details["duplicateQuestionId"] == "Q001"
    assert details["similarity"] >= 0.88
    assert client.get(
        f"/exams/{first_exam['id']}", headers={"Accept": "application/json"}
    ).json()["data"]["questionCount"] == 1

    allowed_other_exam = client.post(
        f"/exams/{second_exam['id']}/questions", json={"questionId": similar_id}
    )
    assert allowed_other_exam.status_code == 201
