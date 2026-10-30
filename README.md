<div align="center">

# 🎧 make a wrapped

**spotify wrapped style recaps for listenbrainz, last.fm, libre.fm and navidrome.**<br>
free, open source, no account, and you don't have to wait for december.

<a href="https://github.com/DevMatei/make-a-wrapped/stargazers"><img src="https://img.shields.io/github/stars/DevMatei/make-a-wrapped?style=for-the-badge&labelColor=1a1625&color=c084fc&logo=github&logoColor=c084fc" alt="stars"></a>
<a href="https://github.com/DevMatei/make-a-wrapped/network/members"><img src="https://img.shields.io/github/forks/DevMatei/make-a-wrapped?style=for-the-badge&labelColor=1a1625&color=c084fc&logo=git&logoColor=c084fc" alt="forks"></a>
<a href="https://github.com/DevMatei/make-a-wrapped/issues"><img src="https://img.shields.io/github/issues/DevMatei/make-a-wrapped?style=for-the-badge&labelColor=1a1625&color=c084fc" alt="issues"></a>
<a href="https://github.com/DevMatei/make-a-wrapped/commits"><img src="https://img.shields.io/github/last-commit/DevMatei/make-a-wrapped?style=for-the-badge&labelColor=1a1625&color=c084fc" alt="last commit"></a>
<a href="./LICENSE"><img src="https://img.shields.io/badge/license-agpl--3.0-c084fc?style=for-the-badge&labelColor=1a1625" alt="license agpl-3.0"></a>
<br>
<a href="https://wrapped.devmatei.com"><img src="https://img.shields.io/badge/live-wrapped.devmatei.com-c084fc?style=for-the-badge&labelColor=1a1625&logo=googlechrome&logoColor=c084fc" alt="live site"></a>
<a href="https://wrapped.devmatei.com"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fwrapped.devmatei.com%2Fmetrics%2Fwrapped&query=%24.count&label=wraps%20made&style=for-the-badge&labelColor=1a1625&color=c084fc" alt="wraps made"></a>
<a href="https://discord.gg/ucFGpJdznF"><img src="https://img.shields.io/badge/discord-join-c084fc?style=for-the-badge&labelColor=1a1625&logo=discord&logoColor=c084fc" alt="discord"></a>
<br>
<a href="https://ko-fi.com/F1F016B4WM"><img src="https://img.shields.io/badge/ko--fi-buy%20me%20a%20coffee-ff5e5b?style=for-the-badge&labelColor=1a1625&logo=kofi&logoColor=ff5e5b" alt="support on ko-fi"></a>
<a href="https://sponsor.devmatei.com/"><img src="https://img.shields.io/badge/ads-your%20project%20here-c084fc?style=for-the-badge&labelColor=1a1625" alt="advertise here"></a>

<a href="https://wrapped.devmatei.com"><b>make yours</b></a> ·
<a href="./docs/API.md"><b>api docs</b></a> ·
<a href="#-templates-beta"><b>templates</b></a> ·
<a href="#-quickstart"><b>self-host</b></a> ·
<a href="#-support-it"><b>support it</b></a>

there's a [discord](https://discord.gg/ucFGpJdznF) too, come say hi, post your wrapped, report bugs, whatever

<br>

<img width="900" alt="Make a Wrapped website, showing the wrapped generator and poster preview" src="image.png" />

</div>

## 💡 why it's cool

