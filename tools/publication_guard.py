from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def check_pinned_requirements(path: Path, failures: list[str], *, allow_include: bool = False) -> None:
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if allow_include and line.startswith("-r "):
            continue
        if "==" not in line:
            fail(f"{path.name}:{line_number}: dependency is not directly version-pinned: {line}", failures)


def tracked_paths(failures: list[str]) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail("unable to enumerate tracked publication files with git ls-files", failures)
        return []
    return [
        ROOT / entry.decode("utf-8", errors="surrogateescape")
        for entry in result.stdout.split(b"\0")
        if entry
    ]


def main() -> int:
    failures: list[str] = []
    tracked = tracked_paths(failures)

    required = [
        ROOT / "README.md",
        ROOT / "LICENSE",
        ROOT / "SECURITY.md",
        ROOT / "PUBLICATION.md",
        ROOT / ".env.example",
        ROOT / ".python-version",
        ROOT / "requirements.txt",
        ROOT / "requirements-dev.txt",
        ROOT / "Procfile",
        ROOT / "templates" / "index.html",
        ROOT / "static" / "app.js",
    ]
    for path in required:
        if not path.is_file():
            fail(f"missing required publication file: {path.relative_to(ROOT)}", failures)

    if failures:
        for item in failures:
            print(item)
        return 1

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not readme.startswith("# Signal Forge"):
        fail("README must present the project as Signal Forge", failures)
    for phrase in (
        "legally permitted",
        "one worker",
        "pytest",
        "not affiliated",
    ):
        if phrase.casefold() not in readme.casefold():
            fail(f"README is missing publication boundary/verification phrase: {phrase}", failures)
    if "# Signal Forge / SpotifyDownAutomater" in readme:
        fail("README title still exposes the legacy repository name", failures)

    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    if "Signal Forge" not in template:
        fail("public UI is missing Signal Forge branding", failures)

    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    secret_match = re.search(r"(?m)^SECRET_KEY=(.*)$", env_text)
    if secret_match is None:
        fail(".env.example must include SECRET_KEY=", failures)
    elif secret_match.group(1).strip():
        fail(".env.example must not contain a usable SECRET_KEY", failures)

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for ignored in (".env", "*.zip", "_tmp_mine/", ".cursor/hooks/state/"):
        if ignored not in gitignore:
            fail(f".gitignore is missing {ignored}", failures)

    check_pinned_requirements(ROOT / "requirements.txt", failures)
    check_pinned_requirements(ROOT / "requirements-dev.txt", failures, allow_include=True)

    forbidden_artifact_suffixes = {".mp3", ".m4a", ".wav", ".flac", ".zip"}
    forbidden_internal_prefixes = ("_tmp_mine/", ".cursor/hooks/state/")
    windows_user_root = r"[A-Za-z]:[\\/]" + "Users" + r"[\\/]"
    mac_user_root = "/" + "Users" + "/"
    unix_home_root = "/" + "home" + "/"
    absolute_workstation_path = re.compile(
        f"(?:{windows_user_root}|{re.escape(mac_user_root)}|{re.escape(unix_home_root)})",
        re.IGNORECASE,
    )
    for path in tracked:
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            continue
        if relative.startswith(forbidden_internal_prefixes):
            fail(f"internal state/transcript file must not be published: {relative}", failures)
        if path.suffix.casefold() in forbidden_artifact_suffixes:
            fail(f"generated/media artifact must not be published: {relative}", failures)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if absolute_workstation_path.search(text):
            fail(f"tracked text contains an absolute workstation path: {relative}", failures)

    if failures:
        print("publication guard failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("publication guard ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
