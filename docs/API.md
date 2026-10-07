# Make a Wrapped API v1

The API turns listening stats into a finished Wrapped poster. Send stats from a supported provider or your own JSON, and the server returns a PNG or SVG. Your app does not need to render the poster.

- **Endpoint:** `POST https://wrapped.devmatei.com/api/v1/wrapped`
- **Local endpoint:** `POST http://127.0.0.1:5000/api/v1/wrapped`
- **Authentication:** no account or API key
- **Success response:** image bytes (`image/png` by default, or `image/svg+xml`)
- **Error response:** JSON, including when the requested output is an image

## Quick start

This example creates a poster from custom stats and saves the returned PNG to `wrapped.png`:

```sh
curl --fail-with-body https://wrapped.devmatei.com/api/v1/wrapped \
  -H 'Content-Type: application/json' \
  -d '{
    "template": "black",
    "data": {
      "artists": ["Artist One", "Artist Two"],
      "tracks": ["Track One", "Track Two"],
      "minutes": 12345,
      "genre": "Indie rock",
      "period": {"label": "2025"}
    },
    "format": "png"
  }' \
  --output wrapped.png
```

On success, the response has `Content-Type: image/png` and a download filename. Use `"format": "svg"` for `Content-Type: image/svg+xml`. If `format` is omitted, the API returns PNG.

## Handle the response in an app

Check `response.ok` before treating the body as an image. On failure, parse the JSON error and use its message. On success, save or display the returned image bytes:

```js
const response = await fetch("https://wrapped.devmatei.com/api/v1/wrapped", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    template: "black",
    data: {
      artists: ["Artist One", "Artist Two"],
      tracks: ["Track One"],
      minutes: 12345,
      genre: "Indie rock",
      period: { label: "2025" }
    },
    format: "png"
  })
});

if (!response.ok) {
  const result = await response.json().catch(() => null);
  const apiError = result?.error;
  const message = apiError
    ? `${apiError.code}: ${apiError.message}`
    : `Request failed with HTTP ${response.status}`;
  throw new Error(message);
}

const image = await response.blob();
```

## Use an existing provider

Provider requests reuse the project's existing ListenBrainz, Last.fm, or Libre.fm integrations. The server loads stats, finds available artwork, applies the selected template, and returns the rendered file.

```sh
curl --fail-with-body https://wrapped.devmatei.com/api/v1/wrapped \
  -H 'Content-Type: application/json' \
  -d '{
    "template": "pink",
    "source": {
      "type": "provider",
      "provider": "listenbrainz",
      "username": "YOUR_LISTENBRAINZ_USERNAME",
      "range": {"preset": "this_year"},
      "limit": 5
    },
    "format": "png"
  }' \
  --output listenbrainz-wrapped.png
```

Set `provider` to `listenbrainz`, `lastfm`, or `librefm`. Set `username` to the public username for that service. `limit` controls how many top artists and tracks are requested; it accepts an integer from 1 to 10 and defaults to 5.

Supported `range.preset` values are `this_year` (default), `last_year`, `last_12_months`, `this_month`, `last_month`, `specific_month`, and `all_time`. For `specific_month`, also pass integer `month` and `year` fields.

Navidrome remains browser-only because its integration keeps the server URL and password on the user's device. Apps that use Navidrome can send their own stats through the `data` field instead. For example, replace the provider object above with:

```json
{
  "data": {
    "artists": ["Artist One", "Artist Two"],
    "tracks": ["Track One", "Track Two"],
    "minutes": 12345,
    "genre": "Indie rock",
    "period": {"label": "2025"}
  }
}
```

## Custom data format

Pass the data your app has already collected. Include at least one of `artists` or `tracks`. Each list accepts up to 10 strings. `minutes` can be a non-negative integer or a display string such as `"12,345"`. `genre` is a string. `period` is optional and currently accepts a `label` string.

```json
{
  "template": "black",
  "data": {
    "artists": ["Artist One", "Artist Two"],
    "tracks": ["Track One", "Track Two"],
    "minutes": 12345,
    "genre": "Indie rock",
    "period": {"label": "2025"}
  },
  "format": "png"
}
```

The API validates every field and rejects unknown data fields. `artwork` can be a PNG, JPEG, or WebP data URL when your app already has a cover image. Its decoded size must be at most 32 KiB. For larger or provider-hosted covers, use the artwork lookup options below.

## Select artwork

For provider stats, artwork defaults to the same provider and username. You can choose a different supported provider, use an artist image or release cover, and set how the image fits the template artwork slot:

