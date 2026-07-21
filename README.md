# Harbor & Key Realty

A fictional, Render-ready real estate website for testing UI changes, integrations, automation, APIs, forms, and deployment workflows.

## Included

- Responsive home, listings, property-detail, about, contact, and 404 pages
- Eight fictional properties stored in `data/properties.json`
- Search, filters, and sorting
- Image gallery lightbox
- JSON endpoints:
  - `GET /api/properties`
  - `GET /api/properties/<id>`
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

## Contact form behavior

The demo validates the form and logs a minimal server-side event, but it does not save the message. Connect the handler in `app.py` to your CRM, database, email provider, or webhook.

## Important

All brokerage details, addresses, prices, phone numbers, and property records are fictional. The project uses externally hosted demo photography, so images require an internet connection.
