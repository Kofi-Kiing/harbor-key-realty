from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "properties.json"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")


def load_properties() -> list[dict[str, Any]]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def filter_properties(items: list[dict[str, Any]], args: dict[str, str]) -> list[dict[str, Any]]:
    city = args.get("city", "").strip().lower()
    property_type = args.get("type", "").strip().lower()
    beds = parse_int(args.get("beds"))
    min_price = parse_int(args.get("min_price"))
    max_price = parse_int(args.get("max_price"))
    query = args.get("q", "").strip().lower()

    filtered = []
    for item in items:
        haystack = " ".join(
            [
                item["title"],
                item["address"],
                item["city"],
                item["state"],
                item["type"],
                item["description"],
            ]
        ).lower()

        if query and query not in haystack:
            continue
        if city and item["city"].lower() != city:
            continue
        if property_type and item["type"].lower() != property_type:
            continue
        if beds is not None and int(item["beds"]) < beds:
            continue
        if min_price is not None and int(item["price"]) < min_price:
            continue
        if max_price is not None and int(item["price"]) > max_price:
            continue

        filtered.append(item)

    sort = args.get("sort", "featured")
    if sort == "price_asc":
        filtered.sort(key=lambda item: item["price"])
    elif sort == "price_desc":
        filtered.sort(key=lambda item: item["price"], reverse=True)
    elif sort == "sqft_desc":
        filtered.sort(key=lambda item: item["sqft"], reverse=True)
    else:
        filtered.sort(key=lambda item: (not item["featured"], -item["price"]))

    return filtered


@app.template_filter("money")
def money(value: int | float) -> str:
    return f"${value:,.0f}"


@app.route("/")
def home():
    properties = load_properties()
    featured = [item for item in properties if item["featured"]][:3]
    cities = sorted({item["city"] for item in properties})
    return render_template("home.html", featured=featured, cities=cities)


@app.route("/properties")
def listings():
    properties = load_properties()
    filtered = filter_properties(properties, request.args.to_dict())
    cities = sorted({item["city"] for item in properties})
    types = sorted({item["type"] for item in properties})
    return render_template(
        "listings.html",
        properties=filtered,
        cities=cities,
        types=types,
        filters=request.args,
    )


@app.route("/properties/<slug>")
def property_detail(slug: str):
    properties = load_properties()
    property_item = next((item for item in properties if item["slug"] == slug), None)
    if property_item is None:
        abort(404)

    related = [
        item
        for item in properties
        if item["slug"] != slug
        and (item["city"] == property_item["city"] or item["type"] == property_item["type"])
    ][:3]
    return render_template("detail.html", property=property_item, related=related)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("Please complete your name, email, and message.", "error")
            return render_template("contact.html"), 400

        # This demo deliberately avoids storing personal data.
        # Replace this block with your CRM, email provider, or database integration.
        app.logger.info("Demo inquiry received: name=%s email=%s", name, email)
        flash("Thanks — your demo inquiry was submitted successfully.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/api/properties")
def api_properties():
    properties = filter_properties(load_properties(), request.args.to_dict())
    return jsonify({"count": len(properties), "properties": properties})


@app.route("/api/properties/<int:property_id>")
def api_property(property_id: int):
    item = next((item for item in load_properties() if item["id"] == property_id), None)
    if item is None:
        return jsonify({"error": "Property not found"}), 404
    return jsonify(item)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
