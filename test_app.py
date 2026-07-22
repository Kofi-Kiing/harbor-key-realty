import hashlib
import hmac
import json
import os
import tempfile

# Configure an isolated database and a known webhook key before importing the app.
os.environ["STORYCHIEF_WEBHOOK_KEY"] = "test-secret-key"
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DATABASE_URL"] = "sqlite:///" + _TMP_DB.name

from app import app  # noqa: E402

WEBHOOK_KEY = os.environ["STORYCHIEF_WEBHOOK_KEY"]


def canonical(payload):
    # Match app-side encoding (compact, escaped slashes) and, crucially, preserve
    # key order. Flask's test client json= helper sorts keys, which would break the
    # signature, so we build and post the raw body ourselves.
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True).replace("/", "\\/")


def sign(payload):
    return hmac.new(WEBHOOK_KEY.encode(), canonical(payload).encode(), hashlib.sha256).hexdigest()


def post_event(client, event, data):
    payload = {"meta": {"event": event}, "data": data}
    payload["meta"]["mac"] = sign(payload)
    return client.post(
        "/webhooks/storychief", data=canonical(payload), content_type="application/json"
    )


def test_routes():
    client = app.test_client()
    for path in [
        "/",
        "/properties",
        "/properties/modern-pearl-district-loft",
        "/about",
        "/contact",
        "/blog",
        "/blog/new",
        "/blog/portland-metro-market-outlook",
        "/api/health",
        "/api/properties",
        "/api/posts",
    ]:
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)


def test_api_filter():
    client = app.test_client()
    response = client.get("/api/properties?city=Portland&beds=3")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["count"] >= 1
    assert all(item["city"] == "Portland" and item["beds"] >= 3 for item in payload["properties"])


def test_blog_post_validation():
    client = app.test_client()
    response = client.post("/blog/new", data={"title": "", "body": ""})
    assert response.status_code == 400


def test_storychief_test_event():
    client = app.test_client()
    response = post_event(client, "test", {})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["mac"] == WEBHOOK_KEY


def test_storychief_bad_signature():
    client = app.test_client()
    payload = {"meta": {"event": "publish", "mac": "deadbeef"}, "data": {"id": 1, "title": "x"}}
    response = client.post(
        "/webhooks/storychief", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 401


def test_storychief_publish_and_delete():
    client = app.test_client()
    data = {
        "storychief_id": 987654,
        "title": "StoryChief Integration Works",
        "content": "<p>Hello from <strong>StoryChief</strong>.</p><script>alert(1)</script>",
        "excerpt": "A published article.",
        "featured_image": {
            "data": {
                "url": "https://example.test/cover.jpg",
                "alt": "Cover",
                "sizes": {"regular": "https://example.test/r.jpg", "large": "https://example.test/l.jpg"},
            }
        },
        "author": {"data": {"first_name": "Casey", "last_name": "Rivera"}},
        "categories": {"data": [{"storychief_id": 1, "name": "Announcements", "slug": "announcements"}]},
        "tags": {
            "data": [
                {"storychief_id": 2, "name": "News", "slug": "news"},
                {"storychief_id": 3, "name": "Product", "slug": "product"},
            ]
        },
        "seo_slug": "storychief-integration-works",
    }
    response = post_event(client, "publish", data)
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["id"] == "987654"
    assert body["permalink"].endswith("/blog/storychief-integration-works")

    # The post is visible and its HTML was sanitized (no script tag).
    detail = client.get("/blog/storychief-integration-works")
    assert detail.status_code == 200
    assert b"<script>" not in detail.data
    assert b"StoryChief" in detail.data

    # Nested "data" relations were unwrapped correctly.
    published = next(
        p for p in client.get("/api/posts").get_json()["posts"] if p["external_id"] == "987654"
    )
    assert published["author"] == "Casey Rivera"
    assert published["category"] == "Announcements"
    assert published["tags"] == ["News", "Product"]
    assert published["image"] == "https://example.test/cover.jpg"

    # An update keeps the same record.
    data["title"] = "StoryChief Integration Still Works"
    updated = post_event(client, "update", data)
    assert updated.status_code == 200
    assert updated.get_json()["id"] == "987654"

    # Delete removes it.
    deleted = post_event(client, "delete", {"storychief_id": 987654})
    assert deleted.status_code == 200
    assert client.get("/blog/storychief-integration-works").status_code == 404


if __name__ == "__main__":
    test_routes()
    test_api_filter()
    test_blog_post_validation()
    test_storychief_test_event()
    test_storychief_bad_signature()
    test_storychief_publish_and_delete()
    print("All smoke tests passed.")
