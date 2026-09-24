# fleets

Test fleets for repoplane, applied to real forges with
[forgelab](https://github.com/repoplane/forgelab): forge edge-case shapes, and a labelled
corpus for measuring convergence.

A *fleet* is a directory that declares a known set of repositories. forgelab puts it into a
sandbox organisation (`apply`), asserts it is still there (`verify`), and puts it back after a
test run has churned it (`reset`). What makes a fleet reusable is that it is pinned: the same
inputs produce the same commit SHAs on every machine and every forge, so `fleet.lock.json` is
identical for everyone who applies it.

| Fleet | Repos | What it is for |
|---|---:|---|
| [`shapes/`](shapes) | 12 | One repository per shape a forge integration trips on: archived, no commits, a `master` default branch, tags, a public one among privates, namespaces. Correctness. |
| [`corpus/`](corpus) | 101 | Generated and deliberately heterogeneous: eight ecosystem archetypes crossed with non-compliance patterns, plus five repositories that fit no archetype. Ships `labels.json`, the ground truth a convergence number is measured against. The only fleet large enough to cross a forge's pagination boundary. |

## Using a fleet

`sandboxes.yaml` lives at the repository root and is shared by every fleet, so pass it
explicitly:

```sh
forgelab plan   --sandbox gh --fleet shapes --config sandboxes.yaml
forgelab apply  --sandbox gh --fleet shapes --config sandboxes.yaml
forgelab verify --sandbox gh --fleet shapes --config sandboxes.yaml
forgelab reset  --sandbox gh --fleet shapes --config sandboxes.yaml
```

`verify` exits 1 and names the drift; `reset` puts only the drifted repositories back.

## Tokens

`sandboxes.yaml` names an environment variable per sandbox — `token_env` — and never holds a
credential. That indirection is what lets the same file work locally and in CI.

**Locally (macOS)**, keep the tokens in the keychain and let `.env` read them out. Add them
once:

```sh
security add-generic-password -a "$USER" -s forgelab-gh  -w
security add-generic-password -a "$USER" -s forgelab-gl  -w
security add-generic-password -a "$USER" -s forgelab-ado -w
```

then `cp .env.example .env` and `source .env` before running forgelab. `.env` is gitignored —
not because it holds a secret (it holds only `security` lookups) but because `.env` is the file
people habitually put secrets in.

**In CI**, there is no keychain. Put the tokens in the runner's secret store and export them
into the same variable names; `sandboxes.yaml` needs no change.

## Sandboxes

The declared sandboxes target organisations that hold nothing else:

- `gh` — <https://github.com/repoplane-sandbox>
- `gl` — <https://gitlab.com/repoplane-sandbox>
- `ado` — <https://dev.azure.com/repoplane-sandbox>
- `local` — a Forgejo on `localhost:3000` (`make up` in the forgelab checkout)

What protects a wrong target is not this file: it is what the token can reach, plus forgelab's
marker topic and its refusal to touch anything the fleet does not declare.

Two consequences worth knowing:

**Azure DevOps has no repository topics and no per-repository visibility**, so it carries no
marker — there, a repository with a declared name is treated as forgelab's. Keep that
organisation empty of anything else.

**`shapes/` contains one public repository**, deliberately: restoring visibility is the one
drift whose failure has a real consequence, so it is exercised against live forges rather than
only a fake server. On GitLab a public project cannot sit in a private group, so that single
repository is why `repoplane-sandbox` is a public group. `corpus/` has no public repository.
