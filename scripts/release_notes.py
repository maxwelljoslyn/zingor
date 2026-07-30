#!/usr/bin/env python3
"""Generate issue-first release notes for a git tag range.

GitHub's built-in generator lists the pull request that carried a change. This
script lists the *issue* the change closed instead, which is usually what a
reader cares about, and it covers work that never went through a PR at all.

For every commit in the range, the change is attributed in this order:

1. ``Closes #N`` / ``Fixes #N`` / ``Resolves #N`` trailers in the commit message.
2. The ``closingIssuesReferences`` of any merged PR containing the commit. This
   picks up issues linked through the PR body or the Development sidebar, and
   works with rebase merges since GitHub keeps the commit/PR association
   regardless of merge strategy.
3. The merged PR itself, when it closes no issue (chores, refactors).
4. The commit subject, when there is no PR either.

Entries are deduplicated by what they point at, so two commits closing one
issue produce one bullet, and a squashed-then-referenced issue is not double
counted. Categories, excluded labels and excluded authors are read from
``.github/release.yml`` so grouping matches GitHub's own button.

Usage::

    uv run --with pyyaml scripts/release_notes.py
    uv run --with pyyaml scripts/release_notes.py --from v0.3.2 --to v0.4.0
    uv run --with pyyaml scripts/release_notes.py --include-refs --credit

Pipe the result into a release once it looks right::

    uv run --with pyyaml scripts/release_notes.py > notes.md
    gh release create v0.4.0 --notes-file notes.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_CANDIDATES = (".github/release.yml", ".github/release.yaml")
CLOSING_KEYWORDS = "closes|close|closed|fixes|fixed|fix|resolves|resolved|resolve"
REFERENCE_KEYWORDS = "refs|ref|references|see"
CLOSING_TRAILER = re.compile(
    rf"^\s*(?:{CLOSING_KEYWORDS})\b(?P<numbers>[\s,#\d]+)$",
    re.IGNORECASE | re.MULTILINE,
)
REFERENCE_TRAILER = re.compile(
    rf"^\s*(?:{REFERENCE_KEYWORDS})\b(?P<numbers>[\s,#\d]+)$",
    re.IGNORECASE | re.MULTILINE,
)
ISSUE_NUMBER = re.compile(r"#(\d+)")
COMMIT_FIELD_SEPARATOR = "\x1f"
COMMIT_RECORD_SEPARATOR = "\x1e"
GRAPHQL_BATCH = 40
# The `bump` script commits "Bump version to x.y.z" immediately before tagging,
# so that commit lands in every range and never has an issue or PR behind it.
DEFAULT_COMMIT_EXCLUDE = re.compile(r"^Bump version\b", re.IGNORECASE)

COMMIT_FRAGMENT = """
fragment CommitInfo on Commit {
  oid
  associatedPullRequests(first: 5) {
    nodes {
      number
      merged
      closingIssuesReferences(first: 10) { nodes { number } }
    }
  }
}
"""

ITEM_FRAGMENTS = """
fragment IssueInfo on Issue {
  number
  title
  url
  author { login }
  labels(first: 20) { nodes { name } }
}
fragment PullInfo on PullRequest {
  number
  title
  url
  author { login }
  labels(first: 20) { nodes { name } }
}
"""


@dataclass(frozen=True)
class Entry:
    """One bullet in the generated notes."""

    key: tuple[str, str]
    title: str
    ref: str
    url: str | None
    author: str | None
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Commit:
    """A commit in the range being described."""

    sha: str
    subject: str
    message: str


def run_git(*args: str) -> str:
    """Run a git command in the repository and return its stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("git " + " ".join(args) + " failed: " + result.stderr.strip())
    return result.stdout.strip()


