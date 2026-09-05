#!/usr/bin/env python3
"""Click-to-run Foxhole vanilla + complete map-mod builder."""

from __future__ import annotations

import ast
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

try:
    from PIL import Image  # noqa: F401
except ImportError as exc:
    raise SystemExit(
        "Pillow is required. Install dependencies with:\n"
        "    py -3 -m pip install -r requirements.txt"
    ) from exc

from foxhole_map_builder import settings
from foxhole_map_builder.layout import LayoutError, parse_bpmaplist_uasset
from foxhole_map_builder.pak import PakError, TextureError, extract_entry, find_entry, read_pak_footer, read_pak_index
from foxhole_map_builder.pipeline import BuildError, IncompleteMapMod, build_from_pak, inspect_pak_completeness


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "settings.txt"
OUTPUT_ROOT = SCRIPT_DIR / "output"
MAIN_PAK_FILENAME = "War-WindowsNoEditor.pak"
ALLOWED_SETTINGS = {"path_to_main_pak", "list_paths_to_mod_paks"}


class ConfigError(RuntimeError):
    pass


def load_config(path: Path) -> dict:
    defaults = {
        "path_to_main_pak": "",
        "list_paths_to_mod_paks": [],
    }
    if not path.is_file():
        raise ConfigError(f"settings file not found: {path}")

    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path), mode="exec")
    except SyntaxError as exc:
        raise ConfigError(f"settings.txt syntax error: {exc}") from exc

    values = dict(defaults)
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise ConfigError("Only simple NAME = value assignments are allowed")
            name = stmt.targets[0].id
            value_node = stmt.value
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        else:
            raise ConfigError("settings.txt may contain only comments and simple constant assignments")

        if name not in ALLOWED_SETTINGS:
            raise ConfigError(
                f"Unknown setting {name!r}; allowed settings are: {', '.join(sorted(ALLOWED_SETTINGS))}"
            )
        try:
            values[name] = ast.literal_eval(value_node)
        except Exception as exc:
            raise ConfigError(
                f"{name} must be a literal string/list. Use raw Windows strings, e.g. r\"D:\\Foxhole\\file.pak\""
            ) from exc

    main = values["path_to_main_pak"]
    if main is None:
        main = ""
    if not isinstance(main, str):
        raise ConfigError("path_to_main_pak must be a string")
    values["path_to_main_pak"] = main.strip()

    mods = values["list_paths_to_mod_paks"]
    if mods is None:
        mods = []
    if not isinstance(mods, (list, tuple)):
        raise ConfigError("list_paths_to_mod_paks must be a list of strings")
    clean_mods = []
    for item in mods:
        if not isinstance(item, str):
            raise ConfigError("Every list_paths_to_mod_paks item must be a string")
        if item.strip():
            clean_mods.append(item.strip())
    values["list_paths_to_mod_paks"] = clean_mods
    return values


def resolve_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = SCRIPT_DIR / p
    return p.resolve()


def resolve_main_pak(config: Mapping[str, object]) -> Tuple[Path, str]:
    raw = str(config.get("path_to_main_pak", "") or "").strip()
    if raw:
        return resolve_path(raw), "settings.txt:path_to_main_pak"

    for p in SCRIPT_DIR.iterdir():
        if p.is_file() and p.name.lower() == MAIN_PAK_FILENAME.lower():
            return p.resolve(), "same-directory automatic lookup"

    raise ConfigError(
        f"path_to_main_pak is empty and {MAIN_PAK_FILENAME} was not found beside the program"
    )


