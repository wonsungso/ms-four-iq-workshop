# Contributing to Microsoft IQ Workshop

Contributions to the workshop documentation and sample code are welcome.

## Contributor License Agreement

<!-- TODO: Maintainer confirmation required: applicable CLA policy. Do not assume a CLA bot is configured for the target repository. -->

## Code of Conduct

Read and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Issues and proposals

Search the [workshop issue tracker](https://github.com/wonsungso/ms-four-iq-workshop/issues)
before reporting a bug or proposing a feature, including when you work from a fork.
Include the affected lab and step, the relevant revision, your execution environment,
reproduction steps, and the expected and actual results.
Discuss substantial changes with the maintainers before implementing them.

Remove credentials, subscription and tenant IDs, personal resource identifiers,
customer data, and private information from logs and screenshots.
Report security vulnerabilities using [SECURITY.md](SECURITY.md), not a public issue.
See [SUPPORT.md](SUPPORT.md) for help and support information.

## Pull requests

Search the [workshop pull requests](https://github.com/wonsungso/ms-four-iq-workshop/pulls)
for related changes.
Make your changes in a dedicated branch of your fork and keep unrelated local changes intact.
Submit the pull request to the maintainer-confirmed `main` branch of
`wonsungso/ms-four-iq-workshop`.
Use the target repository's pull request template when one exists.

Keep the change focused and describe any changes to lab behavior.
Preserve existing copyright notices, attribution, and third-party licenses.
Do not change licensing or rewrite shared history without maintainer approval.
Use follow-up commits when addressing review feedback.

## Workshop validation

This is a notebook-led workshop. Each Part notebook is stored in its associated
directory under [labs](labs), alongside its images and a short README containing
metadata, an execution link, and navigation. Prerequisites, validation, cleanup,
and troubleshooting belong in the notebook, not in duplicate README prose.
The setup lab retains its full Markdown deployment guide.
This project-specific departure from the full paired-guide format was approved
by the maintainer on 2026-10-21.

The shared authentication module, requirements, Copilot CLI sidequest, and
index restoration utility remain under [notebooks](notebooks).
Run each Part notebook's initial path setup cell before its other code cells.
It locates the repository root from the working directory and its parents,
then adds the shared module directory to the Python import path.
Environment files and data are resolved from that root.
Preserve the existing mission and source-hunt cells and test any path changes.

The declared execution environments are GitHub Codespaces and local VS Code.
The existing [devcontainer](.devcontainer/devcontainer.json) uses Python 3.12;
manual local setup requires Python 3.10 or newer as documented in the
[deployment guide](labs/00-setup/README.md).
Cloud deployment, paid service calls, resource deletion, and remote publication
require separate approval.

Run the nine checks documented in [AGENTS.md](AGENTS.md) from the repository root
using Git Bash or a Bash-based devcontainer.
The checks require gitleaks 8.19 or newer, Python 3.10 or newer,
and the dependencies in `local-only/workshop-checks/requirements-workshop.txt`.
Copy `workshop_checks.py` and `requirements-workshop.txt` from the verified
workshop-standardization skill bundle into `local-only/workshop-checks/` for each new clone.
Confirm that `local-only/` is Git-ignored and the copied tools are untracked.
Resolve existing-file conflicts with the maintainer before copying.
Git ignore rules do not exclude files from workshop checks.
Do not automatically move or delete existing files under `scripts/`.
Record each command, its scope, commit SHA, exit status, and actual result.
A final `PASS` does not override an earlier error.
If a new repository has no Git history, report history checks as not run;
do not count a tree-only scan as a full history pass.

Keep validation logs and decision records in a confirmed Git-ignored local directory.
Share only redacted summaries in the pull request.

Automated checks do not replace a complete workshop run in the declared environment
or a review of screenshots for private information.
Leave `validated_on` blank until a person completes the workshop and provides the date.
Do not invent durations, cost estimates, or successful execution results.
List unresolved TODOs and policy decisions in the pull request.