def graphql(query: str, **variables: str) -> dict:
    """Execute a GraphQL query through `gh` and return the `data` payload."""
    command = ["gh", "api", "graphql", "-f", f"query={query}"]
    for name, value in variables.items():
        command += ["-f", f"{name}={value}"]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit("gh api graphql failed: " + result.stderr.strip())
    payload = json.loads(result.stdout)
    if payload.get("errors"):
        messages = "; ".join(error.get("message", "?") for error in payload["errors"])
        raise SystemExit("GraphQL errors: " + messages)
    return payload["data"]


def repository_slug() -> tuple[str, str]:
    """Return the (owner, name) of the `origin` remote."""
    url = run_git("remote", "get-url", "origin")
    match = re.search(r"(?:github\.com[:/])([^/]+)/(.+?)(?:\.git)?$", url)
    if not match:
        raise SystemExit(f"cannot parse a GitHub owner/name out of {url!r}")
    return match.group(1), match.group(2)


def resolve_range(start: str | None, end: str | None) -> tuple[str, str]:
    """Fill in the newest tag and its predecessor for any unspecified endpoint."""
    end = end or run_git("describe", "--tags", "--abbrev=0")
    start = start or run_git("describe", "--tags", "--abbrev=0", f"{end}^")
    return start, end


def load_config(explicit: Path | None) -> dict:
    """Load the release-notes config, returning an empty config if none exists."""
    paths = [explicit] if explicit else [REPO_ROOT / name for name in CONFIG_CANDIDATES]
    for path in paths:
        if path and path.is_file():
            return yaml.safe_load(path.read_text()) or {}
    return {}


def read_commits(start: str, end: str) -> list[Commit]:
    """Return the commits in `start..end`, oldest first."""
    template = COMMIT_FIELD_SEPARATOR.join(["%H", "%s", "%B"]) + COMMIT_RECORD_SEPARATOR
    raw = run_git("log", "--reverse", f"--format={template}", f"{start}..{end}")
    commits = []
    for record in raw.split(COMMIT_RECORD_SEPARATOR):
        record = record.strip("\n")
        if not record.strip():
            continue
        sha, subject, message = record.split(COMMIT_FIELD_SEPARATOR)
        commits.append(Commit(sha=sha, subject=subject, message=message))
    return commits


