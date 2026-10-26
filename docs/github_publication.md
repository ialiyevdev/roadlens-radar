# Publish RoadLens Radar v1.0.0

The local release is prepared for publication. No repository, commit, tag,
GitHub release or Pages deployment was created by this preparation task.
Run the commands below only when you choose to publish.

## Current state and repository details

The checked-out branch is `main`, with no branch commits, tracked files or
configured remote. Two local tool-managed tree snapshots are separate from the
publication branch. Push only `main` and the explicit `v1.0.0` tag; do not use
`--mirror` or `--all`.

Suggested repository name: **roadlens-radar**.

Suggested description:

> Local CPU computer vision and traffic analytics workbench with calibrated
> measurement, validation tools and a synthetic portfolio showcase.

Suggested topics:

```text
computer-vision opencv yolox object-detection multi-object-tracking
traffic-analytics camera-calibration homography fastapi react typescript
vite python portfolio
```

On GitHub, create an **empty public repository** under your chosen account or
organization if it does not exist. Do not initialize it with a README, license
or `.gitignore`; those files already exist locally. If using an existing
repository, inspect its content and visibility first. These instructions do
not change repository visibility or overwrite existing remote history.

The owner is not configured locally, so there is no verified public repository
or showcase URL yet. Keep the README link locations marked pending until GitHub
provides the actual URLs.

## Review and publish the source

Use PowerShell in the repository root. These commands are for this first
publication state; stop on any error rather than continuing through the sequence.

```powershell
$GitHubOwner = Read-Host 'GitHub username or organization'
if ($GitHubOwner -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') { throw 'Enter a GitHub account name, not a URL.' }
$Repository = "$GitHubOwner/roadlens-radar"
$RepositoryUrl = "https://github.com/$Repository.git"

git status --short --untracked-files=all
git remote -v
.\.venv\Scripts\python.exe scripts\check_release.py

git add -- .github .gitattributes .gitignore .vscode LICENSE README.md CHANGELOG.md pyproject.toml requirements-dev.lock requirements-build.lock backend frontend scripts docs examples third_party
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
```

Review the staged files and their content before proceeding. `data/`, `.venv`,
`node_modules`, generated builds, environment files and model weights must not
appear. The existing ignore rules exclude them. Confirm ownership, MIT terms,
third-party notices, image rights and the demo manifest. A pattern scan does not
replace a human review.

The local Git author name is unset. Choose the author identity that will become
public in the commit. Copy your preferred no-reply email from GitHub's email
settings rather than reusing a private address by accident:

```powershell
$GitAuthorName = Read-Host 'Public Git author name'
$GitAuthorEmail = Read-Host 'GitHub no-reply email for public commits'
if ([string]::IsNullOrWhiteSpace($GitAuthorName) -or [string]::IsNullOrWhiteSpace($GitAuthorEmail)) { throw 'Author name and email are required.' }
git config --local user.name $GitAuthorName
git config --local user.email $GitAuthorEmail
git commit -m "Release RoadLens Radar v1.0.0"
```

Install GitHub CLI (`gh`) if using its authentication and release commands.
Confirm the selected account with `gh auth status`; if needed, run
`gh auth login --hostname github.com --git-protocol https --web` first.
Then connect the empty destination and publish:

```powershell
gh auth setup-git
if (@(git remote).Count -ne 0) { throw 'A remote is now configured; inspect it before continuing.' }
$RemoteRefs = @(git ls-remote --refs $RepositoryUrl)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the destination repository.' }
if ($RemoteRefs.Count -ne 0) { throw 'The remote is not empty. Reconcile its history without force-pushing.' }
git remote add origin $RepositoryUrl
git push -u origin main
```

The push publishes the source and automatically triggers **Deploy static
showcase**. It is also the point at which external Pages deployment becomes
authorized by your action. No force push or history rewrite is required.

## Enable and verify GitHub Pages

In the GitHub repository, open **Settings → Pages → Build and deployment** and
choose **GitHub Actions** as the source. If an empty repository does not expose
that setting, make the first push, select it, then run **Deploy static showcase**
from the Actions tab. Approve a `github-pages` environment deployment if repository
protection rules require it; keep existing organization controls in place.

The prepared [workflow](../.github/workflows/deploy-showcase.yml) uses Node 24.16.0,
`npm ci` and the existing command:

```text
npm run build:showcase -- --base=/roadlens-radar/
```

Only **`frontend/dist-showcase`** is uploaded to the official Pages artifact and
deployment actions. It contains the shared static tour, bundled evidence,
reviewed Phase 6 screenshots and their notices. The normal frontend configuration,
backend source, uploaded recordings, local study data and separately downloaded
model are not hosted. The artifact checker validates the static boundary before
upload. GitHub documents the required Pages setup and deployment permissions in
[Using custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

Wait for the workflow and deployment to succeed. Open the URL reported by the
`github-pages` environment or **Settings → Pages**. Check all ten steps, keyboard
navigation, native charts, screenshots and evidence downloads. In browser
developer tools, confirm that no `/api` request or localhost connection is made.
The Python backend can remain stopped.

Read the actual repository and Pages URLs after they exist:

```powershell
gh repo view $Repository --json url --jq .url
gh api "repos/$Repository/pages" --jq .html_url
```

Replace the README's pending repository/live-showcase link locations with these
verified URLs and set the repository's About website field to the successful
deployment URL. If that changes the README, commit and push the documentation
update before tagging the release, then verify the resulting deployment:

```powershell
git add -- README.md
git commit -m "Document verified public project URLs"
git push origin main
```

## Tag and create the release

After the source, confirmed URLs and deployed showcase have been reviewed:

```powershell
git status --short
git tag -a v1.0.0 -m "RoadLens Radar v1.0.0"
git push origin v1.0.0
gh release create v1.0.0 --repo $Repository --verify-tag --title "RoadLens Radar v1.0.0" --notes-file docs/release_notes.md
```

`--verify-tag` prevents GitHub CLI from silently creating a missing tag. The
release command publishes the prepared notes without uploading local media,
environments or model files. See the official
[GitHub CLI release reference](https://cli.github.com/manual/gh_release_create).
Tag pushes do not trigger this Pages workflow; it follows `main`.

## Final checklist

- [ ] Confirm the destination account and empty `roadlens-radar` repository.
- [ ] Review staged files, public Git identity, MIT terms, third-party rights and privacy.
- [ ] Read the current local results in [testing](testing.md), [release audit](release_audit.md)
  and [reproducibility](reproducibility.md).
- [ ] Explicitly choose to commit and push; recognize that `main` pushes trigger Pages.
- [ ] Enable the GitHub Actions Pages source and satisfy environment approval rules.
- [ ] Verify the hosted showcase under its repository subdirectory, including zero backend calls.
- [ ] Replace pending README URLs only with confirmed repository/deployment URLs.
- [ ] Review and push the annotated `v1.0.0` tag; publish the prepared release notes.

Independent roadway speed/counting accuracy remains unverified. A passing static
deployment does not validate physical measurements. No further product phase is
required to publish this version.
