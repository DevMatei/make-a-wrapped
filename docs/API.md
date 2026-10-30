# make a wrapped api v1

the api turns listening stats into a finished wrapped poster. send stats from a supported provider or your own json, get a png or svg back. your app doesn't have to render anything.

| | |
| --- | --- |
| **endpoint** | `POST https://wrapped.devmatei.com/api/v1/wrapped` |
| **local** | `POST http://127.0.0.1:5000/api/v1/wrapped` |
| **auth** | none, no account or api key |
| **success** | image bytes, `image/png` by default or `image/svg+xml` |
| **errors** | always json, even when you asked for an image |

**contents:** [quick start](#quick-start) · [request fields](#request-fields) · [providers](#use-a-provider) · [custom data](#custom-data) · [artwork](#artwork) · [templates](#templates) · [template catalog](#template-catalog) · [errors](#errors) · [limits](#limits) · [running it locally](#running-it-locally)

## quick start

render a poster from your own stats and save it as `wrapped.png`:

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

or straight from someone's listenbrainz:

```sh
curl --fail-with-body https://wrapped.devmatei.com/api/v1/wrapped \
  -H 'Content-Type: application/json' \
  -d '{"source": {"type": "provider", "provider": "listenbrainz", "username": "YOUR_USERNAME"}}' \
  --output wrapped.png
```

### from javascript

check `response.ok` before treating the body as an image. on failure, read the json error:

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

## request fields

| field | type | notes |
| --- | --- | --- |
| `source` | object | load stats from a provider. see [use a provider](#use-a-provider) |
| `data` | object | your own stats. see [custom data](#custom-data) |
| `template` | string | template slug, defaults to `black` |
| `format` | string | `png` (default) or `svg` |
| `artwork` | object | optional artwork lookup. see [artwork](#artwork) |

send either `source` or `data`, not both. any other top level field returns `400`.

## use a provider

provider requests reuse the site's own listenbrainz, last.fm and libre.fm integrations. the server loads the stats, finds artwork, applies the template and sends back the file.

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

| field | values | default |
| --- | --- | --- |
| `type` | `provider` | required |
| `provider` | `listenbrainz`, `lastfm`, `librefm` | required |
| `username` | the public username on that service | required |
| `range.preset` | `this_year`, `last_year`, `last_12_months`, `this_month`, `last_month`, `specific_month`, `all_time` | `this_year` |
| `range.month`, `range.year` | integers, only for `specific_month` | |
| `limit` | how many top artists and tracks, `1` to `10` | `5` |

navidrome stays browser only, because that integration keeps the server url and password on the user's device. apps that use navidrome can collect the stats themselves and send them as [custom data](#custom-data).

## custom data

pass the stats your app already has:

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

| field | type | notes |
| --- | --- | --- |
| `artists` | array of strings | up to 10 |
| `tracks` | array of strings | up to 10 |
| `minutes` | integer or string | a non-negative integer, or a display string like `"12,345"` |
| `genre` | string | |
| `period.label` | string | optional, shown on the poster |
| `artwork` | string | optional png, jpeg or webp data url, at most 32 KiB decoded |

include at least one of `artists` or `tracks`. text values can be up to 120 characters. unknown fields in `data` return `400`.

for bigger covers or covers from a service, skip `data.artwork` and use an [artwork lookup](#artwork) instead. you can't use both in one request.

## artwork

with provider stats, artwork comes from the same provider and username by default. the `artwork` object lets you change that:

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

| field | values | default |
| --- | --- | --- |
| `provider` | `listenbrainz`, `lastfm`, `librefm` | the stats provider |
| `username` | username on that service | the stats username |
| `source` | `artist` (artist image) or `release` (album cover) | `artist` |
| `fit` | `cover` (crop to fill) or `contain` (show the whole image) | `cover` |
| `range` | same shape as `source.range` | the stats range |
| `enabled` | `false` skips artwork | `true` |

with custom data there's no provider to fall back on, so pass `provider` and `username` yourself. that way an app can send its own stats and still get a matching cover:

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

artwork lookup is best effort. if the service has no image or is down, you still get the poster, just without artwork.

## templates

`template` is the slug of an official or approved community template, `black` by default. find slugs with the [template catalog](#template-catalog) or on the [template library](https://wrapped.devmatei.com/marketplace). the template's own canvas size is kept, within the render size [limits](#limits).

## template catalog

the catalog endpoints let you show the template library on your own site: list templates, page through them and embed preview images. they're read-only `GET` requests with cors on, so they work straight from the browser.

### list templates

```sh
curl 'https://wrapped.devmatei.com/api/v1/templates?limit=12&sort=popular'
```

| param | values | default |
| --- | --- | --- |
| `limit` | `1` to `50` | `20` |
| `sort` | `popular`, `newest`, `name` | `popular` |
| `origin` | `official`, `community` | all |
| `category` | `dark`, `light`, `minimal`, `vibrant`, `retro`, `abstract`, `bold`, `soft` | all |
| `featured` | `true`, `false` | all |
| `q` | search text, up to 60 characters, matched against name, slug, tags and creator | none |
| `cursor` | `page.next_cursor` from the previous response | first page |

unknown params return `400`, so a typo doesn't quietly give you the wrong list.

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

`links.use` opens the generator with that template already picked. `created_at` is `null` for official templates. `creator` can be `null`, and `creator.website` only shows up when it's an http(s) link.

### paging

pass `page.next_cursor` back as `cursor`, with the same filters and sort, to get the next page. when `has_more` is `false`, `next_cursor` is `null` and you have everything. a cursor only works with the query that made it. mix it with different filters and you get a `400`, so start again without one.

cursors point at a spot in the sorted list, not a page number, so templates added or removed between requests won't make you skip or repeat anything. the exception is `sort=popular`: use counts change all the time, so a template can jump pages while you're paging. for a complete, stable sync use `sort=newest` or `sort=name`.

### get one template

```sh
curl https://wrapped.devmatei.com/api/v1/templates/black
```

returns the same fields as the list under `template`, plus `definition`: the full template json (canvas, background, artwork slot, elements) in case you want to draw it yourself. image backgrounds come back as absolute urls.

### preview images

```html
<img
  src="https://wrapped.devmatei.com/api/v1/templates/black/preview.png?size=sm&v=506e50c0b6686ddb"
  width="360" height="640" loading="lazy" alt="Midnight template">
```

previews are pngs of the template filled with sample stats and placeholder artwork. `size` is `sm` (360px wide), `md` (540px, the default) or `lg` (1080px). height follows the template's canvas ratio.

use `links.preview` from the catalog and append `&size=sm` (or `lg`) for another size. it already includes `v`, the template version. with a matching `v` the image is cached for a year, since editing a template changes the version and so the url. without `v` it's cached for five minutes.

the first request renders the preview, after that it's served from disk. if the renderer is busy you get a `503` with `Retry-After`, so show a placeholder and retry later.

### embed example

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

### caching

catalog responses have an `ETag` and `Cache-Control: public, max-age=60` (`max-age=300` for a single template). send `If-None-Match` with the last `ETag` and you get an empty `304` when nothing changed. the server builds the catalog in memory and rebuilds it every 30 seconds (`TEMPLATE_CATALOG_TTL`), so a freshly approved template can take that long to show up.

## errors

every api error has the same json shape, including bad input, unknown api paths, rate limits and renderer failures. the status code tells you the kind of error, `error.code` and `error.message` explain it.

```json
{
  "error": {
    "code": "bad_request",
    "message": "data.artists must be an array of strings."
  }
}
```

| status | meaning | what to do |
| --- | --- | --- |
| `304` | catalog or preview unchanged since your `If-None-Match` | reuse your cached copy |
| `400` | invalid input or unsupported field | check the field names and values |
| `404` | unknown template or api path | check the slug or url |
| `413` | request body or generated image too big | send less, or try another template |
| `415` | request isn't json | send `Content-Type: application/json` |
| `422` | template assets or canvas can't be rendered | pick another template |
| `429` | rate limited, or the artwork queue is busy | wait for `Retry-After` if present, then back off |
| `500` | unexpected failure | retry later. internal details are kept out of the response |
| `502` | the provider didn't return usable stats | check the username and try again later |
| `503` | render queue full, render timed out or renderer unavailable | wait for `Retry-After` and back off |

`Retry-After` is sent for rate limits and temporary render capacity errors. please don't retry in a tight loop.

## limits

no api key needed. limits are per client ip:

| what | limit | env var |
| --- | --- | --- |
| `POST /api/v1/wrapped` | 15 per minute | `APP_IMAGE_RATE_LIMIT` |
| catalog requests | 120 per minute | `APP_CATALOG_RATE_LIMIT` |
| preview images | 240 per minute | `APP_PREVIEW_RATE_LIMIT` |

previews get a higher limit because one page of thumbnails is a lot of requests.

| size limit | value |
| --- | --- |
| json request body | 64 KiB |
| `data.artwork` | 32 KiB decoded |
| text values | 120 characters |
| template canvas | 2.5 million pixels |
| source images | 16 million pixels |
| generated file | 12 MiB |

rendering eats cpu and memory, so the server caps concurrent renders and keeps a bounded wait queue. the docker compose setup runs four gunicorn workers with eight threads each, one active render per worker, and redis backed rate limits shared between workers. requests that can't be served in time get a `503` with `Retry-After`, so retry with exponential backoff and some jitter.

## running it locally

the api renderer needs node 20+ and npm on top of the python setup. install the node dependencies, then start flask:

```sh
npm ci
./.venv/bin/python wrapped-fm.py
```

the local endpoint is `http://127.0.0.1:5000/api/v1/wrapped`. or run the docker compose setup, which serves the app on port `8000`:

```sh
docker compose up --build
```

rendered previews are cached in `data/template-previews` (`TEMPLATE_PREVIEW_DIR`).
