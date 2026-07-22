from __future__ import annotations

import hashlib
import hmac
import html as html_module
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import nh3
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "properties.json"
BLOG_FILE = BASE_DIR / "data" / "blog_posts.json"
FEATURED_FILE = BASE_DIR / "data" / "featured_articles.json"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")


def _database_uri() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    # SQLAlchemy requires the postgresql:// scheme; Render provides postgres://.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        url = "sqlite:///" + str(BASE_DIR / "data" / "blog.db")
    return url


app.config["SQLALCHEMY_DATABASE_URI"] = _database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(64), unique=True, nullable=True, index=True)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False, default="Harbor & Key Editorial")
    published_on = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(120), nullable=False, default="General")
    excerpt = db.Column(db.Text, nullable=False, default="")
    image = db.Column(db.String(1024), nullable=False, default="")
    tags = db.Column(db.JSON, nullable=False, default=list)
    body_html = db.Column(db.Text, nullable=False, default="")
    source = db.Column(db.String(32), nullable=False, default="manual")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def date(self) -> str:
        return self.published_on.isoformat() if self.published_on else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "external_id": self.external_id,
            "slug": self.slug,
            "title": self.title,
            "author": self.author,
            "date": self.date,
            "category": self.category,
            "excerpt": self.excerpt,
            "image": self.image,
            "tags": self.tags or [],
            "body_html": self.body_html,
            "source": self.source,
        }


def load_properties() -> list[dict[str, Any]]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_featured_articles() -> list[dict[str, Any]]:
    if not FEATURED_FILE.exists():
        return []
    with FEATURED_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


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


# --- HTML helpers -----------------------------------------------------------

ALLOWED_TAGS = {
    "a", "p", "br", "span", "div", "strong", "b", "em", "i", "u", "s",
    "blockquote", "code", "pre", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "td", "th",
}

ALLOWED_ATTRIBUTES = {
    # nh3 manages the "rel" attribute on links automatically (adds noopener/noreferrer).
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "*": {"class"},
}


def sanitize_html(raw: str | None) -> str:
    if not raw:
        return ""
    return nh3.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = nh3.clean(raw, tags=set(), attributes={})
    return re.sub(r"\s+", " ", text).strip()


def text_to_html(text: str | None) -> str:
    paragraphs = [para.strip() for para in (text or "").split("\n\n") if para.strip()]
    return "".join(
        "<p>{}</p>".format(html_module.escape(para).replace("\n", "<br>"))
        for para in paragraphs
    )


def derive_excerpt(body_html: str | None, limit: int = 198) -> str:
    text = strip_html(body_html)
    return (text[: limit - 1] + "…") if len(text) > limit else text


def existing_slugs(exclude_id: int | None = None) -> set[str]:
    query = db.session.query(Post.slug)
    if exclude_id is not None:
        query = query.filter(Post.id != exclude_id)
    return {row[0] for row in query.all()}


# --- StoryChief helpers -----------------------------------------------------

def storychief_key() -> str:
    return os.environ.get("STORYCHIEF_WEBHOOK_KEY", "").strip()


def verify_storychief_signature(payload: dict[str, Any]) -> bool:
    """Validate the StoryChief HMAC-SHA256 signature.

    StoryChief strips ``meta.mac`` from the payload, JSON-encodes the remainder
    (PHP ``json_encode`` style: compact separators, escaped forward slashes) and
    signs it with the channel encryption key. We recompute and compare.
    """
    key = storychief_key()
    if not key:
        return False
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return False
    received = meta.pop("mac", None)
    if not received:
        return False
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).replace("/", "\\/")
    calculated = hmac.new(key.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, str(received))


def parse_storychief_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_author(author: Any) -> str:
    if isinstance(author, dict):
        name = " ".join(
            part for part in [author.get("first_name"), author.get("last_name")] if part
        ).strip()
        return name or author.get("name") or "StoryChief"
    if isinstance(author, str) and author.strip():
        return author.strip()
    return "StoryChief"


def extract_category(categories: Any) -> str:
    if isinstance(categories, list) and categories:
        first = categories[0]
        if isinstance(first, dict):
            return first.get("name") or "General"
        if isinstance(first, str) and first.strip():
            return first.strip()
    return "General"


def extract_tags(tags: Any) -> list[str]:
    result: list[str] = []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict) and tag.get("name"):
                result.append(str(tag["name"]).strip())
            elif isinstance(tag, str) and tag.strip():
                result.append(tag.strip())
    return result


def extract_image(featured: Any) -> str:
    if isinstance(featured, dict):
        if featured.get("url"):
            return str(featured["url"])
        sizes = featured.get("sizes")
        if isinstance(sizes, dict):
            for key in ("large", "full", "original", "medium"):
                if sizes.get(key):
                    return str(sizes[key])
    if isinstance(featured, str) and featured.strip():
        return featured.strip()
    return ""


