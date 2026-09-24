# corpus

101 repositories, generated. Where [`shapes/`](../shapes) asks whether forgelab handles a
forge correctly, this fleet asks whether a *rule* does something meaningful when applied
across an estate — and gives you the ground truth to check the answer against.

```sh
python3 generate.py          # rewrite repos/, fleet.yaml and labels.json
python3 generate.py --check  # exit 1 if what is on disk has drifted from the generator
```

Nothing here is hand-edited. `repos/`, `fleet.yaml` and `labels.json` are all outputs; the
generator is the source. `--check` belongs in CI, so a hand edit cannot quietly become the
thing everyone measures against.

## Why generated rather than forked

Copying 101 real repositories would have cost more and measured less:

- **Determinism.** forgelab pins the author and the clock so a fleet produces identical
  commit SHAs on every machine and forge. Real repositories force either a full history
  import or a squash, and squashing discards the only realism a fork uniquely offered.
- **Licensing.** A hundred public repositories include copyleft and unlicensed ones.
- **Cost.** `reset` staying cheap is the whole point. This corpus is 70 KB.
- **Ground truth.** This is the decisive one. You cannot measure convergence without
  knowing the right answer for every repository. Fork 101 and you hand-label 101. Generate
  them and the label falls out of the generation.

## What is in it

96 repositories across 8 ecosystem archetypes — node, go, python, rust, java, ruby, dotnet,
php — each a few hundred bytes of realistic *structure* (a manifest, an entry point,
sometimes a Dockerfile), because structure is what rules match on.

Archetypes are assigned by hashing the repository name, so the spread is uneven (10–14 per
archetype) rather than a tidy twelve. That is deliberate twice over: real estates are not
balanced, and a name can leave the pool without shifting every repository after it.

Names are checked against every sibling fleet at generation time. Both fleets apply to the
same sandbox organisation and forgelab identifies a repository by name, so a name used twice
means one fleet silently overwrites the other on a live forge — which is exactly what
happened the first time this corpus was applied, and why `claimed_elsewhere()` exists.

Six rules are then applied at deliberately uneven rates. A corpus that misses every rule at
the same frequency teaches a metric nothing; these roughly mirror a real estate, where
READMEs are near-universal and CODEOWNERS is rare:

| Rule | Compliant | Violating | Not applicable |
|---|---:|---:|---:|
| `readme` | 95 | 6 | 0 |
| `license` | 82 | 19 | 0 |
| `ci-workflow` | 81 | 17 | 3 |
| `security-policy` | 57 | 43 | 1 |
| `codeowners` | 42 | 59 | 0 |
| `dockerfile-pinned` | 32 | 26 | 43 |

**`dockerfile-pinned` is the interesting column.** Forty-three repositories have no Dockerfile
at all, so they are neither compliant nor violating. A tool that scores them as either one
reports a number that is wrong in a way nobody notices. `labels.json` keeps the three states
separate for exactly that reason.

## The tail

Five repositories fit no archetype, and exist because the measured reality is that hard
cases **do not cluster**:

| Repository | Why it is awkward |
|---|---|
| `legacy-monolith` | No manifest at all. Shell scripts and an rsync deploy. |
| `docs-portal` | Prose only. Most code rules are not applicable, not failing. |
| `vendored-tool` | Dependencies committed in-tree; a file walker must skip `vendor/`. |
| `platform-monorepo` | Three manifests in one repository. "The" manifest is ambiguous. |
| `abandoned-spike` | One stray text file. No README, no manifest. |

A rule pack tuned against the 96 still has to make a decision about these five, and for
several of them the correct decision is "not applicable". That judgement is what separates a
convergence number from a vanity metric.

## labels.json

Per repository: its archetype, whether it is tail, and per rule a verdict of `true`, `false`
or `null` for not-applicable. Plus `totals`, the denominators above.

```json
"billing-api": {
  "archetype": "go",
  "tail": false,
  "rules": {
    "readme": { "compliant": true },
    "dockerfile-pinned": { "compliant": null, "reason": "no Dockerfile" }
  }
}
```

## Notes

Every repository is private, on purpose — the single public repository in this setup lives
in `shapes/`, where it earns its keep.

At 101 repositories this is also the only fleet that crosses a forge's listing page
(GitHub and GitLab return 100 at a time, Forgejo 50), so it is what exercises the
multi-page path against a live forge rather than a fake server.

Bumping `SEED` in `generate.py` reshuffles every rule assignment without touching any other
logic — useful for checking that a rule pack was not accidentally tuned to one draw.
