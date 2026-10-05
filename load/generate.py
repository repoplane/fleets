#!/usr/bin/env python3
"""Generate the load fleet: repos/, fleet.yaml and census.json.

    python3 generate.py          # write repos/, fleet.yaml, census.json
    python3 generate.py --check  # exit 1 if the tree on disk differs

Nothing here is hand-edited. This file is the source; everything beside it is output,
and --check is what stops a hand edit quietly becoming the thing everyone tests against.

This is ../scale/generate.py at twenty times the size, and the same idea holds: **structure
is a literal table and variation is a hash**. One thing had to give at 2,016 repositories:
writing every repository name out by hand. Divisions, teams and subsystems are still
literal; a team's repositories are drawn from its own literal vocabulary of domain nouns,
bare and with a role suffix ("ledger", "ledger-worker"), so a payments team reads as
payments and never grows a "playlist-api". What the hash decides is which candidates a
team keeps, which ecosystem each one belongs to, and which conventional files it has.

Deterministic by construction. Every choice comes from a SHA-256 of the repository's
full fleet path and the dimension being decided, so a regeneration on any machine
produces byte-identical output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

SEED = "repoplane-load-v1"
ROOT = Path(__file__).resolve().parent
REPOS = ROOT / "repos"

# The fake company every repository sits under. As in scale, it is what keeps the whole
# fleet in one Azure DevOps project -- only the first segment becomes one -- instead of
# ten, each of which is a polled background creation. It also keeps this fleet's names
# apart from scale's "acme".
COMPANY = "bigcorp"

# Azure DevOps puts the repositories without a namespace in the sandbox's default_project.
# A top-level namespace of that name would collide with it, and forgelab only notices at
# run time, on that forge alone. See ../sandboxes.yaml; kept as a literal so this file
# stays stdlib-only.
RESERVED_PROJECTS = {"fleet"}

EXPECTED_TOTAL = 2016
EXPECTED_DEPTHS = {2: 4, 3: 21, 4: 1885, 5: 106}
MAX_FLAT = 64


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
# Ten divisions, each holding teams; a few teams split further into subsystems. Team sizes
# are deliberately uneven, from 7 to 74 -- a real company has no tidy grid, and a fixture
# that does is one a rule can accidentally be tuned to.
#
# A team's "size" is how many of its candidates it keeps. Its candidates are the leaves
# every team might have (COMMON), its own nouns, and each noun with a role suffix. The
# core leaves -- api, worker, docs -- come first, so nearly every team has them and they
# recur across the estate, as in scale; then the bare nouns; then the rest.

CORE = ("api", "worker", "docs")
COMMON = CORE + ("web", "sdk", "cli", "infra", "charts", "events", "backoffice")
SUFFIXES = ("api", "worker", "service", "sync", "ui", "jobs", "adapter", "client",
            "gateway", "cli", "exporter", "importer", "store", "scheduler", "proxy",
            "dashboard")

DIVISIONS: dict[str, dict] = {
    "commerce": {
        "repos": ["docs", "infra"],
        "teams": {
            "catalog": {"size": 49, "nouns": [
                "product", "taxonomy", "media", "attributes", "variants", "inventory-feed",
                "merchandising", "brand", "enrichment"]},
            "checkout": {"size": 54, "nouns": [
                "cart", "order", "tax", "promo", "shipping-quote", "address",
                "payment-intent", "confirmation", "fraud-check", "gift-card"],
                "subsystems": {
                    "express": {"size": 11, "nouns": [
                        "one-click", "wallet", "apple-pay", "google-pay"]}}},
            "pricing": {"size": 32, "nouns": [
                "price", "discount", "currency", "rules", "elasticity", "competitor-scan",
                "quote"]},
            "search": {"size": 44, "nouns": [
                "index", "query", "ranking", "autocomplete", "synonyms", "spellcheck",
                "facets", "crawler"]},
            "recommendations": {"size": 27, "nouns": [
                "model", "features", "candidates", "rerank", "similar-items", "bundles"]},
            "reviews": {"size": 15, "nouns": ["review", "rating", "moderation", "photo"]},
            "storefront": {"size": 64, "nouns": [
                "home", "pdp", "plp", "account", "wishlist", "store-locator", "cms",
                "banners", "i18n", "seo", "edge"],
                "subsystems": {
                    "native-shell": {"size": 9, "nouns": ["bridge", "deeplinks", "push"]}}},
            "marketplace": {"size": 37, "nouns": [
                "seller", "onboarding", "listing", "commission", "payout-request",
                "dispute", "catalog-sync"]},
        },
    },
    "finance": {
        "repos": ["docs", "infra", "controls"],
        "teams": {
            "payments": {"size": 74, "nouns": [
                "authorization", "capture", "refund", "chargeback", "wallet", "card-vault",
                "tokenizer", "three-ds", "routing", "psp"],
                "subsystems": {
                    "gateway": {"size": 15, "nouns": [
                        "adyen", "stripe", "braintree", "worldpay"]},
                    "risk": {"size": 12, "nouns": [
                        "scoring", "rules", "velocity", "blocklist"]}}},
            "ledger": {"size": 37, "nouns": [
                "journal", "account", "posting", "balance", "period-close", "audit-trail",
                "fx"]},
            "billing": {"size": 54, "nouns": [
                "subscription", "invoice", "plan", "usage", "metering", "dunning",
                "proration", "entitlement", "coupon"]},
            "invoicing": {"size": 22, "nouns": [
                "template", "pdf", "delivery", "numbering", "archive"]},
            "tax": {"size": 20, "nouns": ["rates", "nexus", "filing", "exemption", "vat"]},
            "treasury": {"size": 12, "nouns": ["cash", "forecast", "hedging", "bank-feed"]},
            "payouts": {"size": 20, "nouns": [
                "payout", "beneficiary", "schedule", "bank-transfer"]},
            "reconciliation": {"size": 17, "nouns": [
                "matcher", "statement", "settlement", "exceptions"]},
            "procurement": {"size": 10, "nouns": ["supplier", "purchase-order", "approval"]},
        },
    },
    "platform": {
        "repos": ["docs", "infra", "charts"],
        "teams": {
            "compute": {"size": 49, "nouns": [
                "cluster", "autoscaler", "node-pool", "capacity", "spot", "image-builder",
                "admission"]},
            "networking": {"size": 32, "nouns": [
                "ingress", "dns", "load-balancer", "firewall", "vpn", "cdn", "egress"]},
            "storage": {"size": 30, "nouns": [
                "object-store", "block", "backup", "snapshot", "retention", "quota"]},
            "observability": {"size": 49, "nouns": [
                "dashboards", "alerting", "on-call", "slo", "status-page"],
                "subsystems": {
                    "tracing": {"size": 11, "nouns": ["collector", "sampler", "span-store"]},
                    "metrics": {"size": 12, "nouns": [
                        "rules", "recording", "remote-write", "cardinality"]},
                    "logging": {"size": 11, "nouns": [
                        "shipper", "parser", "archive", "redaction"]}}},
            "ci": {"size": 40, "nouns": [
                "runner", "pipeline-templates", "build-cache", "artifact", "release",
                "flaky-tests", "merge-queue"]},
            "developer-tools": {"size": 44, "nouns": [
                "scaffolder", "linters", "codemods", "portal", "service-catalog", "plugin",
                "devcontainer", "golden-paths"]},
            "service-mesh": {"size": 20, "nouns": [
                "sidecar", "control-plane", "mtls", "policy"]},
            "secrets": {"size": 15, "nouns": ["vault", "rotation", "kms", "broker"]},
            "core": {"size": 65, "nouns": [
                "config", "feature-flags", "rate-limiter", "health", "discovery",
                "tenancy", "audit", "cron", "cache", "queue", "event-bus",
                "id-generator"]},
        },
    },
    "data": {
        "repos": ["docs", "infra", "notebooks"],
        "teams": {
            "ingest": {"size": 42, "nouns": [
                "connectors", "cdc", "kafka-connect", "batch-loader", "schema-registry",
                "validation", "backfill"],
                "subsystems": {
                    "partners": {"size": 10, "nouns": [
                        "salesforce", "zendesk", "shopify", "sap"]}}},
            "warehouse": {"size": 54, "nouns": [
                "models", "dbt", "snapshots", "marts", "staging", "seeds", "macros",
                "exposures", "contracts"]},
            "ml-platform": {"size": 42, "nouns": [
                "feature-store", "training", "serving", "registry", "labeling",
                "evaluation", "embeddings"]},
            "analytics": {"size": 47, "nouns": [
                "dashboards", "metrics-layer", "reports", "kpi", "cohort", "funnel",
                "attribution"]},
            "streaming": {"size": 32, "nouns": [
                "topics", "consumers", "stream-processor", "windowing", "dead-letter",
                "replay"]},
            "governance": {"size": 15, "nouns": [
                "lineage", "catalog", "pii-scanner", "retention", "access-review"]},
            "experimentation": {"size": 22, "nouns": [
                "assignment", "analysis", "exposure", "guardrails", "sample-size"]},
        },
    },
    "identity": {
        "repos": ["docs", "infra"],
        "teams": {
            "auth": {"size": 37, "nouns": [
                "login", "token", "session", "oauth", "mfa", "password", "webauthn",
                "captcha"]},
            "accounts": {"size": 30, "nouns": [
                "profile", "preferences", "consent", "deletion", "merge", "verification"]},
            "directory": {"size": 17, "nouns": ["ldap", "scim", "groups", "org-chart"]},
            "permissions": {"size": 25, "nouns": [
                "rbac", "policy", "entitlements", "grants", "audit"]},
            "sso": {"size": 12, "nouns": ["saml", "oidc", "broker", "metadata"]},
        },
    },
    "operations": {
        "repos": ["docs", "infra", "runbooks"],
        "teams": {
            "fulfillment": {"size": 49, "nouns": [
                "allocation", "picking", "packing", "wave", "sla", "order-routing",
                "split-shipment"]},
            "logistics": {"size": 57, "nouns": [
                "carrier", "label", "tracking", "rate-shop", "manifest", "customs",
                "route-planner", "last-mile"],
                "subsystems": {
                    "carriers": {"size": 15, "nouns": [
                        "ups", "fedex", "dhl", "usps", "colissimo"]}}},
            "warehousing": {"size": 37, "nouns": [
                "wms", "slotting", "cycle-count", "receiving", "putaway", "yard"]},
            "returns": {"size": 17, "nouns": [
                "rma", "refund-trigger", "inspection", "restock"]},
            "support": {"size": 35, "nouns": [
                "helpdesk", "macros", "knowledge-base", "chat", "ticket", "csat",
                "escalation", "sla-timer"]},
            "workforce": {"size": 12, "nouns": ["shifts", "timesheet", "labor-forecast"]},
        },
    },
    "growth": {
        "repos": ["docs"],
        "teams": {
            "marketing": {"size": 42, "nouns": [
                "campaigns", "email-templates", "landing-pages", "segments", "newsletter",
                "utm", "brand-assets"]},
            "lifecycle": {"size": 25, "nouns": [
                "journeys", "triggers", "winback", "onboarding-flow", "churn"]},
            "seo": {"size": 12, "nouns": [
                "sitemap", "structured-data", "redirects", "crawler-report"]},
            "referrals": {"size": 12, "nouns": ["invite", "reward", "fraud", "leaderboard"]},
            "ads": {"size": 35, "nouns": [
                "bidder", "audiences", "creatives", "conversions", "attribution-feed",
                "budget"]},
            "notifications": {"size": 27, "nouns": [
                "push", "sms", "email", "in-app", "preferences", "templates"]},
        },
    },
    "mobile": {
        "repos": ["docs"],
        "teams": {
            "ios": {"size": 30, "nouns": [
                "app", "widgets", "watch-app", "design-kit", "analytics-kit",
                "networking-kit"]},
            "android": {"size": 30, "nouns": [
                "app", "wear-app", "design-kit", "analytics-kit", "networking-kit",
                "baseline-profiles"]},
            "mobile-platform": {"size": 25, "nouns": [
                "build-tools", "release-train", "crash-reporting", "remote-config",
                "feature-modules"]},
            "wearables": {"size": 7, "nouns": ["sync", "health-data"]},
        },
    },
    "security": {
        "repos": ["docs", "infra"],
        "teams": {
            "appsec": {"size": 22, "nouns": [
                "sast", "dast", "dependency-scan", "threat-models", "secure-defaults",
                "waf-rules"]},
            "detection": {"size": 20, "nouns": [
                "siem-rules", "sensors", "triage", "playbooks", "honeytokens"]},
            "compliance": {"size": 17, "nouns": [
                "evidence", "controls", "soc2", "pci", "gdpr-requests"]},
            "vuln-management": {"size": 15, "nouns": [
                "scanner", "triage", "sla", "exceptions"]},
        },
    },
    "corporate": {
        "repos": ["docs"],
        "teams": {
            "it": {"size": 20, "nouns": [
                "laptops", "mdm", "okta-workflows", "asset-inventory",
                "onboarding-scripts"]},
            "people-systems": {"size": 15, "nouns": [
                "hris-sync", "payroll-export", "org-sync", "recruiting"]},
            "legal-tech": {"size": 7, "nouns": ["contracts", "e-signature", "dpa"]},
            "intranet": {"size": 10, "nouns": ["portal", "wiki", "search", "announcements"]},
        },
    },
}

# The repositories a company keeps outside any division. They are also what makes the
# company namespace itself a mixed parent, as the division-level repositories do for each
# division.
ROOT_REPOS = ["handbook", "design-system", "engineering-blog", "rfcs"]


def candidates(spec: dict) -> list[str]:
    """Every leaf a team or subsystem could have, without duplicates -- and without a
    suffix the noun already says, which is how "dashboards-dashboard" happens."""
    def says(noun: str, suffix: str) -> bool:
        return suffix in {w.removesuffix("s") for w in noun.split("-")} | set(noun.split("-"))

    out: list[str] = []
    for leaf in [*COMMON, *spec["nouns"],
                 *(f"{n}-{s}" for n in spec["nouns"] for s in SUFFIXES if not says(n, s))]:
        if leaf not in out:
            out.append(leaf)
    return out


def pick(prefix: str, spec: dict) -> list[str]:
    """The `size` leaves a namespace keeps: the core leaves first, then the bare nouns,
    then the rest -- the other common leaves among the suffixed ones -- each tier in hash
    order. Mixing the common leaves into the last tier is what keeps every team from
    having a "web", a "charts" and a "backoffice": a big team usually does, a small one
    rarely."""
    pool = candidates(spec)
    if spec["size"] > len(pool):
        raise SystemExit(f"{prefix}: size {spec['size']} but only {len(pool)} candidates")

    def tier(leaf: str) -> tuple[int, int]:
        rank = 0 if leaf in CORE else 1 if leaf in spec["nouns"] else 2
        return rank, roll(f"{prefix}/{leaf}", "pick")

    return sorted(pool, key=tier)[:spec["size"]]


def paths() -> list[str]:
    """Every repository's full fleet path, sorted."""
    out = [f"{COMPANY}/{leaf}" for leaf in ROOT_REPOS]
    for division, dspec in DIVISIONS.items():
        out += [f"{COMPANY}/{division}/{leaf}" for leaf in dspec["repos"]]
        for team, tspec in dspec["teams"].items():
            prefix = f"{COMPANY}/{division}/{team}"
            out += [f"{prefix}/{leaf}" for leaf in pick(prefix, tspec)]
            for sub, sspec in tspec.get("subsystems", {}).items():
                out += [f"{prefix}/{sub}/{leaf}" for leaf in pick(f"{prefix}/{sub}", sspec)]
    return sorted(out)


