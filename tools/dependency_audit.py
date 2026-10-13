"""Opt-in online OSV scan of the public pinned offline dependency list; no environment secrets."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description="Opt-in OSV dependency scan (sends public package names/versions)")
    parser.add_argument("--allow-network", action="store_true", required=True)
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("Network opt-in required")
    root = Path(__file__).resolve().parents[1]
    packages = []
    for line in (root / "requirements-offline.txt").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^;\s]+)", line)
        if match:
            packages.append({"package": {"name": match[1], "ecosystem": "PyPI"}, "version": match[2]})
    request = Request("https://api.osv.dev/v1/querybatch", data=json.dumps({"queries": packages}).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if len(result.get("results", [])) != len(packages) or any(r.get("next_page_token") for r in result["results"]):
        raise RuntimeError("Incomplete vulnerability scan; do not report a clean result")
    findings = [{"package": p["package"]["name"], "version": p["version"], "vulnerabilities": r.get("vulns", [])} for p, r in zip(packages, result["results"]) if r.get("vulns")]
    print(json.dumps({"checked_at_utc": datetime.now(timezone.utc).isoformat(), "source": "https://api.osv.dev/v1/querybatch", "packages_checked": len(packages), "findings": findings, "result": "findings" if findings else "no_known_findings"}, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
