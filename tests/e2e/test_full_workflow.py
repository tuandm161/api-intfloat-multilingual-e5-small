from fastapi.testclient import TestClient


def fake_full_candidate(
    stem: str,
    *,
    option_a: str = "Thực hiện đầy đủ quy trình kỹ thuật trong thời gian quy định.",
    option_b: str = "Bảo đảm duy trì sự sống của người bệnh ở giai đoạn khẩn cấp.",
    option_c: str = "Giúp thân nhân người bệnh bớt lo lắng.",
    option_d: str = "Sàng lọc người bệnh để chuyển khoa sớm hơn.",
) -> str:
    return (
        '{"stem":"'
        + stem
        + '","optionA":"'
        + option_a
        + '","optionB":"'
        + option_b
        + '","optionC":"'
        + option_c
        + '","optionD":"'
        + option_d
        + '"}'
    )


def fake_candidate_outputs(
    stem: str,
    *,
    option_a: str = "Thực hiện đầy đủ quy trình kỹ thuật trong thời gian quy định.",
    option_b: str = "Bảo đảm duy trì sự sống của người bệnh ở giai đoạn khẩn cấp.",
    option_c: str = "Giúp thân nhân người bệnh bớt lo lắng.",
    option_d: str = "Sàng lọc người bệnh để chuyển khoa sớm hơn.",
) -> list[str]:
    return [stem, option_a, option_b, option_c, option_d]


def create_and_validate_job(client: TestClient) -> dict:
    created = client.post(
        "/paraphrase-jobs",
        json={
            "sourceQuestionId": "Q001", "mode": "FULL_QUESTION", "requestedCount": 5,
            "targetLanguage": "vi", "changeStrength": "medium", "provider": "mock",
        },
    )
    assert created.status_code == 201
    job_id = created.json()["data"]["jobId"]
    validated = client.post(f"/paraphrase-jobs/{job_id}/validate")
    assert validated.status_code == 200
    return client.get(
        f"/paraphrase-jobs/{job_id}", headers={"Accept": "application/json"}
    ).json()["data"]


def test_full_happy_path_creates_inherited_child_question(client: TestClient) -> None:
    job = create_and_validate_job(client)
    labels = {candidate["label"] for candidate in job["candidates"]}
    assert "GOOD" in labels
    assert all(
        "CONTAINS_ANSWER_HINT" not in candidate["warnings"]
        for candidate in job["candidates"]
    )
    good = next(candidate for candidate in job["candidates"] if candidate["label"] == "GOOD")
    assert client.post(
        f"/paraphrase-candidates/{good['id']}/approve",
        json={"reviewerNotes": "Meaning preserved."},
    ).status_code == 200
    saved = client.post(f"/paraphrase-candidates/{good['id']}/save-as-question").json()["data"]
    child = client.get(
        f"/questions/{saved['newQuestionId']}", headers={"Accept": "application/json"}
    ).json()["data"]
    parent = client.get("/questions/Q001", headers={"Accept": "application/json"}).json()["data"]
    assert child["questionType"] == "PARAPHRASE"
    assert child["parentQuestionId"] == "Q001"
    assert child["options"] == good["options"]
    assert child["options"] != parent["options"]
    assert child["correctAnswer"] == parent["correctAnswer"]
    assert client.post(f"/paraphrase-candidates/{good['id']}/save-as-question").status_code == 400
    parent_html = client.get("/questions/Q001", headers={"Accept": "text/html"})
    assert saved["newQuestionId"] in parent_html.text


def test_edit_requires_revalidation_and_reject_keeps_notes(client: TestClient) -> None:
    job = create_and_validate_job(client)
    candidate = job["candidates"][0]
    edited = client.put(
        f"/paraphrase-candidates/{candidate['id']}",
        json={"candidateStem": "Trong cấp cứu, mục tiêu của việc ưu tiên đánh giá ABC là gì?"},
    ).json()["data"]
    assert edited["status"] == "GENERATED"
    assert edited["semanticSimilarityToSource"] is None
    assert edited["warnings"] == ["EDITED_REVALIDATION_REQUIRED"]
    assert client.post(
        f"/paraphrase-candidates/{candidate['id']}/approve", json={}
    ).status_code == 400
    rejected = client.post(
        f"/paraphrase-candidates/{candidate['id']}/reject",
        json={"reviewerNotes": "Needs a rewrite."},
    )
    assert rejected.status_code == 200
    detail = client.get(f"/paraphrase-candidates/{candidate['id']}").json()["data"]
    assert detail["status"] == "REJECTED"
    assert detail["reviewerNotes"] == "Needs a rewrite."