def parts(path: str) -> tuple[str | None, str | None, str | None, str]:
    """(division, team, subsystem, leaf) for a full fleet path."""
    *ns, leaf = path.split("/")[1:]    # drop the company
    division, team, subsystem = ns + [None] * (3 - len(ns))
    return division, team, subsystem, leaf


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
    "notebooks": ["docs"], "macros": ["docs"], "playbooks": ["docs"],
    "threat-models": ["docs"], "rfcs": ["docs"], "handbook": ["docs"],
    "evidence": ["docs"], "wiki": ["docs"],
    "charts": ["helm"],
    "infra": ["terraform"], "controls": ["terraform"], "secure-defaults": ["terraform"],
    "web": ["node"], "landing-pages": ["node"], "backoffice": ["node"],
    "dashboards": ["node"], "email-templates": ["node"], "design-system": ["node"],
    "engineering-blog": ["node"], "portal": ["node"], "status-page": ["node"],
    "cli": ["go", "rust", "shell"],
    "onboarding-scripts": ["shell"], "laptops": ["shell"], "mdm": ["shell"],
}

# The same, for a role suffix: "billing-ui" is a frontend whatever billing builds in.
SUFFIX_ARCHETYPES = {
    "ui": ["node"], "dashboard": ["node"], "cli": ["go", "rust", "shell"],
}

