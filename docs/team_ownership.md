# Team ownership

| Owner | Owned paths |
| --- | --- |
| AI 1 — Data + Retrieval | `src/retrieval/**`, `data/raw/**`, `data/processed/**`, `data/embeddings/**`, `notebooks/ai1/**`, `docs/ai1_retrieval.md`, retrieval-related tests |
| AI 2 — Conversation + Preference State | `src/conversation/**`, `data/ai2_interactive/**`, `notebooks/ai2/**`, `docs/ai2_conversation.md`, existing AI 2 tests and audit/schema docs |
| AI 3 — Ranking + Evaluation | `src/ranking/**`, `models/ranker/**`, `models/metadata/**`, `notebooks/ai3/**`, `docs/ai3_ranking.md`, ranking-related tests |
| Shared — coordination/review required | `src/common/**`, `src/pipeline/**`, `src/__init__.py`, `pyproject.toml` / dependency files, `README.md`, `.env.example`, CI, public schemas, integration docs/tests |

`src/personalization/**` is reserved and currently has no implementation; agree
ownership and interfaces before adding behavior. AI 2 tooling under `scripts/`,
the existing `benchmarks/` source, and `tests/data/` remain in place under AI 2
review. Do not modify frozen benchmark/test data without an explicit reviewed
change. New module tests should use `test_retrieval_*` / `test_ranking_*` names.
The three new common/import/pipeline test files are shared integration tests.

**NO module may silently change shared schemas.** If a shared schema changes:

1. Update the canonical common schema.
2. Update its documentation and version notes.
3. Update contract tests.
4. Notify the other module owners in the PR/review discussion.
5. Ensure integration tests and the full suite pass.

Do not edit another module destructively; coordinate implementation boundaries.
ID strings are shared across retrieval, ranking and backend with no conversions.
See [data schema](data_schema.md) and [contract](integration_contract.md).

## GitHub setup to finish when identities are known

`.github/CODEOWNERS` contains comments only: placeholders do not request reviews
or enforce ownership. Replace them with verified usernames/team slugs that have
repository access, then uncomment the relevant patterns and add test ownership.
Set branch protection to require PR checks and owner review once configured.
No usernames, remote, repository or branch protection were invented by this task.
The current checkout has Git metadata. Maintainers manage remote access and
branch protection. Follow [CONTRIBUTING.md](../CONTRIBUTING.md).