def test_validation_rejects_too_little_rewrite(client: TestClient) -> None:
    created = client.post(
        "/paraphrase-jobs",
        json={"sourceQuestionId": "Q001", "requestedCount": 1, "provider": "mock"},
    )
    assert created.status_code == 201
    job_id = created.json()["data"]["jobId"]
    job = client.get(
        f"/paraphrase-jobs/{job_id}", headers={"Accept": "application/json"}
    ).json()["data"]
    candidate_id = job["candidates"][0]["id"]

    client.put(
        f"/paraphrase-candidates/{candidate_id}",
        json={"candidateStem": "Trong chăm sóc cấp tính, ưu tiên ABC nhằm mục đích gì?"},
    )
    validated = client.post(f"/paraphrase-candidates/{candidate_id}/validate")

    assert validated.status_code == 200
    data = validated.json()["data"]
    assert data["label"] == "REJECTED"
    assert "TOO_LITTLE_REWRITE" in data["warnings"]


def test_paraphrase_validation_does_not_check_question_bank_duplicates(
    client: TestClient,
) -> None:
    job = create_and_validate_job(client)
    duplicate_warnings = {
        "POSSIBLE_DUPLICATE_WITH_EXISTING_QUESTION",
        "STRONG_DUPLICATE_WITH_EXISTING_QUESTION",
        "VECTOR_INDEX_NOT_READY",
    }

    for candidate in job["candidates"]:
        assert candidate["duplicateMaxSimilarity"] is None
        assert candidate["duplicateQuestionId"] is None
        assert duplicate_warnings.isdisjoint(candidate["warnings"])


def test_audit_export_and_reset_are_repeatable(client: TestClient) -> None:
    create_and_validate_job(client)
    logs = client.get("/audit-logs").json()["data"]
    assert logs["total"] > 0
    assert any(item["action"] == "PARAPHRASE_CANDIDATE_VALIDATED" for item in logs["items"])
    json_export = client.get("/exports/questions.json").json()["data"]
    csv_export = client.get("/exports/questions.csv")
    assert json_export["count"] == 108
    assert csv_export.status_code == 200
    assert csv_export.content.startswith(b"\xef\xbb\xbf")
    reset = client.post("/demo/reset").json()["data"]
    assert reset["seededCount"] == 108
    assert client.get("/questions", headers={"Accept": "application/json"}).json()["data"]["total"] == 108


def test_job_pages_render_review_information(client: TestClient) -> None:
    job = create_and_validate_job(client)
    jobs_page = client.get("/paraphrase-jobs", headers={"Accept": "text/html"})
    detail_page = client.get(
        f"/paraphrase-jobs/{job['id']}", headers={"Accept": "text/html"}
    )
    assert job["id"] in jobs_page.text
    assert "Tương đồng ngữ nghĩa" in detail_page.text
    assert "4 đáp án nguồn" in detail_page.text
    assert "Lưu thành câu hỏi" in detail_page.text
    assert "disabled" in detail_page.text


def test_generator_failure_persists_failed_job_and_supports_retry(client: TestClient) -> None:
    response = client.post(
        "/paraphrase-jobs",
        json={"sourceQuestionId": "Q001", "requestedCount": 3, "provider": "api"},
    )
    assert response.status_code == 503
    job_id = response.json()["error"]["details"]["jobId"]
    failed = client.get(
        f"/paraphrase-jobs/{job_id}", headers={"Accept": "application/json"}
    ).json()["data"]
    assert failed["status"] == "FAILED"
    assert failed["candidates"] == []
    assert "API paraphrase provider is disabled" in failed["errorMessage"]
    retry = client.post(f"/paraphrase-jobs/{job_id}/retry")
    assert retry.status_code == 503