# What a division builds in. Repeats are weights: a real division has a stack, and that is
# most of what makes the fleet read as a company rather than a shuffle.
DIVISION_STACK = {
    "commerce": ["node", "node", "java", "go", "python"],
    "finance": ["java", "java", "java", "go", "python"],
    "platform": ["go", "go", "go", "rust", "python"],
    "data": ["python", "python", "python", "java", "go"],
    "identity": ["java", "java", "go", "node"],
    # The parts of a company that predate its current stack, and keep it: operations on
    # .NET, growth on PHP and Ruby. Without a home of their own those ecosystems end up with
    # a handful of repositories, too few for a rule that mishandles them to show up.
    "operations": ["dotnet", "dotnet", "go", "java", "python"],
    "growth": ["node", "node", "node", "php", "ruby"],
    "mobile": ["shell", "java", "node"],
    "security": ["go", "go", "rust", "python", "shell"],
    "corporate": ["python", "node", "shell", "php"],
    # The unowned root repositories.
    None: ["docs", "node"],
}

# Teams that build in something other than their division does.
TEAM_STACK = {
    "commerce/storefront": ["node", "node", "node", "go"],
    "commerce/reviews": ["ruby", "ruby", "node"],
    "data/ml-platform": ["python"],
    "platform/developer-tools": ["go", "rust", "node"],
    "operations/support": ["php", "php", "ruby", "node"],
    "growth/seo": ["node", "python"],
    "mobile/ios": ["shell"],
    "mobile/android": ["java"],
}


