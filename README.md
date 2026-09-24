<h1 align="center">🛩️ fleets</h1>

<p align="center">
  <strong>The repositories repoplane is tested against: pinned, and put back after every run.</strong>
</p>

<p align="center">
  <a href="https://github.com/repoplane/forgelab"><img src="https://img.shields.io/badge/applied%20with-forgelab-6f42c1" alt="Applied with forgelab"></a>
  <img src="https://img.shields.io/badge/forges-Forgejo%20%C2%B7%20GitHub%20%C2%B7%20GitLab%20%C2%B7%20Azure%20DevOps-lightgrey" alt="Forges">
</p>

<p align="center">
  <a href="#-the-fleets">The fleets</a> &bull;
  <a href="#-using-a-fleet">Using a fleet</a> &bull;
  <a href="#-tokens">Tokens</a> &bull;
  <a href="#-sandboxes">Sandboxes</a>
</p>

---

> [!NOTE]
> **This is test data for repoplane, not a general-purpose project.** It is public so the
> fixtures are reviewable, but the sandbox names and repository names are specific
> to repoplane's test suite. If you want to build your own fleet, start from
> [forgelab](https://github.com/repoplane/forgelab) and its
> [`examples/fleet`](https://github.com/repoplane/forgelab/tree/main/examples/fleet) instead.

A *fleet* is a directory that declares a known set of repositories.
[forgelab](https://github.com/repoplane/forgelab) puts it into a sandbox organisation
(`apply`), asserts it is still there (`verify`), and puts it back after a test run has churned
it (`reset`).

What makes a fleet reusable is that it is **pinned**: the same inputs produce the same commit
SHAs on every machine and every forge, so `fleet.lock.json` is identical for everyone who
applies it — and tests can assert against it.

## 🗂 The fleets

| Fleet | Repos | Question it answers |
|---|---:|---|
| 🧩 [`shapes/`](shapes) | 15 | *Does forgelab handle each forge correctly?* |
| 🏢 [`scale/`](scale) | 108 | *Does it hold up at size — deep namespaces, more than one page, realistic variety?* |

They share every sandbox organisation, and forgelab identifies a repository by name, so nothing
may be named twice. `scale` keeps everything under one `acme/` root, which makes that structural
rather than a rule anyone has to remember — and on Azure DevOps, where only the first path
segment becomes a project, it is also what keeps the two fleets from ever destroying each other:
`scale` owns the project `acme`, `shapes` owns `fleet`, `platform` and `services`.

## 🧩 `shapes/`

Twelve repositories at the root, each one shape a forge integration trips on, and three more in
namespaces. It is the same fleet as forgelab's
[`examples/fleet`](https://github.com/repoplane/forgelab/tree/main/examples/fleet), kept in
sync by hand.

| Fixture | Shape |
|---|---|
| `compliant` | the control — nothing unusual |
| `master-branch` | a default branch that is not `main` |
| `archived` | archived: readable, and rejects every write |
| `no-commits` | no commits at all — the null default ref |
| `tagged` | carries tags `v1` and `v2` |
| `scaffold` | a README and nothing else |
| `public` | the one public repository among privates |
| `dotfiles` | everything under dot-prefixed paths |
| `billing-api` · `ledger-worker` · `node-gateway` · `parser-svc` | plain services, with topics |
| `services/api` · `platform/core/api` | the same leaf name in two namespaces, one of them deep |
| `platform/tooling` | a repository next to a namespace |

Twelve is chosen for its divisors: listing the root with a page size of 12, 6, 5, 4, 3 or 1
gives an exact single page, exact multiples, a short tail and a deep cursor chain.

Namespaces land as subgroups on GitLab, as a project on Azure DevOps, and as a `-`-joined name
on GitHub and Forgejo (`platform/core/api` is `platform-core-api` there), so on those two the
listing holds all fifteen.

## 🏢 `scale/`

108 repositories laid out as a plausible company, under one `acme/` root: twelve uneven teams,
three subsystems taking it to depth four, and leaf names that recur across teams on purpose —
eleven of them are called `api`. Generated, never hand-edited, by
[`scale/generate.py`](scale/generate.py); `--check` runs in CI so an edit cannot quietly become
the thing everyone tests against.

It exists for what `shapes/` structurally cannot reach:

- **More than one page.** GitHub and GitLab list 100 at a time, Forgejo 50. 108 gives `100 + 8`
  on the first two and `50 + 50 + 8` on the third — two *consecutive* full pages, the case that
  `100 + 1` never produces.
- **Namespaces at depth.** Sixteen subgroups on GitLab, created parents-first; one project on
  Azure DevOps, where only the first segment counts; `acme-payments-gateway-api` on GitHub.
- **Realistic variety.** Twelve archetypes, four of which carry no conventional manifest at all,
  so a rule that assumes every repository is parseable visibly fails.

[`scale/census.json`](scale/census.json) records what each repository *has* — archetype, team,
depth, CI markers, which conventional files — but deliberately no verdict on whether that is
good. The opinion belongs to whatever is being tested.

CI markers are present but **inert by construction**: GitHub workflows are `on:
workflow_dispatch`, GitLab pipelines are `when: never`. An apply, and every `reset` push after
it, would otherwise spawn pipelines that fail for want of a runner.

## 🚀 Using a fleet

`sandboxes.yaml` lives at the repository root, outside the fleet directory, so pass it
explicitly:

```sh
forgelab plan   --sandbox gh --fleet shapes --config sandboxes.yaml
forgelab apply  --sandbox gh --fleet shapes --config sandboxes.yaml
forgelab verify --sandbox gh --fleet shapes --config sandboxes.yaml
forgelab reset  --sandbox gh --fleet shapes --config sandboxes.yaml
```

`verify` exits 1 and names the drift; `reset` puts only the drifted repositories back.

```text
fleets/
├── sandboxes.yaml      where each fleet can be applied — shared by all of them
├── .env.example        reads the tokens out of the macOS keychain
├── shapes/
│   ├── fleet.yaml
│   ├── fleet.lock.json
│   └── repos/<path>/   a directory holding a file is a repository;
│                       one holding only directories is a namespace
└── scale/
    ├── generate.py     the source of everything else in this directory
    ├── census.json     what each repository has, per repository
    ├── fleet.yaml
    ├── fleet.lock.json
    └── repos/acme/<team>/[<subsystem>/]<repo>/
```

## 🔑 Tokens

`sandboxes.yaml` names an environment variable per sandbox — `token_env` — and never holds a
credential. That indirection is what lets the same file work locally and in CI.

**💻 Locally (macOS)**, keep the tokens in the keychain and let `.env` read them out. Add them
once:

```sh
security add-generic-password -a "$USER" -s forgelab-gh  -w
security add-generic-password -a "$USER" -s forgelab-gl  -w
security add-generic-password -a "$USER" -s forgelab-ado -w
```

then `cp .env.example .env` and `source .env` before running forgelab. `.env` is gitignored —
not because it holds a secret (it holds only `security` lookups) but because `.env` is the file
people habitually put secrets in.

**🤖 In CI**, there is no keychain. Put the tokens in the runner's secret store and export them
into the same variable names; `sandboxes.yaml` needs no change.

## 🏝 Sandboxes

The declared sandboxes target organisations that hold nothing else:

| Sandbox | Forge | Where |
|---|---|---|
| `local` | Forgejo | `localhost:3000` — `make up` in the forgelab checkout |
| `gh` | GitHub | <https://github.com/repoplane-sandbox> |
| `gl` | GitLab | <https://gitlab.com/repoplane-sandbox> |
| `ado` | Azure DevOps | <https://dev.azure.com/repoplane-sandbox> |

**🔒 What protects a wrong target is not this file:** it is what the token can reach, plus
forgelab's marker topic and its refusal to touch anything the fleet does not declare.

Two consequences worth knowing:

**⚠️ Azure DevOps has no repository topics and no per-repository visibility**, so it carries no
marker — there, a repository with a declared name is treated as forgelab's. Keep that
organisation empty of anything else.

**🌍 `shapes/` contains one public repository**, deliberately: restoring visibility is the one
drift whose failure has a real consequence, so it is exercised against live forges rather than
only a fake server. On GitLab a public project cannot sit in a private group, so that single
repository is why `repoplane-sandbox` is a public group.

