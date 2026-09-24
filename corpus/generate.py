#!/usr/bin/env python3
"""Generate the corpus fleet: repos/, fleet.yaml and labels.json.

Deterministic by construction. Every choice is derived from a SHA-256 of the
repository name and the dimension being decided, so a regeneration on any machine
produces byte-identical output and `git status` stays clean unless SEED or the
archetypes below actually change.

    python3 generate.py          # write repos/, fleet.yaml, labels.json
    python3 generate.py --check  # exit 1 if the tree on disk differs

The point of this fleet is not size. It is that a rule applied across it lands on a
mix of compliant, violating and not-applicable repositories, so a convergence number
measured against it means something. labels.json is the ground truth that makes it
measurable: it says, per repository and per rule, what the right answer is.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

SEED = "repoplane-corpus-v1"
ROOT = Path(__file__).resolve().parent
REPOS = ROOT / "repos"

# 101 repositories: 96 generated plus 5 in the tail. Ninety-six clears a forge page
# (GitHub and GitLab list 100 at a time, Forgejo 50), so the corpus is the only fleet
# that exercises the multi-page path against a live forge.
#
# Only the total is fixed here. Archetypes are assigned by hashing the repository name,
# so the spread lands near this figure rather than exactly on it -- which is both more
# realistic and what lets a name leave the pool without reshuffling everything after it.
PER_ARCHETYPE = 12

DOMAINS = [
    "billing", "checkout", "ledger", "orders", "catalog", "identity",
    "shipping", "pricing", "inventory", "payments", "notify", "search",
    "reporting", "audit", "tenancy", "scheduling",
]
# "relay" is spare capacity: names claimed by another fleet are dropped from the pool, and
# the shortfall is backfilled from the end, so an exclusion costs two names rather than
# reshuffling the whole corpus.
KINDS = ["api", "svc", "worker", "gateway", "job", "bridge", "relay"]


def roll(name: str, dimension: str) -> int:
    """A stable 0-999 for (repo, dimension). The seed is mixed in so the whole corpus
    can be reshuffled by bumping SEED, without touching any other logic."""
    h = hashlib.sha256(f"{SEED}/{name}/{dimension}".encode()).hexdigest()
    return int(h[:8], 16) % 1000


# --- archetypes -------------------------------------------------------------------
# Each returns the ecosystem files for one repository. Content is deliberately tiny:
# realism of *structure* is what repoplane rules match on, and small repos are what
# keeps `forgelab reset` cheap at this count.

def node(name):
    return {
        "package.json": json.dumps(
            {"name": name, "version": "1.0.0", "private": True,
             "main": "src/index.js", "scripts": {"start": "node src/index.js"}},
            indent=2) + "\n",
        "src/index.js": (
            "const http = require('http');\n\n"
            "http.createServer((_, res) => res.end('ok\\n')).listen(8080);\n"),
    }


def go(name):
    return {
        "go.mod": f"module github.com/repoplane-sandbox/{name}\n\ngo 1.23\n",
        "main.go": (
            "package main\n\n"
            'import (\n\t"fmt"\n\t"net/http"\n)\n\n'
            "func main() {\n"
            '\thttp.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {\n'
            '\t\tfmt.Fprintln(w, "ok")\n\t})\n'
            '\thttp.ListenAndServe(":8080", nil)\n}\n'),
    }


def python_(name):
    return {
        "pyproject.toml": (
            "[project]\n"
            f'name = "{name}"\n'
            'version = "1.0.0"\n'
            'requires-python = ">=3.11"\n'),
        "src/app.py": (
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n\n\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200)\n"
            "        self.end_headers()\n"
            "        self.wfile.write(b'ok\\n')\n\n\n"
            "HTTPServer(('', 8080), Handler).serve_forever()\n"),
    }


def rust(name):
    return {
        "Cargo.toml": (
            "[package]\n"
            f'name = "{name}"\n'
            'version = "1.0.0"\n'
            'edition = "2021"\n'),
        "src/main.rs": 'fn main() {\n    println!("ok");\n}\n',
    }


def java(name):
    return {
        "pom.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            "  <modelVersion>4.0.0</modelVersion>\n"
            "  <groupId>io.repoplane</groupId>\n"
            f"  <artifactId>{name}</artifactId>\n"
            "  <version>1.0.0</version>\n"
            "</project>\n"),
        "src/main/java/App.java": (
            "public class App {\n"
            "    public static void main(String[] args) {\n"
            '        System.out.println("ok");\n'
            "    }\n}\n"),
    }


def ruby(name):
    return {
        "Gemfile": "source 'https://rubygems.org'\n\ngem 'sinatra'\n",
        "app.rb": "require 'sinatra'\n\nget('/') { \"ok\\n\" }\n",
    }


def dotnet(name):
    return {
        f"{name}.csproj": (
            '<Project Sdk="Microsoft.NET.Sdk.Web">\n'
            "  <PropertyGroup>\n"
            "    <TargetFramework>net8.0</TargetFramework>\n"
            "  </PropertyGroup>\n"
            "</Project>\n"),
        "Program.cs": (
            "var app = WebApplication.CreateBuilder(args).Build();\n"
            'app.MapGet("/", () => "ok");\n'
            "app.Run();\n"),
    }


def php(name):
    return {
        "composer.json": json.dumps(
            {"name": f"repoplane/{name}", "type": "project", "require": {"php": ">=8.2"}},
            indent=2) + "\n",
        "public/index.php": "<?php\n\nheader('Content-Type: text/plain');\necho \"ok\\n\";\n",
    }


ARCHETYPES = {
    "node": node, "go": go, "python": python_, "rust": rust,
    "java": java, "ruby": ruby, "dotnet": dotnet, "php": php,
}

# Base images per archetype, for the Dockerfile rule.
BASE_IMAGE = {
    "node": ("node", "20.11.0-alpine"), "go": ("golang", "1.23-alpine"),
    "python": ("python", "3.12-slim"), "rust": ("rust", "1.79-slim"),
    "java": ("eclipse-temurin", "21-jre"), "ruby": ("ruby", "3.3-alpine"),
    "dotnet": ("mcr.microsoft.com/dotnet/aspnet", "8.0"), "php": ("php", "8.3-cli"),
}

# A fake but well-formed digest, derived from the image name so it is stable and
# obviously synthetic rather than a real image anyone might try to pull.
def digest_for(image: str) -> str:
    return "sha256:" + hashlib.sha256(f"{SEED}/image/{image}".encode()).hexdigest()


# --- rules ------------------------------------------------------------------------
# Each rule is (name, probability the repo complies). The probabilities are not
# uniform on purpose: a corpus where every rule is missed at the same rate teaches a
# convergence metric nothing. These roughly mirror what a real estate looks like --
# READMEs almost everywhere, CODEOWNERS rarely.
RULES = [
    ("readme", 970),
    ("license", 850),
    ("security-policy", 550),
    ("ci-workflow", 800),
    ("codeowners", 400),
]
# Dockerfile is three-state: absent (not applicable), floating tag, or digest-pinned.
DOCKERFILE_PRESENT = 620
DOCKERFILE_PINNED = 500

LICENSE_TEXT = (
    "MIT License\n\n"
    "Copyright (c) 2026 repoplane\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    "of this software and associated documentation files (the \"Software\"), to deal\n"
    "in the Software without restriction.\n")

CI_YML = (
    "name: CI\n\n"
    "on:\n  push:\n    branches: [main]\n  pull_request:\n\n"
    "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
    "      - uses: actions/checkout@v4\n"
    "      - run: echo build\n")


def claimed_elsewhere() -> set[str]:
    """Repository names another fleet in this repository already owns.

    Both fleets are applied to the same sandbox organisation and forgelab identifies a
    repository by name, so a name used twice means one fleet silently overwrites the
    other's content on a live forge -- and the loser only finds out at `verify`. Reading
    the sibling fleet is what keeps that from being a thing anyone has to remember.
    """
    claimed = set()
    for fleet in sorted((ROOT.parent).iterdir()):
        repos = fleet / "repos"
        if fleet.name == ROOT.name or not repos.is_dir():
            continue
        claimed |= {p.name for p in repos.iterdir() if p.is_dir()}
    return claimed


def names() -> list[str]:
    """Distinct <domain>-<kind> names that no sibling fleet claims, in a fixed order."""
    claimed = claimed_elsewhere()
    pool = [f"{d}-{k}" for k in KINDS for d in DOMAINS if f"{d}-{k}" not in claimed]
    want = len(ARCHETYPES) * PER_ARCHETYPE
    if len(pool) < want:
        raise SystemExit(
            f"name pool exhausted: {len(pool)} usable, need {want}. Add a domain or a kind.")
    return pool[:want]


def build_repo(name: str, archetype: str) -> tuple[dict, dict]:
    """Return (files, labels) for one generated repository."""
    files = dict(ARCHETYPES[archetype](name))
    rules: dict[str, dict] = {}

    for rule, threshold in RULES:
        compliant = roll(name, rule) < threshold
        rules[rule] = {"compliant": compliant}
        if not compliant:
            continue
        if rule == "readme":
            files["README.md"] = (
                f"# {name}\n\n"
                f"A {archetype} service in the repoplane corpus fleet.\n")
        elif rule == "license":
            files["LICENSE"] = LICENSE_TEXT
        elif rule == "security-policy":
            files["SECURITY.md"] = (
                "# Security Policy\n\n"
                "Report vulnerabilities to security@repoplane.invalid.\n")
        elif rule == "ci-workflow":
            files[".github/workflows/ci.yml"] = CI_YML
        elif rule == "codeowners":
            files["CODEOWNERS"] = "* @repoplane/platform\n"

    # A repository needs at least one file at its root, or forgelab reads the directory
    # as a namespace rather than a repository. Every archetype ships a root manifest, so
    # this never fires today; it is here so adding a nested-only archetype fails safe.
    if not any("/" not in p for p in files):
        files[".gitattributes"] = "* text=auto\n"

    image, tag = BASE_IMAGE[archetype]
    if roll(name, "dockerfile") < DOCKERFILE_PRESENT:
        pinned = roll(name, "dockerfile-pin") < DOCKERFILE_PINNED
        ref = f"{image}@{digest_for(image)}" if pinned else f"{image}:{tag}"
        files["Dockerfile"] = (
            f"FROM {ref}\n"
            "WORKDIR /app\n"
            "COPY . .\n"
            'CMD ["echo", "ok"]\n')
        rules["dockerfile-pinned"] = {"compliant": pinned}
    else:
        rules["dockerfile-pinned"] = {"compliant": None, "reason": "no Dockerfile"}

    return files, {"archetype": archetype, "tail": False, "rules": rules}


# --- the tail ---------------------------------------------------------------------
# Five repositories that fit no archetype. They exist because the measured reality is
# that the hard cases do not cluster: a rule pack tuned on the 96 above should still
# have to make a decision about these, and several of those decisions are "not
# applicable" rather than "violating".

def tail_repos() -> dict[str, tuple[dict, dict]]:
    def entry(files, note, rules):
        return files, {"archetype": None, "tail": True, "note": note, "rules": rules}

    na = lambda reason: {"compliant": None, "reason": reason}

    return {
        # No manifest of any kind: shell scripts committed over a decade.
        "legacy-monolith": entry(
            {"README.md": "# legacy-monolith\n\nNo build file. Deploys by rsync.\n",
             "deploy.sh": "#!/bin/sh\nrsync -a . prod:/srv/app\n",
             "cron.sh": "#!/bin/sh\n/srv/app/run nightly\n"},
            "no manifest; not a buildable project",
            {"readme": {"compliant": True}, "license": {"compliant": False},
             "security-policy": {"compliant": False},
             "ci-workflow": na("nothing to build"),
             "codeowners": {"compliant": False},
             "dockerfile-pinned": na("no Dockerfile")}),

        # Documentation only. Most code rules simply do not apply.
        "docs-portal": entry(
            {"README.md": "# docs-portal\n\nProse only.\n",
             "docs/index.md": "# Index\n",
             "docs/runbook.md": "# Runbook\n"},
            "documentation only; code rules are not applicable",
            {"readme": {"compliant": True}, "license": {"compliant": True},
             "security-policy": na("no code"), "ci-workflow": na("no code"),
             "codeowners": {"compliant": True},
             "dockerfile-pinned": na("no Dockerfile")}),

        # Dependencies committed in-tree: a rule that walks files must not treat
        # vendor/ as first-party.
        "vendored-tool": entry(
            {"README.md": "# vendored-tool\n\nDependencies are committed.\n",
             "go.mod": "module github.com/repoplane-sandbox/vendored-tool\n\ngo 1.23\n",
             "main.go": 'package main\n\nfunc main() { println("ok") }\n',
             "vendor/modules.txt": "# github.com/example/dep v1.2.3\n",
             "vendor/github.com/example/dep/dep.go": "package dep\n"},
            "vendored dependencies; file-walking rules must skip vendor/",
            {"readme": {"compliant": True}, "license": {"compliant": False},
             "security-policy": {"compliant": False},
             "ci-workflow": {"compliant": False},
             "codeowners": {"compliant": False},
             "dockerfile-pinned": na("no Dockerfile")}),

        # Several projects in one repository: "the" manifest is ambiguous.
        "platform-monorepo": entry(
            {"README.md": "# platform-monorepo\n\nThree projects in one repository.\n",
             "CODEOWNERS": "/services/ @repoplane/platform\n",
             "services/api/go.mod": "module platform/api\n\ngo 1.23\n",
             "services/api/main.go": 'package main\n\nfunc main() { println("api") }\n',
             "services/web/package.json": '{\n  "name": "web",\n  "private": true\n}\n',
             "libs/shared/pyproject.toml": '[project]\nname = "shared"\nversion = "0.1.0"\n'},
            "multiple manifests; per-repo rules are ambiguous by design",
            {"readme": {"compliant": True}, "license": {"compliant": False},
             "security-policy": {"compliant": False},
             "ci-workflow": {"compliant": False},
             "codeowners": {"compliant": True},
             "dockerfile-pinned": na("no Dockerfile")}),

        # Stale and nearly empty: the shape an abandoned experiment leaves behind.
        "abandoned-spike": entry(
            {"NOTES.txt": "tried the thing. did not work. left for reference.\n"},
            "no README, no manifest; nearly empty",
            {"readme": {"compliant": False}, "license": {"compliant": False},
             "security-policy": {"compliant": False},
             "ci-workflow": na("nothing to build"),
             "codeowners": {"compliant": False},
             "dockerfile-pinned": na("no Dockerfile")}),
    }


def generate() -> dict:
    """Build the whole corpus in memory: {repo: (files, labels)}."""
    corpus: dict[str, tuple[dict, dict]] = {}
    archetypes = sorted(ARCHETYPES)
    for name in names():
        # Derived from the name, not its position: dropping a name from the pool then
        # shifts nothing else, so an exclusion costs two repositories of churn instead
        # of re-pushing most of the corpus to three forges.
        corpus[name] = build_repo(name, archetypes[roll(name, "archetype") % len(archetypes)])
    corpus.update(tail_repos())
    return dict(sorted(corpus.items()))


def totals(corpus: dict) -> dict:
    """Per-rule denominators. These are what a convergence number is a fraction of:
    'not applicable' is counted separately so it never silently inflates compliance."""
    out: dict[str, dict] = {}
    for _, labels in corpus.values():
        for rule, verdict in labels["rules"].items():
            t = out.setdefault(rule, {"compliant": 0, "violating": 0, "not_applicable": 0})
            if verdict["compliant"] is None:
                t["not_applicable"] += 1
            elif verdict["compliant"]:
                t["compliant"] += 1
            else:
                t["violating"] += 1
    return dict(sorted(out.items()))


def fleet_yaml(corpus: dict) -> str:
    """Only what a directory cannot express. Visibility stays private throughout: the
    one public repository in this setup lives in shapes/, on purpose."""
    lines = [
        "# Generated by generate.py -- do not edit by hand.",
        "#",
        "# The directory tree under repos/ IS the fleet. This file carries only the",
        "# pinned git identity (which is what makes commit SHAs reproducible across",
        "# machines and forges) and the per-repository topics.",
        "",
        "version: 1",
        "",
        "git:",
        "  author:",
        "    name: Forgelab Fixture",
        "    email: fixture@forgelab.test",
        '  timestamp: "2026-01-01T00:00:00Z"',
        "",
        "defaults:",
        "  visibility: private",
        "  default_branch: main",
        "",
        "repos:",
    ]
    for name, (_, labels) in corpus.items():
        topics = [labels["archetype"]] if labels["archetype"] else ["untyped"]
        if labels["tail"]:
            topics.append("tail")
        lines.append(f"  {name}:")
        lines.append(f"    topics: [{', '.join(topics)}]")
    return "\n".join(lines) + "\n"


def write(corpus: dict, into: Path) -> None:
    repos = into / "repos"
    if repos.exists():
        shutil.rmtree(repos)
    for name, (files, _) in corpus.items():
        for rel, content in sorted(files.items()):
            path = repos / name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    labels = {
        "seed": SEED,
        "generated_by": "generate.py",
        "repo_count": len(corpus),
        "totals": totals(corpus),
        "repos": {name: lab for name, (_, lab) in corpus.items()},
    }
    (into / "labels.json").write_text(json.dumps(labels, indent=2, sort_keys=False) + "\n")
    (into / "fleet.yaml").write_text(fleet_yaml(corpus))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="regenerate into a temporary tree and diff; exit 1 on drift")
    args = ap.parse_args()

    corpus = generate()

    if args.check:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            write(corpus, Path(tmp))
            diff = []
            for rel in ("labels.json", "fleet.yaml"):
                if (ROOT / rel).read_text() != (Path(tmp) / rel).read_text():
                    diff.append(rel)
            a = {p.relative_to(REPOS): p.read_text() for p in REPOS.rglob("*") if p.is_file()}
            b = {p.relative_to(Path(tmp) / "repos"): p.read_text()
                 for p in (Path(tmp) / "repos").rglob("*") if p.is_file()}
            if a != b:
                diff.append("repos/")
            if diff:
                print("corpus is stale, run generate.py:", ", ".join(diff), file=sys.stderr)
                return 1
        print(f"ok: {len(corpus)} repositories match generate.py")
        return 0

    write(corpus, ROOT)
    t = totals(corpus)
    print(f"wrote {len(corpus)} repositories to {REPOS.relative_to(ROOT.parent)}/")
    width = max(len(r) for r in t)
    for rule, counts in t.items():
        print(f"  {rule:<{width}}  {counts['compliant']:>3} ok  "
              f"{counts['violating']:>3} violating  {counts['not_applicable']:>3} n/a")
    return 0


if __name__ == "__main__":
    sys.exit(main())
