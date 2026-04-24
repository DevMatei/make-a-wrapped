# Contributing to Make a Wrapped

First off — thanks for taking the time to contribute! :D  
This project is open to improvements, bug fixes, and cool ideas from the community.  
Before you start, please take a moment to read through this guide.

---

## 🧠 What’s this project?
**Make a Wrapped** is a small web service that generates a Spotify-style “Wrapped” using data from [ListenBrainz](https://listenbrainz.org/), [MusicBrainz](https://musicbrainz.org/), and a few related APIs — all public, no tokens.

---

## 🛠️ Local Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/DevMatei/make-a-wrapped.git
   cd make-a-wrapped

2. **Create and activate a virtual environment**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run locally**

   ```bash
   ./script.sh 0.0.0.0 5000
   ```

   Then open [http://localhost:5000](http://localhost:5000).

---

## 🧩 Code Guidelines

* Follow **PEP8** for Python formatting.
* Use **type hints** where possible.
* Keep functions **small and readable** — clarity over cleverness.
* Use **descriptive commit messages** (`feat:`, `fix:`, `chore:` style preferred).
* Don’t commit large cache/data files — use `.gitignore`.

---

## 💡 Want to Add Something?

* Open an **issue** first to discuss major changes.
* For small fixes (typos, doc updates), just open a **pull request** directly.
* Keep PRs focused — one feature or bug per PR.

---

## 🧑‍💻 Example Areas to Contribute

* UI/UX tweaks or redesigns for the Wrapped output.
* Performance improvements for data fetching.
* New API integrations (Last.fm, Navidrome, etc.).
* Translation/localization support.
* Caching / retry logic improvements.

---

## 🧾 License

By contributing, you agree that your contributions will be licensed under the same license as the project (see `LICENSE` file).

---

## ☕ Note from the dev

This project exists because Spotify Wrapped doesn’t care about self-hosters.
If you like it, share it — but please don’t resell, rebrand, or abuse the API rate limits.

Thanks for helping make "Make a Wrapped" more fun 💜
— **</DevMatei>**


