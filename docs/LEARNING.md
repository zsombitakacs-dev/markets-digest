# Learning notes

Plain-English notes on every coding and finance idea used in this project, with examples from it.

## Coding and tools

### Git and a commit
Git records the history of a folder. A **commit** is a saved snapshot with a message saying what changed and why.
Example: this repo's first commit, "Set up project layout", holds the empty folder structure and this file.
Reading `git log` should tell the story of the build, one working step at a time.

### GitHub, public and private repos
A **repo** (repository) is a folder tracked by Git. GitHub hosts repos online.
This project uses two: `markets-digest` is **public** (the code, which anyone can read, good for a CV) and
`markets-digest-data` is **private** (the prices, digests and logs, visible only to the owner).
Rule of the project: the code is public, the content is private.

### Two-factor authentication (2FA)
Logging in needs a password **and** a one-time code from your phone. A stolen password alone is then useless.
It matters here because whoever controls the GitHub account controls the page, the data and the secrets.

### The noreply commit email
Every commit stores an author email, and in a public repo anyone can read it.
GitHub gives each user a private stand-in address like `12345+username@users.noreply.github.com`,
so commits are still linked to your profile without exposing your real email.

### Virtual environment (venv)
A private copy of Python for one project, in the `.venv/` folder, so this project's libraries
(e.g. `yfinance`) don't clash with other projects. Activate it with `source .venv/bin/activate`.
It is never committed: anyone can recreate it from `requirements.txt`.

### .gitignore
A list of files Git must never track. Here: the venv, Python caches, `.env` (secrets) and the
data folder, so private content can't be committed to the public repo by accident.

### Dependabot
A GitHub robot that checks weekly whether the libraries and actions we pin have updates (often security fixes)
and suggests the change. Config: `.github/dependabot.yml`.

### Repo security settings (applied in phase 0)
- **Outside contributors need approval:** a stranger's proposed change can't run our workflows (which hold secrets) until we approve it.
- **Read-only workflow token:** each workflow gets a temporary GitHub token; by default it may only read, and a workflow must ask for more explicitly.
- **Branch rule on `main`:** blocks force-pushes (rewriting history) and deleting the branch, so the history can't be quietly erased.
- **Secret scanning and push protection:** GitHub refuses a push that contains something that looks like a key or token.
- **Actions switched off in the data repo:** it only stores content, so there is nothing there that should ever run.
