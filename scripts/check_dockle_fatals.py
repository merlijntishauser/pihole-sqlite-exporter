import json
import sys
from pathlib import Path


def _load_dockle_json(path: Path) -> object:
    if not path.exists():
        print(f"{path} not found.")
        raise SystemExit(1)
    return json.loads(path.read_text())


def _collect_fatals(data: object) -> tuple[int, list[dict]]:
    fatal = 0
    fatal_details: list[dict] = []

    if isinstance(data, dict):
        summary = data.get("Summary") or data.get("summary") or {}
        if summary:
            value = summary.get("FATAL", summary.get("fatal", 0))
            try:
                fatal = int(value or 0)
            except (TypeError, ValueError):
                fatal = 0
        else:
            details = data.get("Details") or data.get("details") or []
            for item in details:
                level = item.get("Level") or item.get("level")
                if str(level).upper() == "FATAL":
                    fatal += 1
                    fatal_details.append(item)
    elif isinstance(data, list):
        for item in data:
            level = item.get("Level") or item.get("level")
            if str(level).upper() == "FATAL":
                fatal += 1
                fatal_details.append(item)

    return fatal, fatal_details


def _print_fatal_details(data: object, fatal_details: list[dict]) -> None:
    if not fatal_details and isinstance(data, dict):
        fatal_details = data.get("Details") or data.get("details") or []
    for item in fatal_details:
        level = str(item.get("Level") or item.get("level") or "").upper()
        if level and level != "FATAL":
            continue
        code = item.get("Code") or item.get("code") or "UNKNOWN"
        title = item.get("Title") or item.get("title") or ""
        desc = item.get("Description") or item.get("description") or ""
        print(f"- {code}: {title}".rstrip())
        if desc:
            print(f"  {desc}")
        for key in (
            "Message",
            "Detail",
            "Details",
            "File",
            "FilePath",
            "Filename",
            "Path",
            "Reference",
            "Resource",
            "Target",
            "Cmd",
            "Instruction",
        ):
            value = item.get(key) or item.get(key.lower())
            if value:
                print(f"  {key}: {value}")
        extra = {
            key: value
            for key, value in item.items()
            if key
            not in {
                "Level",
                "level",
                "Code",
                "code",
                "Title",
                "title",
                "Description",
                "description",
                "Message",
                "message",
                "Detail",
                "detail",
                "Details",
                "details",
                "File",
                "file",
                "FilePath",
                "filepath",
                "Filename",
                "filename",
                "Path",
                "path",
                "Reference",
                "reference",
                "Resource",
                "resource",
                "Target",
                "target",
                "Cmd",
                "cmd",
                "Instruction",
                "instruction",
            }
        }
        if extra:
            print(f"  Extra: {extra}")


def main() -> None:
    path = Path("dockle.json")
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])

    data = _load_dockle_json(path)
    fatal, fatal_details = _collect_fatals(data)

    if fatal:
        print(f"Dockle fatal findings: {fatal}")
        _print_fatal_details(data, fatal_details)
        raise SystemExit(1)

    print("Dockle fatal findings: 0")


if __name__ == "__main__":
    main()
