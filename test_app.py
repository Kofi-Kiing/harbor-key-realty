from app import app

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

if __name__ == "__main__":
    test_routes()
    test_api_filter()
    test_blog_post_validation()
    print("All smoke tests passed.")
