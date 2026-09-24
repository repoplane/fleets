#!/usr/bin/env python3
"""Generate the scale fleet: repos/, fleet.yaml and census.json.

    python3 generate.py          # write repos/, fleet.yaml, census.json
    python3 generate.py --check  # exit 1 if the tree on disk differs

Nothing here is hand-edited. This file is the source; everything beside it is output,
and --check is what stops a hand edit quietly becoming the thing everyone tests against.

The idea is that **structure is a literal table and variation is a hash**. Team and
repository names cannot be generated -- a cross product of word lists is exactly what
makes a fixture read as synthetic -- so the layout below is written out. What the hash
decides is only the variation within it: which ecosystem a repository belongs to, which
CI system it uses, which conventional files it happens to have.

Deterministic by construction. Every choice comes from a SHA-256 of the repository's
full fleet path and the dimension being decided, so a regeneration on any machine
produces byte-identical output, and moving a repository between teams reshuffles only
that repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

SEED = "repoplane-scale-v1"
ROOT = Path(__file__).resolve().parent
REPOS = ROOT / "repos"

# The fake company every repository sits under. It earns its place twice: it is the
# namespace that makes the fleet look like an estate, and on Azure DevOps -- where only
# the first segment becomes a project -- it is what keeps the whole fleet in one project
# instead of twelve, each of which is a polled background creation.
COMPANY = "acme"

# Azure DevOps puts the repositories without a namespace in the sandbox's default_project.
# A top-level namespace of that name would collide with it, and forgelab only notices at
# run time, on that forge alone. See ../sandboxes.yaml; kept as a literal so this file
# stays stdlib-only.
RESERVED_PROJECTS = {"fleet"}

EXPECTED_TOTAL = 108
EXPECTED_DEPTHS = {2: 2, 3: 98, 4: 8}
MAX_FLAT = 60


def roll(path: str, dimension: str) -> int:
    """A stable 0-999 for (repository, dimension). Bumping SEED reshuffles every
    variation at once without touching any other logic -- though at this size that means
    rewriting every baseline commit, so treat it as frozen once committed."""
    h = hashlib.sha256(f"{SEED}/{path}/{dimension}".encode()).hexdigest()
    return int(h[:8], 16) % 1000


def weighted(path: str, dimension: str, choices: list[tuple[str, int]]) -> str:
    """Pick from (value, weight) pairs summing to 1000."""
    r, acc = roll(path, dimension), 0
    for value, weight in choices:
        acc += weight
        if r < acc:
            return value
    return choices[-1][0]


# --- the company ------------------------------------------------------------------
# Team sizes are deliberately uneven: a real company has no tidy grid, and a fixture
# that does is one a rule can accidentally be tuned to. Leaf names recur across teams on
# purpose -- ten teams have an "api", nine have "docs" -- because that is both what an
# estate looks like and what forces a rule to key on the full path rather than the leaf.

TEAMS: dict[str, dict] = {
    "payments": {
        "repos": ["api", "worker", "docs", "sdk", "ledger", "settlement",
                  "fraud-scoring", "payouts", "reconciliation", "infra"],
        # A repository beside a sub-namespace in the same parent, and "api"/"worker"
        # recurring at two depths inside one team.
        "subsystems": {"gateway": ["api", "worker", "adapters"]},
    },
    "platform": {
        "repos": ["api", "worker", "docs", "cli", "infra", "charts", "backoffice",
                  "service-catalog", "feature-flags", "build-cache"],
        "subsystems": {"observability": ["collector", "dashboards", "alerting"]},
    },
    "identity": {
        "repos": ["api", "worker", "docs", "web", "sdk", "sso-broker", "session-store",
                  "scim-sync", "mfa", "directory-sync", "charts"],
        "subsystems": {},
    },
    "checkout": {
        "repos": ["api", "worker", "web", "cli", "cart", "tax-engine", "promo-engine",
                  "events", "infra", "docs"],
        "subsystems": {},
    },
    "catalog": {
        "repos": ["api", "worker", "web", "search-indexer", "media-pipeline", "pricing",
                  "sdk", "events", "importer", "docs"],
        "subsystems": {},
    },
    "data": {
        "repos": ["api", "worker", "docs", "warehouse-models", "metrics-store",
                  "notebooks", "lineage", "charts"],
        "subsystems": {"ingest": ["connectors", "scheduler"]},
    },
    "logistics": {
        "repos": ["api", "worker", "web", "carrier-adapters", "label-printer",
                  "tracking", "events", "infra", "backoffice"],
        "subsystems": {},
    },
    "growth": {
        "repos": ["api", "worker", "web", "landing-pages", "experiments", "referrals",
                  "email-templates", "sdk"],
        "subsystems": {},
    },
    "security": {
        "repos": ["api", "worker", "docs", "policy-bundles", "secret-rotator",
                  "vuln-triage", "backoffice"],
        "subsystems": {},
    },
    "mobile": {
        "repos": ["sdk", "ios-app", "android-app", "push-relay", "docs", "web"],
        "subsystems": {},
    },
    "support": {
        "repos": ["api", "docs", "helpdesk-sync", "knowledge-base", "macros"],
        "subsystems": {},
    },
    "sre": {
        "repos": ["cli", "infra", "runbooks", "legacy-deploy"],
        "subsystems": {},
    },
}

# The two repositories a company keeps outside any team. They are also what makes the
# company namespace itself a mixed parent -- repositories beside the twelve team
# namespaces -- which shapes/ does not cover.
ROOT_REPOS = ["handbook", "design-system"]


def paths() -> list[str]:
    """Every repository's full fleet path, sorted."""
    out = [f"{COMPANY}/{leaf}" for leaf in ROOT_REPOS]
    for team, spec in TEAMS.items():
        out += [f"{COMPANY}/{team}/{leaf}" for leaf in spec["repos"]]
        for sub, leaves in spec["subsystems"].items():
            out += [f"{COMPANY}/{team}/{sub}/{leaf}" for leaf in leaves]
    return sorted(out)


