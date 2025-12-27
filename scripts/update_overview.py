import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
DOCKERHUB_DESC_PATH = ROOT / "dockerhub-description.md"


def _load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _summarize_trivy(data: dict) -> tuple[Counter, int]:
    counts = Counter()
    for result in data.get("Results", []) or []:
        for vuln in result.get("Vulnerabilities", []) or []:
            severity = vuln.get("Severity", "UNKNOWN")
            counts[severity] += 1
    total = sum(counts.values())
    return counts, total


def _summarize_dockle(data) -> Counter:
    counts = Counter()
    if isinstance(data, dict):
        summary = data.get("Summary") or data.get("summary") or {}
        for key, value in summary.items():
            try:
                counts[str(key).upper()] += int(value)
            except (TypeError, ValueError):
                continue
        details = data.get("Details") or data.get("details") or []
        if details:
            for item in details:
                level = item.get("Level") or item.get("level")
                if level:
                    counts[str(level).upper()] += 1
        return counts
    if isinstance(data, list):
        for item in data:
            level = item.get("Level") or item.get("level")
            if level:
                counts[str(level).upper()] += 1
    return counts


def _format_trivy(counts: Counter, total: int) -> str:
    if total == 0:
        return "Trivy: 0 vulnerabilities detected."
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    parts = [f"{sev}={counts.get(sev, 0)}" for sev in order if counts.get(sev, 0) > 0]
    return f"Trivy: {total} vulnerabilities ({', '.join(parts)})."


def _format_dockle(counts: Counter) -> str:
    if not counts:
        return "Dockle: no findings reported."
    order = ["FATAL", "WARN", "INFO", "SKIP", "PASS"]
    parts = [f"{sev}={counts.get(sev, 0)}" for sev in order if counts.get(sev, 0) > 0]
    return f"Dockle: {', '.join(parts)}."


def _render_overview(trivy_summary: str, dockle_summary: str) -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "Docker image: hardened minimal runtime (non-root by default) with an HTTP healthcheck on "
        "`/metrics`. Published to Docker Hub: https://hub.docker.com/r/merlijntishauser/pihole-sqlite-exporter",
        "GitHub repo: https://github.com/merlijntishauser/pihole-sqlite-exporter",
        f"Scan summary ({ts}): {dockle_summary} {trivy_summary}",
    ]
    return "\n".join(lines)


def _replace_between_markers(text: str, start: str, end: str, new_content: str) -> str:
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise ValueError("Markers not found or invalid")
    before = text[: start_idx + len(start)]
    after = text[end_idx:]
    return f"{before}\n{new_content}\n{after}"


def main() -> None:
    trivy_data = _load_json(ROOT / "trivy.json")
    dockle_data = _load_json(ROOT / "dockle.json")

    trivy_counts, trivy_total = _summarize_trivy(trivy_data if isinstance(trivy_data, dict) else {})
    dockle_counts = _summarize_dockle(dockle_data)

    trivy_summary = _format_trivy(trivy_counts, trivy_total)
    dockle_summary = _format_dockle(dockle_counts)
    overview = _render_overview(trivy_summary, dockle_summary)

    readme = README_PATH.read_text()
    updated = _replace_between_markers(
        readme,
        "<!-- overview:start -->",
        "<!-- overview:end -->",
        overview,
    )
    README_PATH.write_text(updated)

    DOCKERHUB_DESC_PATH.write_text(overview + "\n")


if __name__ == "__main__":
    main()
