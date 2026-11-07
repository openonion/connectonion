"""Local, interactive, read-only Jira acceptance. Never stores credentials/data.

Credentials are entered in the operator's terminal, not passed as arguments.
Only aggregate acceptance results survive; imported source files are temporary.
"""

import argparse
import getpass
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def source_titles_match(records: list[dict], issues: list[dict]) -> bool:
    # Envelope id is namespaced. Jira's issue key is external_id, not id.
    expected = {item["key"]: str(item["fields"].get("summary") or "") for item in issues}
    actual = {record["external_id"]: record["title"] for record in records}
    return len(records) == len(expected) and actual == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--issues", nargs="+", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = {"scope": "remote read-only; isolated temporary source/state directories",
              "status": "incomplete", "checks": []}
    environment = dict(os.environ)
    try:
        print("Jira 本机只读验证：不会修改远端 issue，也不会保存 API token 或来源正文。")
        print("需要 Jira 网站地址、账号邮箱和 API token（不是账号密码）。Ctrl+C 可以取消。")
        for key, label in (("JIRA_URL", "Jira 网站地址 https://...atlassian.net"), ("JIRA_EMAIL", "Jira 账号邮箱")):
            if not environment.get(key):
                environment[key] = input(label + ": ").strip()
        if not environment.get("JIRA_API_TOKEN"):
            environment["JIRA_API_TOKEN"] = getpass.getpass("Jira API token（输入不显示）: ")
        co = str(Path(sys.executable).with_name("co"))

        def run(label, words):
            result = subprocess.run([co, "jira", *words, "--json"], env=environment,
                                    capture_output=True, text=True, timeout=180)
            try:
                payload = json.loads(result.stdout)
            except ValueError:
                raise RuntimeError(f"{label}: command did not return parseable JSON") from None
            if result.returncode:
                raise RuntimeError(f"{label}: exit {result.returncode}, error_code={payload.get('error_code', 'unknown')}")
            report["checks"].append({"check": label, "passed": True})
            print(label + ": PASS", flush=True)
            return payload

        run("verify", ["verify"])
        projects = run("projects", ["projects"])
        if args.project not in {item["key"] for item in projects["projects"]}:
            raise RuntimeError("Selected test project is not accessible; no import was attempted.")
        original = run("selected issue read", ["issues", args.project, *args.issues])
        with tempfile.TemporaryDirectory(prefix="jira-live-readonly-") as directory:
            root = Path(directory)
            command = ["sync-inc", "--project", args.project, "--output", str(root / "source"),
                       "--state", str(root / "state"), "--no-history"]
            for key in args.issues:
                command.extend(["--issues", key])
            first = run("first incremental import", command)
            records = [json.loads(line) for path in (root / "source").glob("daily/*/*/*.jsonl")
                       for line in path.read_text().splitlines()]
            if not source_titles_match(records, original["issues"]):
                raise RuntimeError("Imported identity/title comparison did not match the selected source read.")
            report["checks"].append({"check": "source identity/title comparison", "passed": True})
            repeat = run("repeat incremental import", command)
            if repeat["net_new_records"] != 0:
                raise RuntimeError("Repeat added versions; source may have changed concurrently, inspect before accepting.")
            checkpoints = {path: path.read_bytes() for path in (root / "state").glob("checkpoints/*.json")}
            run("full repair read", [*command, "--full"])
            if any(path.read_bytes() != before for path, before in checkpoints.items()):
                raise RuntimeError("Full read changed an incremental checkpoint.")
            run("separate selected snapshot", ["sync", args.project, *args.issues,
                                               "--output", str(root / "selected"), "--no-history"])
            report["first_mapped"] = first["issues_mapped"]
            report["repeat_new_versions"] = repeat["net_new_records"]
        report["status"] = "passed"
        report["limitations"] = ["No remote mutations; changed-source behavior uses offline fixtures.",
                                  "History, REM processing and Reader updates are separate checks."]
    except (KeyboardInterrupt, EOFError):
        report["reason"] = "Local credential entry cancelled or unavailable."
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        report["reason"] = str(error) if isinstance(error, RuntimeError) else "CLI command timed out."
    finally:
        environment.pop("JIRA_API_TOKEN", None)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("验证结果: " + report["status"])
        print("仅保存统计结果: " + str(args.report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
