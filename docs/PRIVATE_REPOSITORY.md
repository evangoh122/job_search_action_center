# Private GitHub repository guide

## What may be committed

Source code, tests, `README.md`, documentation, `.devcontainer/`, and example configuration
files without real values are suitable for the private repository.

## What must remain local

Never commit `.env`, tokens, service-account JSON, SQLite databases, job/application exports,
resume files, contact lists, or generated comparison reports. The repository `.gitignore`
excludes these paths and file types.

Before every push, run:

```powershell
git status --short
git diff --cached --name-only
git check-ignore -v .env data\jobs.sqlite resume\your-resume.docx
```

If a secret was ever committed, removing the file is insufficient: rotate the credential and
purge it from Git history before pushing.

## Create the private repository

Using GitHub CLI after authenticating:

```powershell
gh repo create job-search-action-center --private --source . --remote origin --push
```

If `origin` already exists, inspect it before changing anything:

```powershell
git remote -v
gh repo view --json nameWithOwner,visibility,url
```

Repository visibility should report `PRIVATE`. Do not make this repository public; even with
ignored data files, the project documentation can reveal personal job-search strategy.
