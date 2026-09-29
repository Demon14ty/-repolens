"""Check RepoLens's deterministic analysis against evaluation/questions.json.

Measures the automatic parts (framework, entry point, whether expected source
files appear in the learning path or flow, response time). Reading-path
usefulness and quest quality need a human - see evaluation/README.md.

Run from the project root:  python -m evaluation.run_eval
Needs network access (it calls the GitHub API).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from dotenv import load_dotenv

from services.github_service import GitHubClient, GitHubError, fetch_snapshot, github_token
from services.repo_analyzer import analyze_snapshot, choose_files_to_download
from utils.github_parser import parse_github_url

QUESTIONS_FILE = Path(__file__).with_name("questions.json")


def evaluate_repository(case: dict, client: GitHubClient) -> dict:
    owner, repo = parse_github_url(case["repository"])
    started = time.perf_counter()
    analysis = analyze_snapshot(fetch_snapshot(owner, repo, client, choose_files_to_download))
    seconds = time.perf_counter() - started

    surfaced = {s.path for s in analysis.learning_path} | {f.path for f in analysis.flow if f.path}
    sources = [src for q in case["questions"] for src in q["expected_sources"]]
    return {
        "repository": f"{owner}/{repo}",
        "framework_ok": analysis.framework.name == case["expected_framework"],
        "framework": analysis.framework.name,
        "entry_point_ok": bool(analysis.entry_points) and analysis.entry_points[0] == case["expected_entry_point"],
        "entry_point": analysis.entry_points[0] if analysis.entry_points else None,
        "sources_surfaced": sum(src in surfaced for src in sources),
        "sources_total": len(sources),
        "has_quest": analysis.quest is not None,
        "seconds": round(seconds, 1),
    }


def main() -> None:
    load_dotenv()
    client = GitHubClient(token=github_token())
    cases = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        try:
            results.append(evaluate_repository(case, client))
        except GitHubError as exc:
            print(f"{case['repository']}: skipped ({exc})")

    print(f"{'repository':42} {'framework':9} {'entry':6} {'sources':8} {'quest':6} time")
    for r in results:
        print(f"{r['repository']:42} {'ok' if r['framework_ok'] else 'MISS':9} {'ok' if r['entry_point_ok'] else 'MISS':6} "
              f"{r['sources_surfaced']}/{r['sources_total']:<6} {'yes' if r['has_quest'] else 'no':6} {r['seconds']}s")
    if results:
        n = len(results)
        print(f"\nFramework accuracy: {sum(r['framework_ok'] for r in results)}/{n}")
        print(f"Entry-point accuracy: {sum(r['entry_point_ok'] for r in results)}/{n}")
        print(f"Expected sources surfaced: {sum(r['sources_surfaced'] for r in results)}/"
              f"{sum(r['sources_total'] for r in results)}")


if __name__ == "__main__":
    main()