```json
{
  "template": "black",
  "source": {
    "type": "provider",
    "provider": "listenbrainz",
    "username": "YOUR_LISTENBRAINZ_USERNAME"
  },
  "artwork": {
    "provider": "lastfm",
    "source": "release",
    "fit": "cover"
  },
  "format": "png"
}
```

`artwork.provider` accepts `listenbrainz`, `lastfm`, or `librefm`. `artwork.source` accepts `artist` or `release`; it defaults to `artist`. `artwork.fit` accepts `cover` (crop to fill, the default) or `contain` (show the full image).

With custom stats, provide the artwork lookup username too. This lets an app submit its own stats and ask Last.fm or ListenBrainz for a matching cover:

```json
{
  "data": {
    "artists": ["Artist One"],
    "tracks": ["Track One"],
    "minutes": 12345,
    "genre": "Indie rock"
  },
  "artwork": {
    "provider": "listenbrainz",
    "username": "YOUR_LISTENBRAINZ_USERNAME",
    "source": "artist"
  },
  "format": "png"
}
```

Artwork lookup is best effort. If the service has no image or is temporarily unavailable, the API still generates the poster without artwork. Set `"enabled": false` to skip provider artwork.

## Choose a template

The `template` field is an official or approved community template slug. It defaults to `black`. Use the template catalog below to find slugs. Existing template dimensions are preserved, subject to the API render size limit.

## Template catalog

The catalog endpoints let you show the template library on your own site: list templates, page through them, and embed preview images. They are read-only `GET` requests with CORS enabled, so they work straight from the browser.

### List templates

```sh
curl 'https://wrapped.devmatei.com/api/v1/templates?limit=12&sort=popular'
```

| Parameter | Values | Default |
| --- | --- | --- |
| `limit` | `1` to `50` | `20` |
| `sort` | `popular`, `newest`, `name` | `popular` |
| `origin` | `official`, `community` | all |
| `category` | `dark`, `light`, `minimal`, `vibrant`, `retro`, `abstract`, `bold`, `soft` | all |
| `featured` | `true`, `false` | all |
| `q` | search text, up to 60 characters, matched against name, slug, tags and creator | none |
| `cursor` | `page.next_cursor` from the previous response | first page |

Unknown parameters return `400`, so typos don't silently return the wrong list.

```json
{
  "templates": [
    {
      "slug": "black",
      "name": "Midnight",
      "origin": "official",
      "category": "dark",
      "tags": ["dark", "classic"],
      "featured": true,
      "uses": 260,
      "created_at": null,
      "creator": {"id": "official", "name": "Make a Wrapped", "website": "https://wrapped.devmatei.com"},
      "canvas": {"width": 1080, "height": 1920},
      "version": "506e50c0b6686ddb",
      "links": {
        "self": "https://wrapped.devmatei.com/api/v1/templates/black",
        "preview": "https://wrapped.devmatei.com/api/v1/templates/black/preview.png?v=506e50c0b6686ddb",
        "use": "https://wrapped.devmatei.com/?template=black"
      }
    }
  ],
  "page": {"limit": 12, "count": 1, "total": 9, "has_more": true, "next_cursor": "eyJzIjoi..."},
  "query": {"sort": "popular"}
}
```

`links.use` opens the generator with that template already selected. `created_at` is `null` for official templates. `creator` can be `null`, and `creator.website` is only included when it is an http(s) link.

### Paging

Pass `page.next_cursor` back as `cursor` with the same filters and sort to get the next page. When `has_more` is `false`, `next_cursor` is `null` and you have everything. A cursor only works with the query that produced it; mixing it with different filters returns `400`, so start again without a cursor.

Cursors point at a position in the sorted list rather than a page number, so templates being added or removed between requests won't make you skip or repeat items. The exception is `sort=popular`: use counts change all the time, so a template can move between pages while you are paging. If you need a complete, stable sync, use `sort=newest` or `sort=name`.

### Get one template

```sh
curl https://wrapped.devmatei.com/api/v1/templates/black
```

Returns the same fields as the list under `template`, plus `definition`: the full template JSON (canvas, background, artwork slot, elements) in case you want to draw it yourself. Image background paths are returned as absolute URLs.

### Preview images

```html
<img
  src="https://wrapped.devmatei.com/api/v1/templates/black/preview.png?size=sm&v=506e50c0b6686ddb"
  width="360" height="640" loading="lazy" alt="Midnight template">
```

Previews are PNGs of the template filled with sample stats and placeholder artwork. `size` is `sm` (360px wide), `md` (540px, the default) or `lg` (1080px). Height follows the template's canvas ratio.