def archetype_of(path: str) -> str:
    division, team, _, leaf = parts(path)
    pool = (LEAF_ARCHETYPES.get(leaf)
            or ("-" in leaf and SUFFIX_ARCHETYPES.get(leaf.rsplit("-", 1)[1]))
            or TEAM_STACK.get(f"{division}/{team}")
            or DIVISION_STACK[division])
    return pool[roll(path, "archetype") % len(pool)]


# CI configuration is deliberately absent, as in scale: nothing reads it yet, and GitHub
# and GitLab both auto-discover it, so a trigger written wrong would start runs on every
# apply and every reset push. ../scale/README.md has the reasoning.

# --- conventional files -----------------------------------------------------------
# Presence rates for a private company estate, as in scale: most repositories here are
# unlicensed and have no security policy, and CODEOWNERS follows the division rather than
# the dice.

README, LICENSE_RATE, SECURITY = 960, 550, 150
CODEOWNERS_BY_DIVISION = {
    "security": 850, "platform": 800, "finance": 780, "identity": 700,
    "data": 450, "commerce": 380, "operations": 300, "mobile": 200,
    "corporate": 150, "growth": 100, None: 0,
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


def owner(path: str) -> str | None:
    """The team a repository belongs to, or its division when it sits at division level."""
    division, team, _, _ = parts(path)
    return team or division


def build(path: str) -> tuple[dict[str, str], dict]:
    """(files, census entry) for one repository."""
    division, team, subsystem, leaf = parts(path)
    archetype = archetype_of(path)
    files = dict(ARCHETYPES[archetype](leaf))
    has: dict = {}

    has["readme"] = roll(path, "readme") < README
    if has["readme"]:
        line = (f"Owned by the {team} team.\n" if team
                else f"Owned by the {division} division.\n" if division else "Unowned.\n")
        files["README.md"] = f"# {leaf}\n\nA {archetype} repository at {path}.\n{line}"

    has["license"] = roll(path, "license") < LICENSE_RATE
    if has["license"]:
        files["LICENSE"] = LICENSE_TEXT

    has["security_policy"] = roll(path, "security") < SECURITY
    if has["security_policy"]:
        files["SECURITY.md"] = (
            f"# Security Policy\n\nReport vulnerabilities to security@{COMPANY}.invalid.\n")

    has["codeowners"] = roll(path, "codeowners") < CODEOWNERS_BY_DIVISION[division]
    if has["codeowners"]:
        files["CODEOWNERS"] = f"* @{COMPANY}/{owner(path)}\n"

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
        "division": division, "team": team, "subsystem": subsystem, "leaf": leaf,
        "depth": path.count("/") + 1,
        "archetype": archetype,
        "flat": flat(path),
        "ado": ado(path),
        "has": has,
    }


