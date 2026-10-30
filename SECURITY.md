# security policy

## reporting a vulnerability

found a security issue in make a wrapped? please report it privately so it can be fixed before it's public.

- [report it on github](https://github.com/DevMatei/make-a-wrapped/security/advisories/new) (recommended). private vulnerability reporting is on, so it stays private until it's published.
- or email [hello@devmatei.com](mailto:hello@devmatei.com).

please **don't** open a public issue, pr, discord message or forum post about it before it's been looked at and fixed.

## what to include

short but complete is perfect:

- the affected url, endpoint or component
- steps to reproduce
- the impact (what an attacker could get)
- a proof of concept, screenshots or logs, if you have them
- how you'd like to be credited, if at all

data leaks, auth bypasses, injection, path traversal, or anything that could put someone's data or credentials at risk all count. not sure if it counts? send it anyway.

## supported versions

only the latest release gets security fixes.

| version | supported |
| --- | --- |
| latest release | yes |
| older releases | no |
| `develop` / unreleased | no, use at your own risk |

## what happens next

i'll acknowledge your report as soon as i can, usually within a few days, and keep you posted on the fix. once it ships it goes in the release notes, with credit if you want it.

## scope

the code in this repo and the hosted site at [wrapped.devmatei.com](https://wrapped.devmatei.com). for context: navidrome credentials never leave your browser, and the server only keeps what it needs (uploaded artwork for an hour, navidrome badge snapshots, template submissions and counters). problems in listenbrainz, last.fm, libre.fm or navidrome themselves should go to those projects.