def chunked(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    """Yield `items` in slices of at most `size`."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def trailer_numbers(message: str, pattern: re.Pattern[str]) -> list[int]:
    """Return the issue numbers named by trailers matching `pattern`."""
    numbers = []
    for match in pattern.finditer(message):
        numbers += [
            int(number) for number in ISSUE_NUMBER.findall(match.group("numbers"))
        ]
    return numbers


def fetch_commit_pulls(
    owner: str, name: str, shas: Sequence[str]
) -> dict[str, list[dict]]:
    """Map each commit sha to the merged pull requests that contain it."""
    pulls: dict[str, list[dict]] = {}
    for batch in chunked(shas, GRAPHQL_BATCH):
        aliases = "\n".join(
            f'    c{index}: object(oid: "{sha}") {{ ...CommitInfo }}'
            for index, sha in enumerate(batch)
        )
        query = (
            "query($owner: String!, $name: String!) {\n"
            + "  repository(owner: $owner, name: $name) {\n"
            + aliases
            + "\n  }\n}\n"
            + COMMIT_FRAGMENT
        )
        data = graphql(query, owner=owner, name=name)["repository"]
        for index, sha in enumerate(batch):
            node = data.get(f"c{index}") or {}
            associated = (node.get("associatedPullRequests") or {}).get("nodes") or []
            pulls[sha] = [pull for pull in associated if pull.get("merged")]
    return pulls


def fetch_items(owner: str, name: str, numbers: Iterable[int]) -> dict[int, dict]:
    """Look up issues (or PRs) by number, since both share one numbering pool."""
    wanted = sorted(set(numbers))
    items: dict[int, dict] = {}
    for batch in chunked([str(number) for number in wanted], GRAPHQL_BATCH):
        aliases = "\n".join(
            f"    n{number}: issueOrPullRequest(number: {number})"
            + " { __typename ...IssueInfo ...PullInfo }"
            for number in batch
        )
        query = (
            "query($owner: String!, $name: String!) {\n"
            + "  repository(owner: $owner, name: $name) {\n"
            + aliases
            + "\n  }\n}\n"
            + ITEM_FRAGMENTS
        )
        data = graphql(query, owner=owner, name=name)["repository"]
        for number in batch:
            node = data.get(f"n{number}")
            if node:
                items[int(number)] = node
    return items


def label_names(node: dict) -> tuple[str, ...]:
    """Return the label names on an issue or pull request node."""
    labels = (node.get("labels") or {}).get("nodes") or []
    return tuple(label["name"] for label in labels if label.get("name"))


def author_login(node: dict) -> str | None:
    """Return the login of a node's author, if the account still exists."""
    return (node.get("author") or {}).get("login")


def entry_for_item(number: int, node: dict) -> Entry:
    """Build an entry pointing at an issue or pull request."""
    kind = "issue" if node.get("__typename") == "Issue" else "pr"
    return Entry(
        key=(kind, str(number)),
        title=node.get("title") or f"#{number}",
        ref=f"#{number}",
        url=node.get("url"),
        author=author_login(node),
        labels=label_names(node),
    )


def entry_for_commit(commit: Commit, owner: str, name: str) -> Entry:
    """Build an entry pointing at a bare commit."""
    return Entry(
        key=("commit", commit.sha),
        title=commit.subject,
        ref=commit.sha[:7],
        url=f"https://github.com/{owner}/{name}/commit/{commit.sha}",
        author=None,
        labels=(),
    )


def collect_entries(
    commits: Sequence[Commit],
    pulls: dict[str, list[dict]],
    items: dict[int, dict],
    owner: str,
    name: str,
) -> tuple[dict[tuple[str, str], Entry], dict[tuple[str, str], Entry]]:
    """Turn commits into deduplicated closing entries and referenced-only entries."""
    closing: dict[tuple[str, str], Entry] = {}
    referenced: dict[tuple[str, str], Entry] = {}
    for commit in commits:
        commit_pulls = pulls.get(commit.sha, [])
        numbers = trailer_numbers(commit.message, CLOSING_TRAILER)
        for pull in commit_pulls:
            closes = (pull.get("closingIssuesReferences") or {}).get("nodes") or []
            numbers += [issue["number"] for issue in closes]
        resolved = [number for number in numbers if number in items]
        if resolved:
            for number in resolved:
                entry = entry_for_item(number, items[number])
                closing.setdefault(entry.key, entry)
        elif commit_pulls:
            for pull in commit_pulls:
                number = pull["number"]
                if number not in items:
                    continue
                entry = entry_for_item(number, items[number])
                closing.setdefault(entry.key, entry)
        else:
            entry = entry_for_commit(commit, owner, name)
            closing.setdefault(entry.key, entry)
        for number in trailer_numbers(commit.message, REFERENCE_TRAILER):
            if number in items:
                entry = entry_for_item(number, items[number])
                referenced.setdefault(entry.key, entry)
    for key in closing:
        referenced.pop(key, None)
    return closing, referenced


def is_excluded(entry: Entry, config: dict) -> bool:
    """Report whether the config's exclude rules drop this entry."""
    exclude = (config.get("changelog") or {}).get("exclude") or {}
    labels = {label.casefold() for label in exclude.get("labels") or []}
    if labels & {label.casefold() for label in entry.labels}:
        return True
    authors = {
        author.casefold().removesuffix("[bot]")
        for author in exclude.get("authors") or []
    }
    if entry.author and entry.author.casefold().removesuffix("[bot]") in authors:
        return True
    return False


def categorize(entries: Iterable[Entry], config: dict) -> list[tuple[str, list[Entry]]]:
    """Group entries under the configured category titles, in config order."""
    categories = (config.get("changelog") or {}).get("categories") or []
    buckets: list[tuple[str, set[str], list[Entry]]] = [
        (
            category.get("title") or "Other Changes",
            {label.casefold() for label in category.get("labels") or []},
            [],
        )
        for category in categories
    ]
    fallback: list[Entry] = []
    for entry in entries:
        entry_labels = {label.casefold() for label in entry.labels}
        for _, labels, bucket in buckets:
            if entry_labels & labels or "*" in labels:
                bucket.append(entry)
                break
        else:
            fallback.append(entry)
    grouped = [(title, bucket) for title, _, bucket in buckets if bucket]
    if fallback:
        grouped.append(("Other Changes", fallback))
    return grouped


def format_bullet(entry: Entry, credit: bool) -> str:
    """Render one entry as a markdown list item."""
    link = f"[{entry.ref}]({entry.url})" if entry.url else entry.ref
    bullet = f"* {entry.title} ({link})"
    if credit and entry.author:
        bullet += f" by @{entry.author}"
    return bullet


def render(
    grouped: Sequence[tuple[str, list[Entry]]],
    referenced: Sequence[Entry],
    owner: str,
    name: str,
    start: str,
    end: str,
    credit: bool,
) -> str:
    """Assemble the full release-notes markdown document."""
    lines = ["## What's Changed", ""]
    if not grouped:
        lines += ["_No changes found in this range._", ""]
    for title, entries in grouped:
        lines.append(f"### {title}")
        lines.append("")
        lines += [format_bullet(entry, credit) for entry in entries]
        lines.append("")
    if referenced:
        lines.append("### Also touched")
        lines.append("")
        lines += [format_bullet(entry, credit) for entry in referenced]
        lines.append("")
    compare = f"https://github.com/{owner}/{name}/compare/{start}...{end}"
    lines.append(f"**Full Changelog**: {compare}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print issue-first release notes for the requested tag range."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from", dest="start", help="starting tag (default: previous tag)"
    )
    parser.add_argument("--to", dest="end", help="ending tag (default: newest tag)")
    parser.add_argument("--config", type=Path, help="path to a release.yml config")
    parser.add_argument(
        "--include-refs",
        action="store_true",
        help="add an 'Also touched' section for issues named by Refs trailers",
    )
    parser.add_argument(
        "--credit",
        action="store_true",
        help="append 'by @login' to each bullet",
    )
    parser.add_argument(
        "--exclude-commit-regex",
        help="also drop bare-commit bullets whose subject matches this pattern"
        + " (version-bump commits are always dropped)",
    )
    args = parser.parse_args(argv)

    owner, name = repository_slug()
    start, end = resolve_range(args.start, args.end)
    config = load_config(args.config)
    commits = read_commits(start, end)
    if not commits:
        raise SystemExit(f"no commits in {start}..{end}")

    shas = [commit.sha for commit in commits]
    pulls = fetch_commit_pulls(owner, name, shas)
    numbers: list[int] = []
    for commit in commits:
        numbers += trailer_numbers(commit.message, CLOSING_TRAILER)
        numbers += trailer_numbers(commit.message, REFERENCE_TRAILER)
        for pull in pulls.get(commit.sha, []):
            numbers.append(pull["number"])
            closes = (pull.get("closingIssuesReferences") or {}).get("nodes") or []
            numbers += [issue["number"] for issue in closes]
    items = fetch_items(owner, name, numbers) if numbers else {}

    closing, referenced = collect_entries(commits, pulls, items, owner, name)
    entries = [entry for entry in closing.values() if not is_excluded(entry, config)]
    patterns = [DEFAULT_COMMIT_EXCLUDE]
    if args.exclude_commit_regex:
        patterns.append(re.compile(args.exclude_commit_regex))
    entries = [
        entry
        for entry in entries
        if entry.key[0] != "commit"
        or not any(pattern.search(entry.title) for pattern in patterns)
    ]
    extra = (
        [entry for entry in referenced.values() if not is_excluded(entry, config)]
        if args.include_refs
        else []
    )
    grouped = categorize(entries, config)
    sys.stdout.write(render(grouped, extra, owner, name, start, end, args.credit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