def test_local_generator_creates_candidates_with_fake_model(
    client: TestClient, monkeypatch
) -> None:
    class FakeLlama:
        def __init__(self) -> None:
            self.contents = (
                fake_candidate_outputs(
                    "Vì sao cần ưu tiên đánh giá ABC trước trong chăm sóc cấp tính?"
                )
                + fake_candidate_outputs(
                    "Khi chăm sóc cấp tính, ABC cần được ưu tiên vì lý do gì?"
                )
            )
            self.calls = 0

        def create_chat_completion(self, **kwargs):
            index = min(self.calls, len(self.contents) - 1)
            self.calls += 1
            return {
                "choices": [
                    {
                        "message": {
                            "content": self.contents[index]
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "app.modules.paraphrase.providers.local.get_local_llama_model",
        lambda settings: FakeLlama(),
    )

    response = client.post(
        "/paraphrase-jobs",
        json={
            "sourceQuestionId": "Q001",
            "requestedCount": 2,
            "targetLanguage": "vi",
            "changeStrength": "medium",
            "provider": "local",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "GENERATED"
    assert data["candidateCount"] == 2
    detail = client.get(
        f"/paraphrase-jobs/{data['jobId']}",
        headers={"Accept": "application/json"},
    ).json()["data"]
    assert detail["provider"] == "local"
    assert [item["candidateStem"] for item in detail["candidates"]] == [
        "Vì sao cần ưu tiên đánh giá ABC trước trong chăm sóc cấp tính?",
        "Khi chăm sóc cấp tính, ABC cần được ưu tiên vì lý do gì?",
    ]
    assert detail["candidates"][0]["optionB"] == (
        "Bảo đảm duy trì sự sống của người bệnh ở giai đoạn khẩn cấp."
    )


def test_missing_provider_uses_local_paraphrase_provider(
    client: TestClient, monkeypatch
) -> None:
    class FakeLlama:
        def __init__(self) -> None:
            self.contents = fake_candidate_outputs(
                "Vì sao cần ưu tiên đánh giá ABC trước trong chăm sóc cấp tính?"
            )
            self.calls = 0

        def create_chat_completion(self, **kwargs):
            index = min(self.calls, len(self.contents) - 1)
            self.calls += 1
            return {
                "choices": [
                    {
                        "message": {
                            "content": self.contents[index]
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "app.modules.paraphrase.providers.local.get_local_llama_model",
        lambda settings: FakeLlama(),
    )

    response = client.post(
        "/paraphrase-jobs",
        json={
            "sourceQuestionId": "Q001",
            "requestedCount": 1,
            "targetLanguage": "vi",
            "changeStrength": "medium",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    detail = client.get(
        f"/paraphrase-jobs/{data['jobId']}",
        headers={"Accept": "application/json"},
    ).json()["data"]
    assert detail["provider"] == "local"


def test_all_required_audit_actions_are_recorded(client: TestClient) -> None:
    created = client.post(
        "/questions",
        json={
            "stem": "Câu hỏi audit dùng để kiểm thử là gì?", "optionA": "A", "optionB": "B",
            "optionC": "C", "optionD": "D", "correctAnswer": "A",
        },
    ).json()["data"]
    client.put(f"/questions/{created['id']}", json={"topic": "Audit test"})
    client.post("/embeddings/reindex")
    job = create_and_validate_job(client)
    good = next(item for item in job["candidates"] if item["label"] == "GOOD")
    bad = next(item for item in job["candidates"] if item["id"] != good["id"])
    client.put(
        f"/paraphrase-candidates/{good['id']}",
        json={"candidateStem": "Trong cấp cứu, mục tiêu chính của ưu tiên ABC là gì?"},
    )
    client.post(f"/paraphrase-candidates/{good['id']}/validate")
    client.post(f"/paraphrase-candidates/{good['id']}/approve", json={})
    client.post(f"/paraphrase-candidates/{good['id']}/save-as-question")
    client.post(f"/paraphrase-candidates/{bad['id']}/reject", json={})
    client.get("/exports/questions.json")
    logs = client.get("/audit-logs", params={"pageSize": 100}).json()["data"]["items"]
    actions = {item["action"] for item in logs}
    assert {
        "QUESTION_CREATED", "QUESTION_UPDATED", "QUESTION_PARAPHRASE_SAVED",
        "PARAPHRASE_JOB_CREATED", "PARAPHRASE_CANDIDATES_GENERATED",
        "PARAPHRASE_CANDIDATE_VALIDATED", "PARAPHRASE_CANDIDATE_EDITED",
        "PARAPHRASE_CANDIDATE_APPROVED", "PARAPHRASE_CANDIDATE_REJECTED",
        "EMBEDDING_REINDEXED", "EXPORT_CREATED",
    }.issubset(actions)
