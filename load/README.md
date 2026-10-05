# load

2,016 repositories laid out as a large company. It is [`scale/`](../scale) at twenty times the
size: where scale asks whether something holds up *at size*, this fleet is big enough to load it
— a listing of tens of pages, and enough repositories that a run across hundreds of them is
the common case rather than the whole fleet.

```sh
python3 generate.py          # rewrite repos/, fleet.yaml and census.json
python3 generate.py --check  # exit 1 if what is on disk has drifted from the generator
```

Nothing here is hand-edited. `repos/`, `fleet.yaml` and `census.json` are outputs;
`generate.py` is the source, and `--check` runs in CI.

## The shape

Everything sits under one root, `bigcorp/`:

| Depth | Shape | Count |
|---|---|---:|
| 2 | `bigcorp/<repo>` | 4 |
| 3 | `bigcorp/<division>/<repo>` | 21 |
| 4 | `bigcorp/<division>/<team>/<repo>` | 1,885 |
| 5 | `bigcorp/<division>/<team>/<subsystem>/<repo>` | 106 |

Ten divisions, 62 teams, nine subsystems — 82 namespaces. Deliberately uneven, as in scale:
`platform` has 381 repositories and `corporate` 53; `finance/payments` has 101 and
`mobile/wearables` 7.

**Leaf names recur on purpose.** 81 repositories are called `docs`, 71 `api`, 71 `worker`.
A name can be a namespace in one place and a repository in another: `search` is a `commerce`
team and a repository in `corporate/intranet`. A rule has to key on the full path.

**Every parent above a team holds repositories beside a sub-namespace** — `bigcorp` itself, all
ten divisions, and the six teams with subsystems.

## How the names are made

scale writes every repository name out. At 2,016 that stops being possible, so this fleet keeps
the structure literal and draws the leaves:

- Divisions, teams and subsystems are a literal table in `generate.py`, each team with its own
  vocabulary of domain nouns — `ledger` has `journal`, `posting`, `period-close`.
- A team's candidates are the common leaves (`api`, `worker`, `docs`, `web`, `sdk`, …), its
  nouns, and each noun with a role suffix (`journal-sync`, `period-close-service`).
- It keeps `size` of them: `api`, `worker` and `docs` first, then its bare nouns, then the rest
  in hash order. So nearly every team has an `api`, a big team usually has a `web` and a small
  one rarely, and a payments team never grows a `playlist-api`.

## Why `bigcorp/` is load-bearing

For the reasons scale gives for `acme/`: on Azure DevOps only the first path segment becomes a
project, so one root keeps all 2,016 repositories in one project. It is also what lets the three
fleets share a forge: `load` owns `bigcorp`, `scale` owns `acme`, and nothing either one destroys
can reach the other. `generate.py` checks that no name collides with a sibling fleet's.

| Fleet path | GitLab | Azure DevOps | GitHub · Forgejo |
|---|---|---|---|
| `bigcorp/handbook` | `bigcorp/handbook` | `bigcorp/_git/handbook` | `bigcorp-handbook` |
| `bigcorp/finance/ledger/journal` | `bigcorp/finance/ledger/journal` | `bigcorp/_git/finance-ledger-journal` | `bigcorp-finance-ledger-journal` |
| `bigcorp/finance/payments/gateway/api` | `bigcorp/finance/payments/gateway/api` | `bigcorp/_git/finance-payments-gateway-api` | `bigcorp-finance-payments-gateway-api` |

GitLab is the only forge that nests: 82 subgroups, created parents-first. The longest flattened
name is 58 characters; `generate.py` keeps it under 64.

## Why 2,016

The same reasoning as scale's 108, one order of magnitude up:

- **GitHub and GitLab list 100** → `20 × 100 + 16`. Twenty full pages, then a short tail.
- **Forgejo lists 50** → `40 × 50 + 16`.
- **Azure DevOps answers in one call**, so it is one response of 2,016 repositories.
- It divides by 2, 3, 4, 6, 7, 8, 9, 12, 14, 16, 18, 21, 24, 28, 32, 36, 42, 48, 56, 63, 72, 84,
  96 and on, so slices and batches of most sizes come out exact.

## What is in the repositories

The same twelve archetypes as scale, with the same files and the same rule that a leaf whose
name says what it is gets that archetype. The stack follows the division, with a few teams
overriding it (`operations/support` on PHP, `mobile/ios` on shell). A role suffix decides it too:
anything `-ui` or `-dashboard` is `node`. The presence rates for README, LICENSE, SECURITY.md,
Dockerfile, vendored dependencies and second manifests are scale's; CODEOWNERS follows the
division.

No CI configuration, for the reasons in [`scale/README.md`](../scale/README.md#no-ci-configuration-deliberately).
`census.json` has the same form as scale's, with a `division` beside each `team`, and team
tallies keyed `division/team`.

## Notes

Every repository is private, on `main`, with no tags and not archived.

`SEED` is frozen. Bumping it reshuffles every variation at once, which at this size means
rewriting 2,016 baseline commits on every forge. Changing a team's `size` or nouns reshuffles
only that team.

On GitHub, forgelab spaces writes a second apart, so a first apply takes more than an hour;
after that, `reset` touches only what drifted. Destroying it on GitLab removes 82 subgroups
asynchronously — wait before applying again.

Azure DevOps creates a repository named after the project when it makes one, so the `bigcorp`
project holds one repository this fleet never declared: a listing shows 2,017 where the lock
says 2,016. `generate.py` asserts no path flattens to `bigcorp`.
