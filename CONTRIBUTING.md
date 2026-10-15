# Working together

Read [ownership](docs/team_ownership.md), [contracts](docs/integration_contract.md)
and [status](docs/module_status.md) before starting. Pull the latest `main` and
work on a branch scoped to your owner:

- `ai1/<feature>`, e.g. `ai1/semantic-retrieval`
- `ai2/<feature>`, e.g. `ai2/slm-evaluation`
- `ai3/<feature>`, e.g. `ai3/lightgbm-ranker`
- `integration/<feature>` for shared integration work

Suggested workflow in the team Git repository:

```sh
git checkout main
git pull --ff-only
git checkout -b ai1/semantic-retrieval
# Make the scoped change and add/update meaningful tests.
python -m pytest -q -p scripts.sealed_benchmark_guard
python examples/integration_demo.py
git add src/retrieval docs/ai1_retrieval.md
git commit -m "Add semantic retrieval candidate contract support"
git push -u origin ai1/semantic-retrieval
# Open a pull request and request the relevant owners' review.
```

Start with [setup](docs/setup.md). The checkout has Git metadata; maintainers
manage remote access, CODEOWNERS identities and branch protection. The regression
guard excludes sealed-benchmark readers without changing the benchmark or tests.

Do not destructively edit another owner's module. Discuss cross-module changes
and submit shared contracts through a PR/review. Include interface impact,
downstream compatibility, tests and remaining limitations in the PR. Shared
changes require the full suite; local module changes require relevant tests.

Never commit keys or `.env`. Do not add large raw datasets/models without explicit
approval. Keep notebook output small, avoid private interaction logs, preserve
benchmark source data, and use descriptive commits. Mock providers in tests;
do not add training or network LLM jobs to CI. Review `git diff --stat`, staged
files and ignored-file policy before committing.