def resolve_mod_paks(config: Mapping[str, object], main_pak: Path) -> Tuple[List[Path], str]:
    configured = list(config.get("list_paths_to_mod_paks", []) or [])
    if configured:
        candidates = [resolve_path(x) for x in configured]
        mode = "settings.txt:list_paths_to_mod_paks"
    else:
        candidates = sorted(
            [
                p.resolve()
                for p in SCRIPT_DIR.iterdir()
                if p.is_file() and p.suffix.lower() == ".pak"
            ],
            key=lambda x: x.name.lower(),
        )
        mode = "same-directory automatic *.pak scan"

    main_resolved = str(main_pak.resolve()).lower()
    result: List[Path] = []
    seen = set()
    for p in candidates:
        # Explicit requirement: a same-directory file named exactly the main PAK
        # is never treated as a mod. Also exclude the resolved main path even if
        # it has a non-standard filename.
        if p.name.lower() == MAIN_PAK_FILENAME.lower():
            continue
        if str(p.resolve()).lower() == main_resolved:
            continue
        key = str(p.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(p)
    return result, mode


def load_layout_from_main_pak(main_pak: Path):
    with main_pak.open("rb") as fp:
        footer = read_pak_footer(fp)
        mount, entries = read_pak_index(fp, footer)
        bp_entry = find_entry(entries, settings.BPMAPLIST_PAK_PATH)
        bp_bytes = extract_entry(fp, footer, bp_entry)
    regions, metadata = parse_bpmaplist_uasset(bp_bytes)
    return regions, {
        "pak_version": footer.version,
        "mount_point": mount,
        "pak_entry_count": len(entries),
        "bpmaplist_entry": bp_entry.name,
        **metadata,
    }


def safe_output_name(path: Path) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", path.stem).strip(" .")
    return name or "mod"


def main() -> int:
    print("=" * 78)
    print("Foxhole Dynamic Vanilla + Complete Map Mod Builder")
    print("=" * 78)
    print(f"Program directory: {SCRIPT_DIR}")
    print(f"Settings:          {CONFIG_PATH}")
    print()

    try:
        config = load_config(CONFIG_PATH)
        main_pak, main_mode = resolve_main_pak(config)
        if not main_pak.is_file():
            raise ConfigError(f"Main PAK does not exist: {main_pak}")

        mod_paks, mod_mode = resolve_mod_paks(config, main_pak)

        print(f"Main PAK: {main_pak}")
        print(f"  resolved via: {main_mode}")
        print(f"Mod discovery: {mod_mode}")
        print(f"Mod candidates: {len(mod_paks)}")
        print()

        print("Reading current World Conquest layout from main BPMapList...")
        regions, layout_meta = load_layout_from_main_pak(main_pak)
        expected_count = len(regions)
        print(f"  current bIsInHexGrid regions: {expected_count}")
        print(f"  BPMapList: {layout_meta['bpmaplist_entry']}")
        print()

        if OUTPUT_ROOT.exists():
            shutil.rmtree(OUTPUT_ROOT)
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

        run_manifest = {
            "schema": 2,
            "main_pak": str(main_pak),
            "main_pak_resolution": main_mode,
            "layout": layout_meta,
            "current_region_count": expected_count,
            "base_output_size": list(settings.BASE_OUTPUT_SIZE),
            "requested_highres_output_size": list(settings.HIGHRES_OUTPUT_SIZE),
            "mod_discovery": mod_mode,
            "vanilla": {},
            "mods": [],
        }

        print("Building VANILLA from the main game PAK...")
        vanilla_out = OUTPUT_ROOT / "vanilla"
        vanilla_result = build_from_pak(
            main_pak,
            regions,
            vanilla_out,
            label="vanilla",
            require_complete=True,
            verbose=True,
        )
        run_manifest["vanilla"] = {
            "status": "built",
            "output": str(vanilla_out),
            "native_hex_size": list(vanilla_result.native_hex_size),
            "native_stitched_size": list(vanilla_result.native_stitched_size),
            "base_size": list(vanilla_result.base_size),
            "highres_size": list(vanilla_result.highres_size),
            "quadrant_sizes": {k: list(v) for k, v in vanilla_result.quadrant_sizes.items()},
            "individual_count": vanilla_result.individual_count,
        }
        print()

        used_names = set()
        for mod_path in mod_paks:
            record = {"path": str(mod_path), "status": "skipped", "reason": ""}

            if not mod_path.is_file():
                record["reason"] = "file does not exist"
                run_manifest["mods"].append(record)
                print(f"SKIP {mod_path}: file does not exist")
                continue

            try:
                check = inspect_pak_completeness(mod_path, regions)
                record["inspection"] = check

                if not check["complete"]:
                    record["reason"] = (
                        f"incomplete map mod: {len(check['missing'])}/{check['expected_count']} current region image(s) missing"
                    )
                    record["missing_regions"] = check["missing"]
                    run_manifest["mods"].append(record)
                    print(
                        f"SKIP {mod_path.name}: incomplete ({check['matching_count']}/{check['expected_count']} regions)"
                    )
                    continue

                folder = safe_output_name(mod_path)
                base = folder
                n = 2
                while folder.lower() in used_names:
                    folder = f"{base}_{n}"
                    n += 1
                used_names.add(folder.lower())

                print()
                print(
                    f"Building MOD {mod_path.name} ({check['matching_count']}/{check['expected_count']} current regions)..."
                )
                mod_out = OUTPUT_ROOT / "mods" / folder
                result = build_from_pak(
                    mod_path,
                    regions,
                    mod_out,
                    label=mod_path.stem,
                    require_complete=True,
                    verbose=True,
                )

                record.update(
                    {
                        "status": "built",
                        "reason": "",
                        "output": str(mod_out),
                        "native_hex_size": list(result.native_hex_size),
                        "native_stitched_size": list(result.native_stitched_size),
                        "base_size": list(result.base_size),
                        "highres_size": list(result.highres_size),
                        "quadrant_sizes": {k: list(v) for k, v in result.quadrant_sizes.items()},
                        "individual_count": result.individual_count,
                    }
                )
                run_manifest["mods"].append(record)

            except (PakError, TextureError, BuildError, OSError, ValueError) as exc:
                record["reason"] = f"{type(exc).__name__}: {exc}"
                run_manifest["mods"].append(record)
                print(f"SKIP {mod_path.name}: {exc}")

        manifest_path = OUTPUT_ROOT / "run_manifest.json"
        manifest_path.write_text(json.dumps(run_manifest, indent=2) + "\n", encoding="utf-8")

        built_mods = [m for m in run_manifest["mods"] if m["status"] == "built"]
        skipped_mods = [m for m in run_manifest["mods"] if m["status"] != "built"]

        report = [
            "FOXHOLE MAP BUILD REPORT",
            "=" * 80,
            f"Main PAK: {main_pak}",
            f"Current regions from BPMapList: {expected_count}",
            "",
            "Vanilla: BUILT",
            f"  output: {vanilla_out}",
            f"  base: {vanilla_result.base_size[0]}x{vanilla_result.base_size[1]}",
            f"  high-res: {vanilla_result.highres_size[0]}x{vanilla_result.highres_size[1]}",
            f"  native individual hexes: {vanilla_result.individual_count}",
            "",
            f"Mod candidates: {len(mod_paks)}",
            f"Built complete mods: {len(built_mods)}",
            f"Skipped mods: {len(skipped_mods)}",
            "",
            "MOD RESULTS",
            "-" * 80,
        ]
        for rec in run_manifest["mods"]:
            if rec["status"] == "built":
                report.append(f"BUILT   | {rec['path']}")
            else:
                report.append(f"SKIPPED | {rec['path']} | {rec['reason']}")

        (OUTPUT_ROOT / "run_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

        print()
        print("=" * 78)
        print("BUILD COMPLETE")
        print("=" * 78)
        print(f"Vanilla built:       1")
        print(f"Complete mods built: {len(built_mods)}")
        print(f"Mods skipped:        {len(skipped_mods)}")
        print(f"Output:              {OUTPUT_ROOT}")
        return 0

    except (ConfigError, LayoutError, PakError, TextureError, BuildError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