* pulls from ListenBrainz, Last.fm, Libre.fm, Navidrome, MusicBrainz, Cover Art Archive, and Wikidata. all public, no tokens needed (except the optional Last.fm key you'd already have for artwork anyway)
* artist art tries Last.fm first, falls back to MusicBrainz/Wikidata, and if all else fails there's a built-in editor to upload/zoom/position your own image (saved in local storage, or temporarily on the server for 1 hour)
* a data-driven template system, so the built-in themes and community templates all render from the same format
* a [template library](https://wrapped.devmatei.com/marketplace) to browse featured/newest/popular templates and use any of them, plus a [visual editor](https://wrapped.devmatei.com/editor) so artists can design their own Wrapped poster without knowing the format - both still in **beta**
* rate limits are in so your server doesn't get nuked
* there's a live counter of total wraps ever generated (idk it seemed cool)
* officially listed on the [ListenBrainz Enabled Applications](https://wiki.musicbrainz.org/ListenBrainz_Enabled_Applications) page :D

> [!NOTE]
> **libre.fm** integration is marked **beta/unstable**. the service throttles hard per IP and its API is less predictable than last.fm, so wrapped generation can be slower or occasionally flaky. treat it as experimental.

## 🏷️ readme badges

put your top artist in your github profile / website. live shields-style SVG, cached server-side so it won't nuke anything:

```markdown
![top artist](https://wrapped.devmatei.com/badge/YOUR_USERNAME)
```

options via query params:

* `type` - `artist` (default), `track`, `genre`, `minutes`
* `service` - `listenbrainz` (default), `lastfm`, or `librefm`
* `range` - any period preset, e.g. `this_month`, `this_year`, `all_time`
* `color` - hex without the `#`, e.g. `color=ff6b9d`

```markdown
![minutes](https://wrapped.devmatei.com/badge/YOUR_USERNAME?type=minutes&service=lastfm&range=this_month&color=ff6b9d)
```

**navidrome badges** work differently since your server credentials never touch this app: generate your wrapped, hit "copy readme badge", and the browser publishes just the final numbers (top artist/track/genre/minutes, nothing else) under a private key stored in your browser. the badge URL stays stable across regenerations, only you can update it, and snapshots expire after 60 days unless refreshed.

## 🔌 developer api (beta)

generate and download server-rendered wrapped posters from supported providers or your own stats. start with the [api developer guide](./docs/API.md) for request examples, templates, artwork options and error handling.

## ☕ support it

make a wrapped is free, has no paywalls and no accounts, and it's going to stay that way. it runs on my homelab, which still costs power, a domain and a lot of my free time (i'm broke lol). if it gave you a good wrapped, a coffee genuinely helps keep it online.

<a href="https://ko-fi.com/F1F016B4WM"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="support me on ko-fi"></a>

no money? a ⭐ on the repo, a bug report, or posting your wrapped in the [discord](https://discord.gg/ucFGpJdznF) helps too.

## 📣 advertise here

there's a small ad slot on the site and it's cheap. if you've got a project, a tool or a server music nerds would like, [grab a spot on sponsor.devmatei.com](https://sponsor.devmatei.com/). it shows up next to the generator and the money goes straight into hosting.

## ⚡ quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

copy `.env.example` to `.env` and fill in the basics:

```
FLASK_ENV=production
SECRET_KEY=<something>
LASTFM_API_KEY=<your-lastfm-key>
# set HTTP_PROXY / HTTPS_PROXY if you tunnel through a proxy
```

run it:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 wrapped-fm:app
```

or locally:

```bash
./start.sh <host> <port>
```

or with Docker (change the port in the compose file first):

```bash
sudo docker compose up -d
```

## ⚙️ config

### core

`LISTENBRAINZ_API=https://api.listenbrainz.org/1`
`MUSICBRAINZ_API`, `COVER_ART_API`
`LISTENBRAINZ_RANGE=this_year`
`AVERAGE_TRACK_LENGTH_MINUTES`, `COVER_ART_LOOKUP_LIMIT`

### integrations

`LASTFM_API_KEY` - required for Last.fm stats + better artist images
`LASTFM_API`, `LASTFM_USER_AGENT`

### performance

`HTTP_TIMEOUT`, `HTTP_POOL_MAXSIZE`, `LISTENBRAINZ_CACHE_TTL`, `LISTENBRAINZ_CACHE_SIZE`
`APP_RATE_LIMIT`, `APP_STATS_RATE_LIMIT`, `APP_IMAGE_RATE_LIMIT`, `APP_MAX_TOP_RESULTS`
`APP_IMAGE_CONCURRENCY`, `APP_IMAGE_QUEUE_LIMIT`, `APP_IMAGE_QUEUE_TIMEOUT`
`TEMP_ARTWORK_TTL_SECONDS`, `TEMP_ARTWORK_MAX_BYTES`
`COUNTER_DB` (defaults to `data/counters.db`) - sqlite file for the wrapped counter and template uses. the old `WRAPPED_COUNT_FILE` and `data/template-uses.json` get imported once on first start, so old counts are kept
`NODE_ID`, `CLUSTER_PEERS`, `CLUSTER_PRIMARY`, `CLUSTER_SECRET`, `CLUSTER_SYNC_INTERVAL` - only for running more than one server, see below
`WRAPPED_COUNT_SINCE` - label for when you started counting wraps (ISO date string)
`APP_RATE_LIMIT_SALT`, `APP_TRUST_PROXY_HEADERS`
`BADGE_CACHE_TTL` (seconds, default 6h), `BADGE_CACHE_SIZE`
`BADGE_SNAPSHOT_DIR`, `BADGE_SNAPSHOT_TTL_SECONDS` (default 60 days), `BADGE_SNAPSHOT_MAX_COUNT`

### running more than one server

handy if you want a backup box for when the main one goes down. leave all of this empty for a single server.

- every box gets its own `NODE_ID` and the same `CLUSTER_SECRET`
- `CLUSTER_PEERS` is the other boxes' base urls, comma separated. use private addresses (tailscale, wireguard), not the public site url, or a box can end up talking to itself
- one box is the primary. it owns template submissions, uploads and the review desk. every other box sets `CLUSTER_PRIMARY` to the primary's url

what syncs:

- the wrapped counter and template uses. each box counts its own and pulls the others about once a minute, so totals match and nothing is lost if a box is down
- uploaded artwork and navidrome badges. a box that doesn't have one asks the others
- approved templates and their images get copied from the primary. submissions and reviews on other boxes get forwarded to it. while the primary is down, wrapped generation keeps working and submissions say to try again later

boxes talk over `/internal/*` with the secret. nothing in there is useful to the public, so you can also block that path at your proxy.

## 🎨 templates (beta)

templates live as little JSON documents in `static/templates/` (official) and `data/templates/` (approved community). the renderer consumes the same format, so anything the editor makes runs everywhere the built-in themes do. the marketplace, editor and submission flow are still **beta** - expect rough edges.

* `/templates` - a page that explains what templates are and how to use them.
* `/marketplace` - browse templates. search, filter by category, sort by featured/newest/popular, and hit "use this template" to jump straight into the generator. you can also export any template as JSON.
* `/editor` - the visual template editor. position, resize and configure text, lists, stats, background and artwork on a live Wrapped canvas, then submit it for review. export/import templates as JSON to share them.
* `/admin` - moderation. community submissions land in a `pending_review` state and only appear publicly after a maintainer approves them.

creators are attributed by a key held in their browser (the same kind of ownership mechanism the badge snapshots use), so the same artist can submit many templates without re-registering, and nobody can casually claim someone else's identity. to enable the review API set `TEMPLATE_REVIEW_KEY` (see `.env.example`); leave it empty to disable moderation entirely.

## 🤝 contributing

see [CONTRIBUTING.md](./.github/CONTRIBUTING.md) for setup, style notes and the pr checklist. tl;dr: keep prs focused, run `python -m py_compile wrapped-fm.py`, and attach screenshots for any ui changes.

## 🧩 to-do

* [x] security improvements
* [x] faster rendering (capped around 33s by api speeds, not much i can do)
* [x] modular, readable code (kind of)

## 🙋 why it exists

i self-host my music library on navidrome and don't use spotify, but all my friends post their wrapped every year and everyone's like "wait what's that?" when you show them a listenbrainz stats page. so i built this. same vibe, works with open music platforms.

originally made for last.fm only by [jeff parla](https://github.com/parlajatwit) <3

### about me

i'm matei ([devmatei](https://devmatei.com)), full-stack dev from moldova. i build random web tools, run a homelab full of self-hosted stuff, and care way too much about my music library. check out my other projects at [devmatei.com](https://devmatei.com) or hit me up on socials if you wanna talk projects or self-hosting.

## ⭐ star history

<div align="center">

<a href="https://www.star-history.com/?repos=devmatei%2Fmake-a-wrapped&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=devmatei/make-a-wrapped&type=date&theme=dark&legend=top-left&sealed_token=hqKtGOCKpuhqdJ4EGwzj7IO3Br7w8APo1cS5gbEa2Qjc09c7d_5G0LbhnmPzV7xYM1VVayE0IifWD_IUBifA5HSAdm33mKRu8nmp43tqSyUbOshG1oHCug" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=devmatei/make-a-wrapped&type=date&legend=top-left&sealed_token=hqKtGOCKpuhqdJ4EGwzj7IO3Br7w8APo1cS5gbEa2Qjc09c7d_5G0LbhnmPzV7xYM1VVayE0IifWD_IUBifA5HSAdm33mKRu8nmp43tqSyUbOshG1oHCug" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=devmatei/make-a-wrapped&type=date&legend=top-left&sealed_token=hqKtGOCKpuhqdJ4EGwzj7IO3Br7w8APo1cS5gbEa2Qjc09c7d_5G0LbhnmPzV7xYM1VVayE0IifWD_IUBifA5HSAdm33mKRu8nmp43tqSyUbOshG1oHCug" />
 </picture>
</a>

</div>

## 📜 license

agpl-3.0, share alike. see [LICENSE](./LICENSE).

not affiliated with spotify, listenbrainz, last.fm, navidrome or musicbrainz. just a fan thing built for fun.

<div align="center">
<br>
<sub>made with too many scrobbles by <a href="https://devmatei.com">devmatei</a> · <a href="https://wrapped.devmatei.com">wrapped.devmatei.com</a> · <a href="https://ko-fi.com/F1F016B4WM">ko-fi</a> · <a href="https://discord.gg/ucFGpJdznF">discord</a></sub>
</div>
