from app import app

def test_routes():
    client = app.test_client()
    for path in ["/", "/properties", "/properties/modern-pearl-district-loft", "/about", "/contact", "/api/health", "/api/properties"]:
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)

def test_api_filter():
    client = app.test_client()
    response = client.get("/api/properties?city=Portland&beds=3")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["count"] >= 1
    assert all(item["city"] == "Portland" and item["beds"] >= 3 for item in payload["properties"])

if __name__ == "__main__":
    test_routes()
    test_api_filter()
    print("All smoke tests passed.")
