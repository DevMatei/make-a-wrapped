# Contributing

Thanks for considering a contribution to Make a Wrapped. This guide covers the project workflow and a few expectations for changes.

## Branches

| Branch | Purpose |
| --- | --- |
| `develop` | Main development branch. Base work here and target pull requests here. Pushes build the `:develop` Docker image. |
| `main` | Release branch. Releases are merged from `develop` and tagged `vX.Y.Z`; Docker builds publish `:latest` and versioned tags. |

## Setup

You need Python 3 and, for the API or template previews, Node.js 20 or later.

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

Open http://localhost:5000. Last.fm stats require `LASTFM_API_KEY` in `.env`; other services work without it. See the [README configuration section](../README.md) for other settings.

## Checks

Before opening a pull request, run:

```bash
python -m py_compile wrapped-fm.py
python -m unittest discover -s wrapped_fm/tests -t .
```

## Code guidelines

- Prefer clear, direct code over clever abstractions.
- Follow PEP 8 for Python. Add type hints where they make the code easier to understand.
- Keep functions focused. Validate external input and handle expected failures and edge cases cleanly.
- Add comments when they explain a non-obvious reason. Avoid comments that merely restate the code.
- Keep changes focused and consistent with the surrounding code.
- Use short, lowercase commit messages that describe the change. See `git log` for examples.
- Do not commit cache or data files.

## AI tools

You may use AI tools while working on a contribution. You are responsible for the result: review the code, understand what it does, and be ready to explain your changes. Run the relevant checks and correct any problems before submitting.

Review AI-generated changes for project conventions, security, input validation, and failure handling. Remove unnecessary comments, especially comments that just narrate the code. Keep useful comments that explain why something is done.

This reflects my view too: tools are fine, but contributors should understand the code they submit. See [Linus Torvalds's email on AI and understanding contributions](https://lore.landau.one/lkml/CAHk-%3DwhTs09_ozN%2Be09GU68N1wPP56MUzDjrg9rnKxQUa0A_4Q%40mail.gmail.com/).

## Pull requests

- Target `develop`, not `main`.
- For a larger change, open an issue first to discuss the direction. Small fixes, such as typos, can go straight to a pull request.
- Keep each pull request focused on one feature or fix.
- Include a screenshot for user interface changes.
- Fill out the pull request template.

## Contributions to consider

- Bug reports with reproduction steps, browser, and operating system.
- Support for additional scrobblers.
- New templates. Templates can be created in the [editor](https://wrapped.devmatei.com/editor) and submitted without a pull request.
- Improvements to data fetching, caching, or retries.

For questions or ideas, use the [Discord](https://discord.gg/ucFGpJdznF).

## Security

Do not report vulnerabilities in a public issue. Follow the instructions in [SECURITY.md](../SECURITY.md).

## License

Contributions are licensed under the project's [AGPL-3.0 license](../LICENSE).
