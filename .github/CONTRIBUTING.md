# contributing

hey, thanks for wanting to help out :D

make a wrapped turns your listenbrainz, last.fm, libre.fm or navidrome history into a spotify wrapped style poster. it's a hobby project, not a company, so the rules are loose. just keep these in mind.

## branches

| branch | what it is |
| --- | --- |
| `develop` | where work happens. branch off it and open your pr back into it. every push builds a `:develop` docker image |
| `main` | the release line. only gets merges from `develop`, and each release is a `vX.Y.Z` tag on top. docker `:latest` and versioned tags build from it |

## setup

you need python 3 and, if you touch the api or template previews, node 20+.

```bash
git clone https://github.com/DevMatei/make-a-wrapped.git
cd make-a-wrapped
git checkout develop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm ci
cp .env.example .env
python wrapped-fm.py
```

then open http://localhost:5000. last.fm stats need a `LASTFM_API_KEY` in `.env`, the other services work without one. every other setting is listed in the config section of the [readme](../README.md).

## checks

run these before you push:

```bash
python -m py_compile wrapped-fm.py
python -m unittest discover -s wrapped_fm/tests -t .
```

## code rules

clarity beats cleverness.

- pep8 for python.
- type hints where they help, not everywhere.
- small functions that do one thing.
- comments only where the why isn't obvious.
- short, lowercase commit messages that say what changed, like `fix template preview 404 for names with underscores`. check `git log` for the vibe.
- don't commit cache or data files, `.gitignore` exists for a reason.

## before you open a pr

- prs go into `develop`, not `main`.
- for big changes, open an issue first so we can agree on the direction. small stuff like typos can go straight to a pr.
- one feature or one fix per pr, not a kitchen sink.
- ui change? attach a screenshot, i need to see it.
- fill out the pr template, i actually read it.

## where you can help

- bug reports with steps to reproduce, plus your browser and os.
- support for scrobblers it doesn't cover yet.
- new templates. make one in the [editor](https://wrapped.devmatei.com/editor) and submit it, no pr needed.
- perf ideas for data fetching, caching and retries.

questions or ideas? the [discord](https://discord.gg/ucFGpJdznF) is the fastest way to reach me.

## security

found a vulnerability? don't open a public issue, see [SECURITY.md](../SECURITY.md).

## license

by contributing, you agree your changes are licensed under the project's [agpl-3.0](../LICENSE) license.

## the vibe

this is a homelab passion project, not a product with a roadmap. i built it because i wanted a wrapped that actually cares about self-hosters. don't resell it, don't rebrand it, and don't hammer the public apis or abuse the rate limits. be nice in issues and reviews, assume good faith, and remember everyone's just here for the data crunching.

that's it. if you made it this far, nice. thanks for helping make it more fun. i'm matei.
