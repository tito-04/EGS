import httpx

BASE_URL = "http://127.0.0.1:8000"


def test_request_and_correlation_ids_are_exposed() -> None:
    headers = {
        "X-Request-ID": "req-test-123",
        "X-Correlation-ID": "corr-test-456",
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{BASE_URL}/health", headers=headers)

    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "req-test-123"
    assert response.headers.get("x-correlation-id") == "corr-test-456"


def test_request_id_is_generated_when_missing() -> None:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{BASE_URL}/health")

    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert response.headers.get("x-correlation-id")
