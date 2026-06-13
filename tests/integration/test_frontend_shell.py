from fastapi.testclient import TestClient


def test_root_redirects_to_question_bank(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/questions"


def test_frontend_pages_render_shared_navigation(client: TestClient) -> None:
    routes = [
        "/questions",
        "/questions/new",
        "/questions/Q001",
        "/exams",
        "/exams/new",
        "/demo-guide",
    ]

    for route in routes:
        response = client.get(route, headers={"Accept": "text/html"})

        assert response.status_code == 200
        assert "Ngân hàng câu hỏi" in response.text
        assert "Bộ đề" in response.text
        assert "Lịch sử diễn đạt lại" in response.text
        assert "Hướng dẫn demo" in response.text


def test_new_question_page_creates_bank_question_without_duplicate_check(
    client: TestClient,
) -> None:
    response = client.get("/questions/new", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Tạo câu hỏi mới" in response.text
    assert "Lưu câu hỏi" in response.text
    assert "kiểm tra trùng ngữ nghĩa" not in response.text