def parts(path: str) -> tuple[str | None, str | None, str]:
    """(team, subsystem, leaf) for a full fleet path."""
    seg = path.split("/")[1:]          # drop the company
    if len(seg) == 1:
        return None, None, seg[0]
    if len(seg) == 2:
        return seg[0], None, seg[1]
    return seg[0], seg[1], seg[2]


def flat(path: str) -> str:
    """What GitHub and Forgejo call it: the whole path, "-"-joined."""
    return path.replace("/", "-")


def ado(path: str) -> dict:
    """What Azure DevOps calls it: the first segment is a project, the rest is joined."""
    seg = path.split("/")
    return {"project": seg[0], "repo": "-".join(seg[1:])}


# --- archetypes -------------------------------------------------------------------
# Each returns {relative path: content} for one repository. Content is deliberately
# tiny: realism of *structure* is what a rule matches on, and small repositories are
# what keeps `forgelab reset` cheap at this count.
#
# A ".sh" file is written executable. That is not decoration -- fleet.Digest hashes the
# executable bit, so it is part of the commit SHA and therefore part of what verify
# compares.

def node(leaf):
    return {
        "package.json": json.dumps(
            {"name": leaf, "version": "1.0.0", "private": True,
             "main": "src/index.js", "scripts": {"start": "node src/index.js"}},
            indent=2) + "\n",
        "src/index.js": (
            "const http = require('http');\n\n"
            "http.createServer((_, res) => res.end('ok\\n')).listen(8080);\n"),
    }


def go(leaf):
    return {
        "go.mod": f"module github.com/{COMPANY}/{leaf}\n\ngo 1.23\n",
        "main.go": (
            "package main\n\n"
            'import (\n\t"fmt"\n\t"net/http"\n)\n\n'
            "func main() {\n"
            '\thttp.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {\n'
            '\t\tfmt.Fprintln(w, "ok")\n\t})\n'
            '\thttp.ListenAndServe(":8080", nil)\n}\n'),
    }