def generate() -> dict[str, tuple[dict, dict]]:
    return {p: build(p) for p in paths()}


# --- checks -----------------------------------------------------------------------
# These run on every generate and every --check. Each one is a thing that would
# otherwise be found on a forge, sometimes on only one of them, and usually as damage
# rather than an error.

SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TOPIC = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")


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
    # against two fixtures that differ only in case fighting over one repository. At this
    # size it also catches a namespace and a leaf that join to the same name, such as a
    # team "checkout" with a repository "express-api" beside a subsystem "express" holding
    # an "api".
    seen: dict[str, str] = {}
    for path in all_paths:
        key = flat(path).casefold()
        if key in seen:
            raise SystemExit(f"{seen[key]} and {path} are both {key!r} on a forge "
                             "without namespaces")
        seen[key] = path

    # GitHub refuses a topic that is not lowercase letters, digits and hyphens, at most 50.
    for path, (_, entry) in corpus.items():
        for topic in (entry["archetype"], owner(path) or "unowned"):
            if not TOPIC.match(topic):
                raise SystemExit(f"{path}: {topic!r} is not a valid topic")

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

    # A path that is both a repository and a namespace: forgelab would read it as a
    # repository and lose everything under it.
    repo_set = set(all_paths)
    for path in all_paths:
        ns = path.rsplit("/", 1)[0]
        if ns in repo_set:
            raise SystemExit(f"{ns} is a repository and the namespace holding {path}")

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
            "divisions": tally(e["division"] for e in entries if e["division"]),
            # Keyed by division as well: a team name is only unique within its division.
            "teams": tally(f"{e['division']}/{e['team']}" for e in entries if e["team"]),
            "unowned": sum(1 for e in entries if not e["division"]),
            "depth": {str(k): v for k, v in sorted(tally(e["depth"] for e in entries).items())},
            "namespaces": len({p.rsplit("/", 1)[0] for p in corpus}),
            "recurring_leaves": {k: v for k, v in leaves.items() if v > 1},
        },
        "census": {
            "archetype": tally(e["archetype"] for e in entries),
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
        topics = [entry["archetype"], owner(path) or "unowned"]
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
                print("load is stale, run generate.py:", ", ".join(stale), file=sys.stderr)
                return 1
        print(f"ok: {len(corpus)} repositories match generate.py")
        return 0

    write(corpus, ROOT)
    c = census(corpus)
    print(f"wrote {len(corpus)} repositories to {REPOS.relative_to(ROOT.parent)}/")
    print(f"  {c['structure']['namespaces']} namespaces, "
          f"depth {dict(c['structure']['depth'])}")
    for label in ("archetype", "dockerfile"):
        print(f"  {label}: {c['census'][label]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