Use `links.preview` from the catalog, and append `&size=sm` if you want a different size. It includes `v`, the template version. With a matching `v`, the image is cached for a year, since a template edit changes the version and therefore the URL. Without `v`, the image is cached for five minutes.

The first request for a preview renders it; after that it is served from disk. If the renderer is busy, you get `503` with `Retry-After`. Show a placeholder and retry later.

### Embed example

```js
async function loadTemplates(cursor) {
  const url = new URL("https://wrapped.devmatei.com/api/v1/templates");
  url.searchParams.set("limit", "12");
  url.searchParams.set("sort", "newest");
  if (cursor) url.searchParams.set("cursor", cursor);

  const response = await fetch(url);
  if (!response.ok) {
    const { error } = await response.json().catch(() => ({}));
    throw new Error(error ? error.message : `HTTP ${response.status}`);
  }
  return response.json();
}

const grid = document.querySelector("#templates");
let cursor = null;

async function showMore() {
  const { templates, page } = await loadTemplates(cursor);
  for (const template of templates) {
    const link = document.createElement("a");
    link.href = template.links.use;
    const img = document.createElement("img");
    img.src = `${template.links.preview}&size=sm`;
    img.alt = template.name;
    img.loading = "lazy";
    link.append(img, template.name);
    grid.append(link);
  }
  cursor = page.next_cursor;
  document.querySelector("#more").hidden = !page.has_more;
}
```

### Caching

Catalog responses carry an `ETag` and `Cache-Control: public, max-age=60` (`max-age=300` for a single template). Send `If-None-Match` with the last `ETag` to get an empty `304` when nothing changed. The server builds the catalog in memory and refreshes it every 30 seconds (`TEMPLATE_CATALOG_TTL`), so a newly approved template can take that long to show up.

## Errors

Every API error has a JSON body with a stable shape, including invalid requests, missing API paths, rate limits, and renderer failures. The status code identifies the class of error; `error.code` and `error.message` explain it.

```json
{
  "error": {
    "code": "bad_request",
    "message": "data.artists must be an array of strings."
  }
}
```

| Status | Meaning | What to do |
| --- | --- | --- |
| `400` | Invalid input or unsupported field | Check the JSON schema and field values. |
| `304` | Catalog or preview unchanged since your `If-None-Match` | Reuse your cached copy. |
| `404` | Unknown template or API path | Check the template slug or endpoint URL. |
| `413` | Request body or generated image exceeds its size limit | Send a smaller request or use another template. |
| `415` | Request is not JSON | Send `Content-Type: application/json`. |
| `422` | Template assets or canvas cannot be rendered | Select another available template. |
| `429` | Rate limit or artwork service queue is busy | Respect `Retry-After` when present, then retry with backoff. |
| `502` | Provider did not return usable stats | Check the username and try again later. |
| `503` | Render queue is full, render timed out, or renderer is unavailable | Respect `Retry-After` and retry with backoff. |
| `500` | Unexpected generation failure | Retry later; internal details are kept out of the response. |

The server returns `Retry-After` for rate limiting and temporary render capacity errors. Clients should avoid immediate retry loops.

## Limits and deployment notes

No API key is required. Requests are limited per client IP: `POST /api/v1/wrapped` by the image rate limit, 15 per minute by default (`APP_IMAGE_RATE_LIMIT`), catalog requests at 120 per minute (`APP_CATALOG_RATE_LIMIT`), and preview images at 240 per minute (`APP_PREVIEW_RATE_LIMIT`). The preview limit is higher because a single page of thumbnails makes many requests. Rendered previews are cached in `data/template-previews` (`TEMPLATE_PREVIEW_DIR`). JSON request bodies are limited to 64 KiB. Templates are capped at 2.5 million canvas pixels, source images at 16 million pixels, and generated files at 12 MiB.

Rendering uses CPU and memory, so the server limits concurrent renders and keeps a bounded wait queue. Docker Compose runs four Gunicorn workers with eight request threads each, one active render per worker, and Redis-backed rate limits shared between workers. Requests that cannot be served in a reasonable time receive `503` with `Retry-After`; clients should retry with exponential backoff and jitter. These limits protect the service during bursts, but no finite server can promise zero errors during unlimited traffic.

For local development, the API renderer needs Node.js 20 or newer and npm. Install the Node dependencies with `npm ci`, then start Flask:

```sh
./.venv/bin/python wrapped-fm.py
```

To run the Docker Compose deployment locally instead:

```sh
docker compose up --build
```

The local Flask endpoint is `http://127.0.0.1:5000/api/v1/wrapped`; Docker Compose exposes the app on port `8000`.