def python_(leaf):
    return {
        "pyproject.toml": (
            "[project]\n"
            f'name = "{leaf}"\n'
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


def rust(leaf):
    return {
        "Cargo.toml": f'[package]\nname = "{leaf}"\nversion = "1.0.0"\nedition = "2021"\n',
        "src/main.rs": 'fn main() {\n    println!("ok");\n}\n',
    }


def java(leaf):
    return {
        "pom.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            "  <modelVersion>4.0.0</modelVersion>\n"
            f"  <groupId>com.{COMPANY}</groupId>\n"
            f"  <artifactId>{leaf}</artifactId>\n"
            "  <version>1.0.0</version>\n"
            "</project>\n"),
        "src/main/java/App.java": (
            "public class App {\n"
            "    public static void main(String[] args) {\n"
            '        System.out.println("ok");\n'
            "    }\n}\n"),
    }


def ruby(leaf):
    return {
        "Gemfile": "source 'https://rubygems.org'\n\ngem 'sinatra'\n",
        "app.rb": "require 'sinatra'\n\nget('/') { \"ok\\n\" }\n",
    }


def dotnet(leaf):
    return {
        f"{leaf}.csproj": (
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


def php(leaf):
    return {
        "composer.json": json.dumps(
            {"name": f"{COMPANY}/{leaf}", "type": "project", "require": {"php": ">=8.2"}},
            indent=2) + "\n",
        "public/index.php": "<?php\n\nheader('Content-Type: text/plain');\necho \"ok\\n\";\n",
    }


# The four below carry no conventional manifest, which is the point of having them: they
# are what breaks a rule that assumes every repository is parseable.

def terraform(leaf):
    return {
        "main.tf": (
            'resource "null_resource" "ok" {\n'
            '  triggers = { name = var.name }\n}\n'),
        "variables.tf": f'variable "name" {{\n  type    = string\n  default = "{leaf}"\n}}\n',
        "versions.tf": (
            "terraform {\n"
            '  required_version = ">= 1.6"\n'
            "}\n"),
    }


def helm(leaf):
    return {
        "Chart.yaml": f'apiVersion: v2\nname: {leaf}\nversion: 1.0.0\nappVersion: "1.0.0"\n',
        "values.yaml": "replicaCount: 1\nimage:\n  repository: ok\n  tag: \"1.0.0\"\n",
        "templates/deployment.yaml": (
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: {{ .Chart.Name }}\n"
            "spec:\n"
            "  replicas: {{ .Values.replicaCount }}\n"),
    }


def docs(leaf):
    return {
        "mkdocs.yml": f"site_name: {leaf}\nnav:\n  - Home: index.md\n  - Runbook: runbook.md\n",
        "docs/index.md": f"# {leaf}\n\nWhat this is and who owns it.\n",
        "docs/runbook.md": "# Runbook\n\nWhat to do when it pages.\n",
    }


def shell(leaf):
    return {
        "bin/deploy.sh": "#!/bin/sh\nset -eu\nrsync -a . \"$1\":/srv/app\n",
        "bin/rotate.sh": "#!/bin/sh\nset -eu\nfind /var/log -name '*.log' -mtime +7 -delete\n",
        "Makefile": "deploy:\n\t./bin/deploy.sh prod\n\nrotate:\n\t./bin/rotate.sh\n",
    }


ARCHETYPES = {
    "node": node, "go": go, "python": python_, "rust": rust,
    "java": java, "ruby": ruby, "dotnet": dotnet, "php": php,
    "terraform": terraform, "helm": helm, "docs": docs, "shell": shell,
}

# Base images for the Dockerfile, per archetype. The four manifest-less archetypes are
# absent because they have nothing to containerise -- which is what makes "no Dockerfile"
# a fact about the repository rather than a gap in it.
BASE_IMAGE = {
    "node": ("node", "20.11.0-alpine"), "go": ("golang", "1.23-alpine"),
    "python": ("python", "3.12-slim"), "rust": ("rust", "1.79-slim"),
    "java": ("eclipse-temurin", "21-jre"), "ruby": ("ruby", "3.3-alpine"),
    "dotnet": ("mcr.microsoft.com/dotnet/aspnet", "8.0"), "php": ("php", "8.3-cli"),
    "shell": ("alpine", "3.20"),
}

# A leaf whose name says what it is gets the archetype that name implies. Without this a
# hash will cheerfully put a Cargo.toml in a repository called "docs".
LEAF_ARCHETYPES = {
    "docs": ["docs"], "runbooks": ["docs"], "knowledge-base": ["docs"],
    "notebooks": ["docs"], "macros": ["docs"],
    "charts": ["helm"],
    "infra": ["terraform"],
    "web": ["node"], "landing-pages": ["node"], "backoffice": ["node"],
    "dashboards": ["node"], "email-templates": ["node"],
    "cli": ["go", "rust", "shell"],
    "legacy-deploy": ["shell"], "secret-rotator": ["shell"],
    "ios-app": ["shell"], "android-app": ["java"],
}

# What a team builds in. Repeats are weights: a real team has a stack, and that is most
# of what makes the fleet read as a company rather than a shuffle.
TEAM_STACK = {
    "payments": ["java", "java", "java", "go", "go", "python"],
    "platform": ["go", "go", "rust", "rust", "python", "node"],
    "identity": ["java", "java", "go", "node", "python"],
    "checkout": ["node", "node", "java", "go", "ruby"],
    "catalog": ["python", "python", "node", "go", "java"],
    "data": ["python", "python", "python", "python", "go", "java"],
    # The parts of a company that predate its current stack, and keep it: logistics on
    # .NET, support on PHP. Without a home of their own those ecosystems end up with one
    # repository each, too few for a rule that mishandles them to show up as anything.
    "logistics": ["dotnet", "dotnet", "go", "java", "python"],
    "growth": ["node", "node", "node", "php", "php", "ruby"],
    "security": ["go", "rust", "rust", "python", "shell"],
    "mobile": ["node", "java", "shell", "go"],
    "support": ["php", "php", "ruby", "node"],
    "sre": ["shell", "shell", "go", "python", "terraform", "shell"],
    # The two unowned root repositories.
    None: ["docs", "node"],
}


def archetype_of(path: str) -> str:
    team, _, leaf = parts(path)
    pool = LEAF_ARCHETYPES.get(leaf) or TEAM_STACK[team]
    return pool[roll(path, "archetype") % len(pool)]


# --- CI ---------------------------------------------------------------------------
# Every marker is inert by construction. The file is realistic in shape -- which is what
# a rule matches on -- but nothing ever runs: a GitHub workflow on `workflow_dispatch`
# and a GitLab pipeline on `when: never` mean an apply, and every reset push after it,
# cannot spawn a run that fails for want of a runner, burns minutes, or leaves check-run
# noise that verify knows nothing about. Jenkins and Azure Pipelines never auto-run on
# any of the four forges.

CI_FILES = {
    "github-actions": (".github/workflows/ci.yml",
                       "name: CI\n\n"
                       "# Fixture only: dispatch-only, so an apply never starts a run.\n"
                       "on: workflow_dispatch\n\n"
                       "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
                       "      - uses: actions/checkout@v4\n"
                       "      - run: echo build\n"),
    "gitlab-ci": (".gitlab-ci.yml",
                  "# Fixture only: no pipeline is ever created.\n"
                  "workflow:\n  rules:\n    - when: never\n\n"
                  "build:\n  script:\n    - echo build\n"),
    "azure-pipelines": ("azure-pipelines.yml",
                        "# Fixture only: no CI trigger.\n"
                        "trigger: none\npr: none\n\n"
                        "pool:\n  vmImage: ubuntu-latest\n\n"
                        "steps:\n  - script: echo build\n"),
    "jenkins": ("Jenkinsfile",
                "pipeline {\n"
                "  agent any\n"
                "  stages {\n"
                "    stage('build') {\n"
                "      steps { sh 'echo build' }\n"
                "    }\n  }\n}\n"),
}

CI_WEIGHTS = {
    "code": [("github-actions", 400), ("gitlab-ci", 200), ("azure-pipelines", 100),
             ("jenkins", 100), ("none", 200)],
    "terraform": [("github-actions", 100), ("gitlab-ci", 400), ("azure-pipelines", 200),
                  ("jenkins", 300), ("none", 0)],
    "helm": [("github-actions", 200), ("gitlab-ci", 300), ("azure-pipelines", 0),
             ("jenkins", 300), ("none", 200)],
    "docs": [("github-actions", 300), ("gitlab-ci", 100), ("azure-pipelines", 0),
             ("jenkins", 0), ("none", 600)],
    "shell": [("github-actions", 200), ("gitlab-ci", 0), ("azure-pipelines", 0),
              ("jenkins", 300), ("none", 500)],
}

# A second marker beside the first: the half-finished migration, and the shape that
# defeats any rule that looks for *the* CI system rather than all of them.
SECOND_MARKER = 60


def ci_of(path: str, archetype: str) -> list[str]:
    group = archetype if archetype in CI_WEIGHTS else "code"
    primary = weighted(path, "ci", CI_WEIGHTS[group])
    out = [] if primary == "none" else [primary]
    if out and primary != "jenkins" and roll(path, "ci-second") < SECOND_MARKER:
        out.append("jenkins")
    return out


# --- conventional files -----------------------------------------------------------
# Presence rates for a private company estate, which is a different place from the open
# source one the defaults usually describe: most repositories here are unlicensed and
# have no security policy, and CODEOWNERS follows the team rather than the dice.

README, LICENSE_RATE, SECURITY = 960, 550, 150
CODEOWNERS_BY_TEAM = {
    "platform": 800, "security": 850, "payments": 780, "identity": 700,
    "sre": 600, "data": 450, "checkout": 400, "catalog": 350,
    "logistics": 300, "mobile": 200, "growth": 100, "support": 100, None: 0,
}
DOCKERFILE, DOCKERFILE_PINNED = 550, 200
VENDORED, MONOREPO = 80, 40

LICENSE_TEXT = (
    "MIT License\n\n"
    f"Copyright (c) 2026 {COMPANY}\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    "of this software and associated documentation files (the \"Software\"), to deal\n"
    "in the Software without restriction.\n")


def digest_for(image: str) -> str:
    """A well-formed but synthetic digest, stable per image so the output does not
    change, and obviously not a real one anybody should try to pull."""
    return "sha256:" + hashlib.sha256(f"{SEED}/image/{image}".encode()).hexdigest()


def build(path: str) -> tuple[dict[str, str], dict]:
    """(files, census entry) for one repository."""
    team, subsystem, leaf = parts(path)
    archetype = archetype_of(path)
    files = dict(ARCHETYPES[archetype](leaf))
    has: dict = {}

    has["readme"] = roll(path, "readme") < README
    if has["readme"]:
        owner = f"Owned by the {team} team.\n" if team else "Unowned.\n"
        files["README.md"] = f"# {leaf}\n\nA {archetype} repository at {path}.\n{owner}"

    has["license"] = roll(path, "license") < LICENSE_RATE
    if has["license"]:
        files["LICENSE"] = LICENSE_TEXT

    has["security_policy"] = roll(path, "security") < SECURITY
    if has["security_policy"]:
        files["SECURITY.md"] = (
            f"# Security Policy\n\nReport vulnerabilities to security@{COMPANY}.invalid.\n")

    has["codeowners"] = roll(path, "codeowners") < CODEOWNERS_BY_TEAM[team]
    if has["codeowners"]:
        files["CODEOWNERS"] = f"* @{COMPANY}/{team}\n"

    ci = ci_of(path, archetype)
    for marker in ci:
        rel, content = CI_FILES[marker]
        files[rel] = content

    if archetype in BASE_IMAGE and roll(path, "dockerfile") < DOCKERFILE:
        image, tag = BASE_IMAGE[archetype]
        pinned = roll(path, "dockerfile-pin") < DOCKERFILE_PINNED
        ref = f"{image}@{digest_for(image)}" if pinned else f"{image}:{tag}"
        files["Dockerfile"] = (
            f"FROM {ref}\nWORKDIR /app\nCOPY . .\nCMD [\"echo\", \"ok\"]\n")
        has["dockerfile"] = "pinned" if pinned else "floating"
    else:
        has["dockerfile"] = None

    # Dependencies committed in-tree: a rule that walks files must not read vendor/ as
    # first-party code.
    has["vendor"] = archetype in ("go", "php") and roll(path, "vendored") < VENDORED
    if has["vendor"]:
        files["vendor/modules.txt"] = "# github.com/example/dep v1.2.3\n"
        files["vendor/github.com/example/dep/dep.go"] = "package dep\n"

    # More than one manifest in one repository, so "the" manifest is ambiguous.
    has["monorepo"] = roll(path, "monorepo") < MONOREPO
    if has["monorepo"]:
        files["services/api/go.mod"] = f"module {COMPANY}/{leaf}/api\n\ngo 1.23\n"
        files["services/api/main.go"] = 'package main\n\nfunc main() { println("api") }\n'
        files["services/web/package.json"] = '{\n  "name": "web",\n  "private": true\n}\n'

    # A repository needs a file at its root or forgelab reads the directory as a
    # namespace. Every archetype ships one today; this is here so that adding a
    # nested-only archetype fails safe rather than silently losing the repository.
    if not any("/" not in p for p in files):
        files[".gitattributes"] = "* text=auto\n"

    return files, {
        "team": team, "subsystem": subsystem, "leaf": leaf,
        "depth": path.count("/") + 1,
        "archetype": archetype,
        "flat": flat(path),
        "ado": ado(path),
        "ci": ci,
        "has": has,
    }


def generate() -> dict[str, tuple[dict, dict]]:
    return {p: build(p) for p in paths()}


# --- checks -----------------------------------------------------------------------
# These run on every generate and every --check. Each one is a thing that would
# otherwise be found on a forge, sometimes on only one of them, and usually as damage
# rather than an error.

SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def claimed_elsewhere() -> set[str]:
    """Names a sibling fleet in this repository already owns, case-folded.

    The fleets share a sandbox organisation and forgelab identifies a repository by name,
    so a name used twice means one fleet silently overwrites the other on a live forge --
    and the loser only finds out at verify. A namespaced repository is claimed under both
    its path and the "-"-joined name it lands as on GitHub and Forgejo, and namespaces are
    claimed too: they are projects on Azure DevOps and subgroups on GitLab, and a
    collision there is as real as one between repositories.
    """
    claimed: set[str] = set()

    def walk(repos: Path, d: Path) -> None:
        children = list(d.iterdir())
        rel = d.relative_to(repos).as_posix()
        if d != repos and (not children or any(p.is_file() for p in children)):
            claimed.update({rel.casefold(), rel.replace("/", "-").casefold()})
            return
        if d != repos:                    # a namespace is a name on a forge too
            claimed.update({rel.casefold(), rel.replace("/", "-").casefold()})
        for p in children:
            if p.is_dir():
                walk(repos, p)

    for fleet in sorted(ROOT.parent.iterdir()):
        repos = fleet / "repos"
        if fleet.name != ROOT.name and repos.is_dir():
            walk(repos, repos)
    return claimed


def check(corpus: dict) -> None:
    all_paths = list(corpus)

    for path in all_paths:
        for segment in path.split("/"):
            if not SEGMENT.match(segment):
                raise SystemExit(f"{path}: {segment!r} is not a valid repository name")

    # forgelab refuses two paths that join to the same name, but case-sensitively, while
    # every forge is case-insensitive. This is the stronger check, and the only guard
    # against two fixtures that differ only in case fighting over one repository.
    seen: dict[str, str] = {}
    for path in all_paths:
        key = flat(path).casefold()
        if key in seen:
            raise SystemExit(f"{seen[key]} and {path} are both {key!r} on a forge "
                             "without namespaces")
        seen[key] = path

    if COMPANY in RESERVED_PROJECTS:
        raise SystemExit(f"{COMPANY!r} is a sandbox default_project; see ../sandboxes.yaml")

    for path in all_paths:
        mapped = ado(path)
        if mapped["repo"].casefold() == mapped["project"].casefold():
            raise SystemExit(f"{path}: on Azure DevOps this is {mapped['repo']!r} inside "
                             f"the project of the same name, which silently adopts the "
                             f"repository the project was created with")

    claimed = claimed_elsewhere()
    for path in all_paths:
        for name in (path, flat(path)):
            if name.casefold() in claimed:
                raise SystemExit(f"{path}: another fleet already owns {name!r}")
    for path in all_paths:                # namespaces are names on a forge too
        ns = path.rsplit("/", 1)[0]
        while "/" in ns or ns:
            for name in (ns, ns.replace("/", "-")):
                if name.casefold() in claimed:
                    raise SystemExit(f"{path}: another fleet already owns the namespace "
                                     f"{name!r}")
            if "/" not in ns:
                break
            ns = ns.rsplit("/", 1)[0]

    for path, (files, _) in corpus.items():
        if not any("/" not in p for p in files):
            raise SystemExit(f"{path}: no file at its root, so forgelab reads it as a "
                             "namespace rather than a repository")

    namespaces = {p.rsplit("/", 1)[0] for p in all_paths}
    for ns in namespaces:
        if not any(p.startswith(ns + "/") for p in all_paths):
            raise SystemExit(f"{ns}/: a namespace with no repository under it")

    if len(all_paths) != EXPECTED_TOTAL:
        raise SystemExit(f"{len(all_paths)} repositories, expected {EXPECTED_TOTAL}: "
                         "the page-boundary reasoning in README.md depends on it")
    depths: dict[int, int] = {}
    for path in all_paths:
        depths[path.count("/") + 1] = depths.get(path.count("/") + 1, 0) + 1
    if depths != EXPECTED_DEPTHS:
        raise SystemExit(f"depth histogram {depths}, expected {EXPECTED_DEPTHS}")
    longest = max(all_paths, key=lambda p: len(flat(p)))
    if len(flat(longest)) > MAX_FLAT:
        raise SystemExit(f"{longest} is {len(flat(longest))} characters flattened, "
                         f"over the {MAX_FLAT} this fleet keeps to")


# --- output -----------------------------------------------------------------------

def census(corpus: dict) -> dict:
    """What is in the fleet, as counts. Facts rather than verdicts: a fixture that
    records "compliant" freezes one policy opinion, and the opinion is the consumer's."""
    def tally(values):
        out: dict[str, int] = {}
        for v in values:
            out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))

    entries = [e for _, e in corpus.values()]
    files: dict[str, int] = {}
    for f, _ in corpus.values():
        for rel in f:
            files[rel] = files.get(rel, 0) + 1

    leaves = tally(e["leaf"] for e in entries)
    return {
        "structure": {
            "root": COMPANY,
            "teams": tally(e["team"] for e in entries if e["team"]),
            "unowned": sum(1 for e in entries if not e["team"]),
            "depth": {str(k): v for k, v in sorted(tally(e["depth"] for e in entries).items())},
            "namespaces": len({p.rsplit("/", 1)[0] for p in corpus}),
            "recurring_leaves": {k: v for k, v in leaves.items() if v > 1},
        },
        "census": {
            "archetype": tally(e["archetype"] for e in entries),
            "ci": tally(m for e in entries for m in (e["ci"] or ["none"])),
            "dockerfile": tally(str(e["has"]["dockerfile"]) for e in entries),
            "files": dict(sorted(files.items(), key=lambda kv: (-kv[1], kv[0]))),
        },
    }


def fleet_yaml(corpus: dict) -> str:
    lines = [
        "# Generated by generate.py -- do not edit by hand.",
        "#",
        "# The directory tree under repos/ IS the fleet: a directory holding a file is a",
        "# repository, one holding only directories is a namespace. This file carries only",
        "# the pinned git identity, which is what makes commit SHAs reproducible across",
        "# machines and forges, and the topics a directory cannot express.",
        "#",
        "# Everything else stays at its default: private, on main, no tags, not archived.",
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
    for path, (_, entry) in corpus.items():
        topics = [entry["archetype"], entry["team"] or "unowned"]
        topics.append(entry["ci"][0] if entry["ci"] else "no-ci")
        lines.append(f"  {path}:")
        lines.append(f"    topics: [{', '.join(topics)}]")
    return "\n".join(lines) + "\n"


def write(corpus: dict, into: Path) -> None:
    repos = into / "repos"
    if repos.exists():
        shutil.rmtree(repos)
    for path, (files, _) in corpus.items():
        for rel, content in sorted(files.items()):
            dest = repos / path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
            if rel.endswith(".sh"):
                dest.chmod(0o755)

    body = {"seed": SEED, "generated_by": "generate.py", "repo_count": len(corpus)}
    body.update(census(corpus))
    body["repos"] = {p: e for p, (_, e) in corpus.items()}
    (into / "census.json").write_text(json.dumps(body, indent=2) + "\n")
    (into / "fleet.yaml").write_text(fleet_yaml(corpus))


def snapshot(repos: Path) -> dict[str, tuple[str, bool]]:
    """Content and the executable bit, which is part of the commit SHA."""
    return {
        p.relative_to(repos).as_posix(): (p.read_text(), bool(p.stat().st_mode & 0o111))
        for p in repos.rglob("*") if p.is_file()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="regenerate into a temporary tree and diff; exit 1 on drift")
    args = ap.parse_args()

    corpus = generate()
    check(corpus)

    if args.check:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            write(corpus, Path(tmp))
            stale = [rel for rel in ("census.json", "fleet.yaml")
                     if (ROOT / rel).read_text() != (Path(tmp) / rel).read_text()]
            if snapshot(REPOS) != snapshot(Path(tmp) / "repos"):
                stale.append("repos/")
            if stale:
                print("scale is stale, run generate.py:", ", ".join(stale), file=sys.stderr)
                return 1
        print(f"ok: {len(corpus)} repositories match generate.py")
        return 0

    write(corpus, ROOT)
    c = census(corpus)
    print(f"wrote {len(corpus)} repositories to {REPOS.relative_to(ROOT.parent)}/")
    print(f"  {c['structure']['namespaces']} namespaces, "
          f"depth {dict(c['structure']['depth'])}")
    for label in ("archetype", "ci", "dockerfile"):
        print(f"  {label}: {c['census'][label]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
