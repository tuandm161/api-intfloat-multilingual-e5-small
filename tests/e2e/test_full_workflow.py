from fastapi.testclient import TestClient


def create_and_validate_job(client: TestClient) -> dict:
    created = client.post(
        "/paraphrase-jobs",
        json={
            "sourceQuestionId": "Q001", "mode": "STEM_ONLY", "requestedCount": 5,
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
    assert {"GOOD", "NEED_REVIEW", "REJECTED"}.issubset(labels)
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
    assert child["options"] == parent["options"]
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
    retry = client.post(f"/paraphrase-jobs/{job_id}/retry")
    assert retry.status_code == 503


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
    bad = next(item for item in job["candidates"] if item["label"] == "REJECTED")
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
