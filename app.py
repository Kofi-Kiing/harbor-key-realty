from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "properties.json"
BLOG_FILE = BASE_DIR / "data" / "blog_posts.json"
FEATURED_FILE = BASE_DIR / "data" / "featured_articles.json"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")


def load_properties() -> list[dict[str, Any]]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_posts() -> list[dict[str, Any]]:
    if not BLOG_FILE.exists():
        return []
    with BLOG_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_featured_articles() -> list[dict[str, Any]]:
    if not FEATURED_FILE.exists():
        return []
    with FEATURED_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_posts(posts: list[dict[str, Any]]) -> None:
    with BLOG_FILE.open("w", encoding="utf-8") as file:
        json.dump(posts, file, indent=2, ensure_ascii=False)
        file.write("\n")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "post"


def unique_slug(base: str, existing: set[str]) -> str:
    slug = base
    suffix = 2
    while slug in existing:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def split_tags(raw: str) -> list[str]:
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


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


@app.template_filter("prettydate")
def prettydate(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return value
    return parsed.strftime("%B %-d, %Y")


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


@app.route("/blog")
def blog():
    posts = sorted(load_posts(), key=lambda item: item["date"], reverse=True)
    category = request.args.get("category", "").strip()
    if category:
        posts = [post for post in posts if post.get("category") == category]
    categories = sorted({post.get("category") for post in load_posts() if post.get("category")})
    return render_template(
        "blog.html",
        posts=posts,
        categories=categories,
        active_category=category,
        featured_articles=load_featured_articles(),
    )


@app.route("/blog/new", methods=["GET", "POST"])
def blog_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        author = request.form.get("author", "").strip() or "Guest Contributor"
        category = request.form.get("category", "").strip() or "General"
        image = request.form.get("image", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        tags = split_tags(request.form.get("tags", ""))

        if not title or not body:
            flash("A title and body are required to publish a post.", "error")
            return render_template("blog_new.html", form=request.form), 400

        posts = load_posts()
        existing_slugs = {post["slug"] for post in posts}
        slug = unique_slug(slugify(title), existing_slugs)

        if not excerpt:
            first_paragraph = body.split("\n\n", 1)[0].strip()
            excerpt = (first_paragraph[:197] + "…") if len(first_paragraph) > 198 else first_paragraph

        new_post = {
            "id": max((post["id"] for post in posts), default=0) + 1,
            "slug": slug,
            "title": title,
            "author": author,
            "date": date.today().isoformat(),
            "category": category,
            "excerpt": excerpt,
            "image": image,
            "tags": tags,
            "body": body,
        }
        posts.append(new_post)
        save_posts(posts)

        flash("Your post was published.", "success")
        return redirect(url_for("blog_detail", slug=slug))

    return render_template("blog_new.html", form={})


@app.route("/blog/<slug>")
def blog_detail(slug: str):
    posts = load_posts()
    post = next((item for item in posts if item["slug"] == slug), None)
    if post is None:
        abort(404)

    related = [
        item
        for item in sorted(posts, key=lambda item: item["date"], reverse=True)
        if item["slug"] != slug and item.get("category") == post.get("category")
    ][:3]
    return render_template("blog_detail.html", post=post, related=related)


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


@app.route("/api/posts")
def api_posts():
    posts = sorted(load_posts(), key=lambda item: item["date"], reverse=True)
    return jsonify({"count": len(posts), "posts": posts})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
