# contributing

hey, thanks for wanting to help out :D

make a wrapped is a small open source thing that turns your listenbrainz, last.fm, or navidrome history into a spotify wrapped style poster. it's a hobby project, not a company, so the rules are loose. just keep them in mind.

## setup

clone, venv, install, run. the short version:

```bash
git clone https://github.com/DevMatei/make-a-wrapped.git
cd make-a-wrapped
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./start.sh 0.0.0.0 5000
```

then open http://localhost:5000.

## code rules

keep it readable. clarity beats cleverness.

- follow pep8 for python.
- add type hints where they help, not everywhere.
- keep functions small and to the point.
- commit messages in the `feat:`, `fix:`, `chore:` style.
- don't commit cache or data files, .gitignore exists for a reason.
- run `python -m py_compile wrapped-fm.py` before pushing so you don't ship a syntax error.

## before you open a pr

- for big changes, open an issue first so we can agree on the direction.
- small stuff, like typos or copy fixes, can go straight to a pr.
- keep prs focused. one feature or one fix per pr, not a kitchen sink.
- if it's a ui change, attach a screenshot. i need to see what it looks like.
- fill out the pr template, i actually read it.

## where you can help

- bug reports that show how to reproduce it, plus your browser and os.
- new integrations, last.fm, navidrome, whatever you're into.
- perf ideas for the data fetching, caching, and retry logic.
- translations, i take those gladly.

## license

by contributing, you agree your changes get licensed under the same license as the project (see LICENSE).

## the vibe

this is a homelab passion project, not a product with a roadmap. i built it because i wanted a wrapped that actually cares about self-hosters. don't resell it, don't rebrand it, and don't hammer the public apis and abuse the rate limits. be nice in issues and code review, assume good faith, and remember everyone's just here for the data crunching.

that's it. if you made it this far, nice. thanks for helping make it more fun. i'm matei.
