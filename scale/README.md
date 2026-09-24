# scale

108 repositories laid out as a plausible company. Where [`shapes/`](../shapes) asks whether
forgelab handles a forge *correctly*, this fleet asks whether it handles one *at size* — deep
namespaces, a listing that does not fit on one page, and enough realistic variety that a rule
written against it has to generalise.

```sh
python3 generate.py          # rewrite repos/, fleet.yaml and census.json
python3 generate.py --check  # exit 1 if what is on disk has drifted from the generator
```

Nothing here is hand-edited. `repos/`, `fleet.yaml` and `census.json` are outputs; this file's
neighbour `generate.py` is the source, and `--check` runs in CI so a hand edit cannot quietly
become the thing everyone tests against.

## The shape

Everything sits under one root, `acme/`:

| Depth | Shape | Count |
|---|---|---:|
| 2 | `acme/<repo>` | 2 |
| 3 | `acme/<team>/<repo>` | 98 |
| 4 | `acme/<team>/<subsystem>/<repo>` | 8 |

Twelve teams, deliberately uneven — `payments` and `platform` have 13 repositories each, `sre`
has 4 — because a real company has no tidy grid, and a fixture that does is one a rule can
accidentally be tuned to. Three subsystems (`payments/gateway`, `platform/observability`,
`data/ingest`) take it to depth four.

**Leaf names recur on purpose.** Eleven repositories are called `api`, ten `worker`, nine `docs`.
`payments` has an `api` at two depths — `acme/payments/api` and `acme/payments/gateway/api`. That
is both what an estate looks like and what forces a rule to key on the full path rather than the
leaf.

**Four parents hold repositories beside a sub-namespace** — `acme` itself, `acme/payments`,
`acme/platform`, `acme/data` — which is the one tree case `shapes/` does not cover.

## Why `acme/` is load-bearing

It is not decoration. On Azure DevOps only the **first** path segment becomes a project, so a
single root keeps all 108 repositories in one project instead of twelve — and project creation
there is a polled background operation, so twelve would cost tens of minutes on every apply and
destroy.

It also makes the two fleets incapable of touching each other: `scale` owns the project `acme`,
`shapes` owns `fleet`, `platform` and `services`. Nothing either one destroys can reach the
other.

| Fleet path | GitLab | Azure DevOps | GitHub · Forgejo |
|---|---|---|---|
| `acme/handbook` | `acme/handbook` | `acme/_git/handbook` | `acme-handbook` |
| `acme/payments/api` | `acme/payments/api` | `acme/_git/payments-api` | `acme-payments-api` |
| `acme/payments/gateway/api` | `acme/payments/gateway/api` | `acme/_git/payments-gateway-api` | `acme-payments-gateway-api` |

GitLab is the only forge that nests: 16 subgroups, created parents-first.

## Why 108

It is interesting on all three page sizes at once:

- **GitHub and GitLab list 100** → `100 + 8`. A full page then a short tail, which catches
  "a full page is the last page".
- **Forgejo lists 50** → `50 + 50 + 8`. Two *consecutive* full pages then a short one — the case
  that catches "stop after the second page", and one that `100 + 1` never produces.
- It divides by 2, 3, 4, 6, 9, 12, 18, 27, 36 and 54, so a consumer testing with small page sizes
  still gets exact multiples.

Same reasoning `shapes/` gives for choosing twelve, one order of magnitude up.

## What is in the repositories

Twelve archetypes. Eight are languages; four carry **no conventional manifest**, which is what
breaks a rule that assumes every repository is parseable:

| Archetype | Files |
|---|---|
| node · go · python · rust · java · ruby · dotnet · php | a manifest and an entry point |
| `terraform` | `main.tf`, `variables.tf`, `versions.tf` |
| `helm` | `Chart.yaml`, `values.yaml`, `templates/deployment.yaml` |
| `docs` | `mkdocs.yml`, `docs/index.md`, `docs/runbook.md` |
| `shell` | `bin/deploy.sh`, `bin/rotate.sh` (both **mode 755**), `Makefile` |

The executable bit is not incidental: `fleet.Digest` hashes it, so it is part of the commit SHA
and therefore part of what `verify` compares. `generate.py --check` compares modes for the same
reason.

**A leaf whose name says what it is gets the archetype that name implies** — `docs` is `docs`,
`charts` is `helm`, `infra` is `terraform`. The rest follow their team's stack, because a real
team has one. That is most of what makes this read as a company rather than a shuffle, and it is
why no repository called `docs` contains a `Cargo.toml`.

The spread is uneven and stays that way. It is a draw, not a target — the whole point of a
fixture like this is to be something a rule pack was *not* tuned against, so `generate.py`
reports the census rather than pinning it.

## No CI configuration, deliberately

A realistic estate has `.github/workflows`, `.gitlab-ci.yml` and the rest, and an earlier draft of
this fleet generated a spread of them with triggers that could never fire. They came out again,
because **nothing reads them yet**: CI is not in repoplane's scope, so the only thing the markers
carried was risk.

GitHub and GitLab both auto-discover their CI configuration, and an inert trigger is only inert
if it is written correctly. Get it wrong and every apply — and every `reset` push after it —
starts runs on private repositories that consume quota. That is a poor trade for a dimension
nothing consumes.

Azure DevOps was never the exposure, despite being the one that sounds expensive: a pipeline
there has to be created and pointed at a file, so an `azure-pipelines.yml` sitting in a
repository does nothing at all.

Adding them back is a table and a helper, when there is something to test with them.

## census.json

What each repository **has**, not whether it passes: team, subsystem, leaf, depth, archetype, its
flat name, its Azure DevOps mapping, and which conventional files it carries. Plus the totals.

There is no `compliant` field on purpose. Baking a verdict into a fixture freezes one policy
opinion, and the opinion belongs to whatever is being tested. `has.dockerfile` is three-state —
`"pinned"`, `"floating"` or `null` — because a Helm chart having no Dockerfile is a different
fact from having a bad one, and a tool that scores those the same reports a number that is wrong
in a way nobody notices.

Presence rates are tuned for a **private company** estate, which is a different place from the
open-source one the defaults usually describe: most repositories here are unlicensed, few have a
security policy, and CODEOWNERS follows the team rather than the dice — `platform` and `security`
nearly always, `growth` and `support` almost never. Correlation is what defeats a rule tuned on a
uniform draw.

## Notes

Every repository is private, on `main`, with no tags and not archived. The one public repository
in this setup lives in `shapes/`, where it earns its keep.

`SEED` is frozen. Bumping it reshuffles every variation at once, which at this size means
rewriting all 108 baseline commits and force-pushing them to four forges.

Destroying this fleet on GitLab removes 16 subgroups, and GitLab deletes subgroups
asynchronously — a `destroy` immediately followed by an `apply` can fail with `subgroup acme is
pending deletion`. Wait, or purge in the UI.

Azure DevOps creates a repository named after the project when it makes one, so the `acme`
project holds one repository this fleet never declared. Nothing adopts it — `generate.py` asserts
no path flattens to `acme` — but a listing of that project shows 109 where the lock says 108.
