# shapes

Fifteen repositories, each one a shape a forge integration trips on. Where [`scale/`](../scale)
asks whether forgelab holds up at size, this fleet asks whether it handles each forge *correctly*
— and it is small enough that a failure points straight at what broke.

It is the same fleet as forgelab's
[`examples/fleet`](https://github.com/repoplane/forgelab/tree/main/examples/fleet), kept in sync
by hand. The difference is where it runs: forgelab applies its copy to a throwaway Forgejo in CI,
while this one is applied to all four real sandboxes.

## The fixtures

Twelve at the root:

| Fixture | Shape it is there to test |
|---|---|
| `compliant` | the control — nothing unusual, and no entry in `fleet.yaml` at all |
| `master-branch` | a default branch that is not `main` |
| `archived` | archived: still readable, and rejects every write. Applied last, because once set nothing else can be |
| `no-commits` | `empty: true` — created and never pushed to. The null default ref, and the one fixture `reset` cannot repair |
| `tagged` | carries tags `v1` and `v2` |
| `scaffold` | a README and nothing else |
| `public` | the one public repository among privates |
| `dotfiles` | everything under dot-prefixed paths — `.editorconfig`, `.config/app.yml` |
| `billing-api` · `ledger-worker` · `node-gateway` · `parser-svc` | plain services with topics, and a per-language manifest each |

Three more in namespaces:

| Fixture | Shape it is there to test |
|---|---|
| `services/api` | a namespace one level deep |
| `platform/core/api` | the same leaf name, two levels deep — so `api` appears twice in the fleet |
| `platform/tooling` | a repository sitting beside a sub-namespace in the same parent |

**Twelve is chosen for its divisors.** Listing the root with a page size of 12, 6, 5, 4, 3 or 1
gives an exact single page, exact multiples, a short tail and a deep cursor chain. Crossing a
*real* forge page needs more than a hundred, which is `scale/`'s job.

## What the namespaces land as

The three namespaced fixtures are the only place `shapes` diverges per forge:

| Fleet path | GitLab | Azure DevOps | GitHub · Forgejo |
|---|---|---|---|
| `services/api` | `services/api` | `services/_git/api` | `services-api` |
| `platform/core/api` | `platform/core/api` | `platform/_git/core-api` | `platform-core-api` |
| `platform/tooling` | `platform/tooling` | `platform/_git/tooling` | `platform-tooling` |

GitLab makes a real subgroup per segment. Azure DevOps turns the **first** segment into a project
and joins the rest. GitHub and Forgejo join the whole path, so there the org listing holds all
fifteen repositories flat.

## Two things that are deliberate

**`public` is the reason `repoplane-sandbox` is a public group on GitLab.** A public project
cannot sit inside a private group, so that single fixture makes the whole group public. It earns
it: restoring visibility is the one drift whose failure has a real consequence — a repository a
test made public and `reset` failed to make private again stays exposed. That path is worth
exercising against live forges rather than a fake server. `scale/` has no public repository.

**`archived` cannot be re-seeded on Azure DevOps.** A disabled repository there answers 404 to
everything but the project's listing, so forgelab takes it as already seeded. Changing its content
means destroying it first.

## Isolation from `scale`

Both fleets are applied to the same sandbox organisations, and forgelab identifies a repository by
name, so nothing may be named twice. `shapes` keeps the root and the namespaces `platform`,
`platform/core` and `services`; `scale` keeps everything under `acme/`. On Azure DevOps that means
`shapes` owns the projects `fleet`, `platform` and `services` while `scale` owns `acme` — so
destroying either one cannot reach the other.
