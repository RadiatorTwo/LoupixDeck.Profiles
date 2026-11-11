#!/usr/bin/env python3
"""Validate every submission under profiles/ and build index.json from them.

Layout of one submission:

    profiles/<author>/<id>/
        profile.json            required, see profile.schema.json
        <id>.loupixprofile      required, exported from LoupixDeck
        preview.png             required (preview.jpg also accepted)
        screenshots/*.png       optional, at most MAX_SCREENSHOTS
        README.md               optional

Usage:
    python scripts/build_index.py              validate and write index.json
    python scripts/build_index.py --validate   validate only, write nothing

Only the standard library is used, so the script runs on a bare GitHub runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles"
INDEX_FILE = ROOT / "index.json"

DEFAULT_BASE_URL = "https://raw.githubusercontent.com/RadiatorTwo/LoupixDeck.Profiles/master/"
BASE_URL = os.environ.get("PROFILES_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/"

INDEX_SCHEMA_VERSION = 1
# Highest ProfilePackageManifest.CurrentFormatVersion the store accepts.
MAX_FORMAT_VERSION = 1

MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_SCREENSHOTS = 6

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AUTHOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
TAG_RE = ID_RE
PLATFORMS = {"Windows", "Linux", "macOS"}
KINDS = {"Profile", "Workspace", "TouchPage", "RotaryPage"}
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
ALLOWED_FOLDER_FILES = {"profile.json", "README.md", "preview.png", "preview.jpg"}
PROFILE_KEYS = {"$schema", "id", "name", "description", "author", "version", "license", "tags", "platforms"}


class Errors:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, where: Path | str, message: str) -> None:
        if isinstance(where, Path):
            where = where.relative_to(ROOT).as_posix()
        self.items.append(f"{where}: {message}")


def url_for(path: Path) -> str:
    return BASE_URL + path.relative_to(ROOT).as_posix()


def ci_get(data: dict, key: str, default=None):
    """Case-insensitive lookup: the app writes the manifest in PascalCase."""
    lowered = key.lower()
    for k, v in data.items():
        if k.lower() == lowered:
            return v
    return default


def is_image(path: Path) -> bool:
    head = path.read_bytes()[:8]
    return head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")


def last_commit_time(folder: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(folder)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out or None
    except (OSError, subprocess.CalledProcessError):
        return None


def check_profile_json(path: Path, author: str, profile_id: str, errors: Errors) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        errors.add(path, f"not valid JSON ({ex})")
        return None
    if not isinstance(data, dict):
        errors.add(path, "must be a JSON object")
        return None

    before = len(errors.items)
    for key in sorted(set(data) - PROFILE_KEYS):
        errors.add(path, f"unknown field '{key}'")
    for key in ("id", "name", "description", "author", "version"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            errors.add(path, f"'{key}' is required and must be a non-empty string")
    if len(errors.items) > before:
        return None

    if data["id"] != profile_id:
        errors.add(path, f"id '{data['id']}' must equal the folder name '{profile_id}'")
    if not ID_RE.match(data["id"]) or len(data["id"]) > 64:
        errors.add(path, "id must be lower-case letters, digits and dashes (max 64)")
    if data["author"] != author:
        errors.add(path, f"author '{data['author']}' must equal the parent folder name '{author}'")
    if not AUTHOR_RE.match(data["author"]):
        errors.add(path, "author must be a GitHub user name")
    if not VERSION_RE.match(data["version"]):
        errors.add(path, "version must be major.minor.patch")
    if len(data["name"]) > 60:
        errors.add(path, "name is longer than 60 characters")
    if len(data["description"]) > 500:
        errors.add(path, "description is longer than 500 characters")

    tags = data.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 10 or len(set(tags)) != len(tags) \
            or not all(isinstance(t, str) and TAG_RE.match(t) for t in tags):
        errors.add(path, "tags must be at most 10 distinct lower-case words")
    platforms = data.get("platforms", [])
    if not isinstance(platforms, list) or len(set(platforms)) != len(platforms) \
            or not all(p in PLATFORMS for p in platforms):
        errors.add(path, f"platforms may only contain {sorted(PLATFORMS)}")
    if "license" in data and (not isinstance(data["license"], str) or not data["license"].strip()):
        errors.add(path, "license must be an SPDX identifier")
    return data


def check_package(path: Path, errors: Errors) -> dict | None:
    """Validate the zip and return its manifest."""
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        errors.add(path, f"package is larger than {MAX_PACKAGE_BYTES // (1024 * 1024)} MB")
        return None
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        errors.add(path, "not a valid .loupixprofile (zip) file")
        return None

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            errors.add(path, f"package has more than {MAX_ENTRIES} entries")
            return None
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            errors.add(path, "package unpacks to more than 100 MB")
            return None

        names = {i.filename for i in infos if not i.is_dir()}
        for name in names:
            normalized = posixpath.normpath(name)
            if "\\" in name or name.startswith("/") or normalized.startswith("..") or ":" in name:
                errors.add(path, f"unsafe entry name '{name}'")
                return None

        if "manifest.json" not in names:
            errors.add(path, "package has no manifest.json")
            return None
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
        except ValueError as ex:
            errors.add(path, f"manifest.json is not valid JSON ({ex})")
            return None
        if not isinstance(manifest, dict):
            errors.add(path, "manifest.json must be a JSON object")
            return None

        format_version = ci_get(manifest, "FormatVersion")
        if not isinstance(format_version, int) or format_version < 1:
            errors.add(path, "manifest FormatVersion is missing or invalid")
        elif format_version > MAX_FORMAT_VERSION:
            errors.add(path, f"manifest FormatVersion {format_version} is newer than the store supports "
                             f"({MAX_FORMAT_VERSION})")
        if ci_get(manifest, "Kind") not in KINDS:
            errors.add(path, f"manifest Kind must be one of {sorted(KINDS)}")
        slug = ci_get(manifest, "SourceDeviceSlug")
        if not isinstance(slug, str) or not ID_RE.match(slug):
            errors.add(path, "manifest SourceDeviceSlug is missing or invalid")

        payload_file = ci_get(manifest, "PayloadFile") or "payload.json"
        if not isinstance(payload_file, str) or "/" in payload_file or not payload_file.endswith(".json"):
            errors.add(path, f"manifest PayloadFile '{payload_file}' is invalid")
            return None
        if payload_file not in names:
            errors.add(path, f"package has no {payload_file}")
            return None

        allowed = {"manifest.json", payload_file, "macros.json"}
        for name in sorted(names - allowed):
            if not (name.startswith("assets/") and posixpath.splitext(name)[1].lower() in ASSET_EXTENSIONS):
                errors.add(path, f"unexpected entry '{name}' (only manifest, payload, macros.json "
                                 f"and images under assets/ are allowed)")

        for json_name in (payload_file, "macros.json"):
            if json_name in names:
                try:
                    json.loads(archive.read(json_name).decode("utf-8-sig"))
                except ValueError as ex:
                    errors.add(path, f"{json_name} is not valid JSON ({ex})")
        return manifest


def check_image(path: Path, errors: Errors) -> None:
    if path.stat().st_size > MAX_IMAGE_BYTES:
        errors.add(path, "image is larger than 2 MB")
    elif not is_image(path):
        errors.add(path, "not a PNG or JPEG image")


def build_entry(folder: Path, author: str, errors: Errors) -> dict | None:
    profile_id = folder.name
    before = len(errors.items)

    profile_path = folder / "profile.json"
    package_path = folder / f"{profile_id}.loupixprofile"
    previews = [folder / n for n in ("preview.png", "preview.jpg") if (folder / n).is_file()]
    screenshots_dir = folder / "screenshots"

    for entry in sorted(folder.iterdir()):
        if entry.is_dir():
            if entry.name != "screenshots":
                errors.add(entry, "unexpected folder (only screenshots/ is allowed)")
        elif entry.name not in ALLOWED_FOLDER_FILES and entry != package_path:
            errors.add(entry, f"unexpected file (the package must be named {package_path.name})")

    if not profile_path.is_file():
        errors.add(folder, "missing profile.json")
    if not package_path.is_file():
        errors.add(folder, f"missing {package_path.name}")
    if len(previews) != 1:
        errors.add(folder, "needs exactly one preview.png or preview.jpg")
    if len(errors.items) > before:
        return None

    profile = check_profile_json(profile_path, author, profile_id, errors)
    manifest = check_package(package_path, errors)
    check_image(previews[0], errors)

    screenshots: list[Path] = []
    if screenshots_dir.is_dir():
        screenshots = sorted(p for p in screenshots_dir.iterdir())
        if len(screenshots) > MAX_SCREENSHOTS:
            errors.add(screenshots_dir, f"at most {MAX_SCREENSHOTS} screenshots")
        for shot in screenshots:
            if shot.is_dir() or shot.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                errors.add(shot, "screenshots/ may only contain PNG or JPEG files")
            else:
                check_image(shot, errors)

    if len(errors.items) > before or profile is None or manifest is None:
        return None

    data = package_path.read_bytes()
    entry: dict = {
        "id": profile["id"],
        "name": profile["name"].strip(),
        "description": profile["description"].strip(),
        "author": profile["author"],
        "version": profile["version"],
    }
    updated = last_commit_time(folder)
    if updated:
        entry["updatedAt"] = updated
    entry["license"] = profile.get("license", "CC-BY-4.0")
    entry["tags"] = profile.get("tags", [])
    entry["platforms"] = profile.get("platforms", [])
    entry["kind"] = ci_get(manifest, "Kind")
    entry["device"] = {
        "slug": ci_get(manifest, "SourceDeviceSlug"),
        "name": ci_get(manifest, "SourceDeviceName") or "",
        "touchButtons": ci_get(manifest, "SourceTouchButtonCount") or 0,
        "rotaryButtons": ci_get(manifest, "SourceRotaryButtonCount") or 0,
        "hasSideStrips": bool(ci_get(manifest, "SourceHasSideStrips")),
    }
    companions = ci_get(manifest, "CompanionDevices")
    if companions:
        entry["companionDevices"] = companions
    entry["requiredPlugins"] = [
        {k: v for k, v in {
            "id": ci_get(p, "Id"),
            "name": ci_get(p, "Name"),
            "version": ci_get(p, "Version"),
            "projectUrl": ci_get(p, "ProjectUrl"),
        }.items() if v}
        for p in (ci_get(manifest, "RequiredPlugins") or []) if isinstance(p, dict) and ci_get(p, "Id")
    ]
    entry["commands"] = sorted(ci_get(manifest, "ReferencedCommands") or [])
    entry["macros"] = sorted(ci_get(manifest, "Macros") or [])
    entry["formatVersion"] = ci_get(manifest, "FormatVersion")
    entry["configSchemaVersion"] = ci_get(manifest, "ConfigSchemaVersion") or 0
    if ci_get(manifest, "AppVersion"):
        entry["appVersion"] = ci_get(manifest, "AppVersion")
    entry["preview"] = url_for(previews[0])
    if screenshots:
        entry["screenshots"] = [url_for(s) for s in screenshots]
    entry["package"] = {
        "fileName": package_path.name,
        "downloadUrl": url_for(package_path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--validate", action="store_true", help="validate only, do not write index.json")
    args = parser.parse_args()

    errors = Errors()
    entries: list[dict] = []
    seen: dict[str, Path] = {}

    if PROFILES_DIR.is_dir():
        for author_dir in sorted(p for p in PROFILES_DIR.iterdir()):
            if author_dir.name.startswith("."):
                continue
            if not author_dir.is_dir():
                errors.add(author_dir, "only author folders belong in profiles/")
                continue
            if not AUTHOR_RE.match(author_dir.name):
                errors.add(author_dir, "folder name must be a GitHub user name")
                continue
            for folder in sorted(p for p in author_dir.iterdir()):
                if not folder.is_dir():
                    errors.add(folder, "only profile folders belong in an author folder")
                    continue
                if not ID_RE.match(folder.name):
                    errors.add(folder, "folder name must be lower-case letters, digits and dashes")
                    continue
                if folder.name in seen:
                    errors.add(folder, f"id '{folder.name}' is already used by {seen[folder.name].relative_to(ROOT).as_posix()}")
                    continue
                seen[folder.name] = folder
                entry = build_entry(folder, author_dir.name, errors)
                if entry:
                    entries.append(entry)

    if errors.items:
        print(f"{len(errors.items)} problem(s) found:", file=sys.stderr)
        for item in errors.items:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(f"{len(entries)} profile(s) valid.")
    if args.validate:
        return 0

    entries.sort(key=lambda e: e["id"])
    index = {"schemaVersion": INDEX_SCHEMA_VERSION, "profiles": entries}
    INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {INDEX_FILE.relative_to(ROOT).as_posix()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
