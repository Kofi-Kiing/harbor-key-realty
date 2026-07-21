# Harbor & Key Realty

A fictional, Render-ready real estate website for testing UI changes, integrations, automation, APIs, forms, and deployment workflows.

## Included

- Responsive home, listings, property-detail, about, contact, blog, and 404 pages
- Eight fictional properties stored in `data/properties.json`
- A blog with sample posts in `data/blog_posts.json` and an open form to publish new posts
- Search, filters, and sorting
- Image gallery lightbox
- JSON endpoints:
  - `GET /api/properties`
  - `GET /api/properties/<id>`
  - `GET /api/posts`
  - `GET /api/health`
- Render Blueprint configuration
- Gunicorn production server

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

## Deploy to Render

### Blueprint method

1. Push this folder to a GitHub repository.
2. In Render, create a new Blueprint.
3. Select the repository.
4. Render will read `render.yaml` and create the web service.

### Manual web-service method

Use:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn app:app`
- **Health check path:** `/api/health`

## Testing the API

```bash
curl http://localhost:5000/api/health
curl "http://localhost:5000/api/properties?city=Portland&beds=3"
curl http://localhost:5000/api/properties/1
```

Supported query parameters for `/api/properties`:

- `q`
- `city`
- `type`
- `beds`
- `min_price`
- `max_price`
- `sort`: `featured`, `price_asc`, `price_desc`, or `sqft_desc`

## Replace the fake listings

Edit `data/properties.json`. Keep each property's `id` and `slug` unique.

## Blog

- Read posts at `/blog`, filter by category, and open a post at `/blog/<slug>`.
- Publish a new post at `/blog/new`. Only a title and body are required; author, category, cover image, tags, and excerpt are optional (the excerpt is auto-generated from the body if left blank).
- Posts are stored in a **database** via SQLAlchemy. Locally this defaults to a SQLite file at `data/blog.db`; in production set `DATABASE_URL` (Render Postgres is wired up automatically in `render.yaml`).
- On first run against an empty database, the sample posts in `data/blog_posts.json` are seeded automatically. That JSON file is only a seed — after the first run, posts live in the database.
- Post bodies are stored as HTML and sanitized with [`nh3`](https://pypi.org/project/nh3/) before rendering, so third-party content (including StoryChief articles) cannot inject scripts.
- The `/blog` page also shows a **Featured articles** section, edited in `data/featured_articles.json`. Each entry is either `"type": "internal"` (link to a post on this site via its `slug`) or `"type": "external"` (link to an outside `url`), with an optional `blurb` and `source` label.

## Environment variables

- `SECRET_KEY` — Flask session/flash signing key.
- `DATABASE_URL` — database connection string. Defaults to SQLite (`data/blog.db`) when unset. A `postgres://` prefix is normalized to `postgresql://` automatically.
- `STORYCHIEF_WEBHOOK_KEY` — the encryption key from your StoryChief Custom Website destination (required for the StoryChief integration).

## StoryChief integration

StoryChief can publish articles straight into the blog through its **Custom Website** webhook. When an article is published, updated, or deleted in StoryChief, it sends a signed `POST` to this app, which verifies the signature and writes the post to the database.

**Endpoint:** `POST /webhooks/storychief`

The endpoint verifies StoryChief's HMAC-SHA256 signature (`meta.mac`) using `STORYCHIEF_WEBHOOK_KEY`, handles the `test`, `publish`, `update`, and `delete` events, and returns `{ id, permalink, mac }`. StoryChief stores the returned `id` as the `external_id` for future updates and deletes.

### One-time setup

1. Deploy the app (the `render.yaml` blueprint provisions a Postgres database and the `STORYCHIEF_WEBHOOK_KEY` variable).
2. In StoryChief, open **Integrations -> Personal Website -> Custom Website -> Add New Destination**.
3. Copy the generated **encryption key** and set it as `STORYCHIEF_WEBHOOK_KEY` on your host, then redeploy/restart.
4. Enter the endpoint URL `https://<your-domain>/webhooks/storychief` and save. StoryChief sends a `test` event, which must return `200`.
5. Publish an article to that channel — it will appear at `/blog`.

## Contact form behavior

The demo validates the form and logs a minimal server-side event, but it does not save the message. Connect the handler in `app.py` to your CRM, database, email provider, or webhook.

## Important

All brokerage details, addresses, prices, phone numbers, and property records are fictional. The project uses externally hosted demo photography, so images require an internet connection.