def upsert_storychief_post(data: dict[str, Any]) -> Post:
    external_id = str(data.get("id"))
    title = (data.get("title") or "Untitled").strip()
    post = Post.query.filter_by(external_id=external_id).first()

    if post is None:
        # Resolve the slug before adding the row so autoflush can't insert a
        # half-built record with a null slug.
        base = slugify(data.get("seo_slug") or data.get("slug") or title)
        slug = unique_slug(base, existing_slugs())
        post = Post(external_id=external_id, source="storychief", slug=slug)
        db.session.add(post)

    post.title = title
    post.body_html = sanitize_html(data.get("content"))
    post.author = extract_author(data.get("author"))
    post.category = extract_category(data.get("categories"))
    post.tags = extract_tags(data.get("tags"))
    post.image = extract_image(data.get("featured_image"))
    post.excerpt = (
        data.get("excerpt") or data.get("seo_description") or derive_excerpt(post.body_html)
    ).strip()
    parsed_date = parse_storychief_date(data.get("published_at"))
    post.published_on = parsed_date or post.published_on or date.today()

    db.session.commit()
    return post


def seed_posts_if_empty() -> None:
    if Post.query.count() > 0 or not BLOG_FILE.exists():
        return
    with BLOG_FILE.open("r", encoding="utf-8") as file:
        items = json.load(file)
    for item in items:
        db.session.add(
            Post(
                external_id=None,
                slug=item["slug"],
                title=item["title"],
                author=item.get("author", "Harbor & Key Editorial"),
                published_on=parse_storychief_date(item.get("date")) or date.today(),
                category=item.get("category", "General"),
                excerpt=item.get("excerpt", ""),
                image=item.get("image", ""),
                tags=item.get("tags", []),
                body_html=sanitize_html(text_to_html(item.get("body", ""))),
                source="seed",
            )
        )
    db.session.commit()


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
    category = request.args.get("category", "").strip()
    query = Post.query
    if category:
        query = query.filter_by(category=category)
    posts = query.order_by(Post.published_on.desc(), Post.id.desc()).all()
    categories = sorted(
        {row[0] for row in db.session.query(Post.category).distinct().all() if row[0]}
    )
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

        body_html = sanitize_html(text_to_html(body))
        if not excerpt:
            excerpt = derive_excerpt(body_html)

        slug = unique_slug(slugify(title), existing_slugs())
        post = Post(
            slug=slug,
            title=title,
            author=author,
            published_on=date.today(),
            category=category,
            excerpt=excerpt,
            image=image,
            tags=tags,
            body_html=body_html,
            source="manual",
        )
        db.session.add(post)
        db.session.commit()

        flash("Your post was published.", "success")
        return redirect(url_for("blog_detail", slug=slug))

    return render_template("blog_new.html", form={})


@app.route("/blog/<slug>")
def blog_detail(slug: str):
    post = Post.query.filter_by(slug=slug).first()
    if post is None:
        abort(404)

    related = (
        Post.query.filter(Post.category == post.category, Post.slug != slug)
        .order_by(Post.published_on.desc(), Post.id.desc())
        .limit(3)
        .all()
    )
    return render_template("blog_detail.html", post=post, related=related)


@app.route("/webhooks/storychief", methods=["POST"])
def storychief_webhook():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400
    app.logger.info("STORYCHIEF RAW PAYLOAD: %s", json.dumps(payload))
    if not verify_storychief_signature(payload):
        return jsonify({"error": "Invalid signature"}), 401

    event = (payload.get("meta") or {}).get("event")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    key = storychief_key()

    if event == "test":
        return jsonify({"id": "test", "permalink": url_for("blog", _external=True), "mac": key})

    if event == "delete":
        external_id = str(data.get("id"))
        post = Post.query.filter_by(external_id=external_id).first()
        if post is not None:
            db.session.delete(post)
            db.session.commit()
        return jsonify(
            {"id": external_id, "permalink": url_for("blog", _external=True), "mac": key}
        )

    if event in ("publish", "update"):
        if not data.get("id"):
            return jsonify({"error": "Missing article id"}), 400
        post = upsert_storychief_post(data)
        return jsonify(
            {
                "id": post.external_id,
                "permalink": url_for("blog_detail", slug=post.slug, _external=True),
                "mac": key,
            }
        )

    return jsonify({"error": f"Unhandled event: {event}"}), 400


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
    posts = Post.query.order_by(Post.published_on.desc(), Post.id.desc()).all()
    return jsonify({"count": len(posts), "posts": [post.to_dict() for post in posts]})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


with app.app_context():
    db.create_all()
    seed_posts_if_empty()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
