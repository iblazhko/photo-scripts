#!/usr/bin/env python3

"""Remove temporary files and reduce disk usage

Assuming following library structure:
    Library/
        YYYY-MM-DD <Description>/
            0_RAW/     -- raw files from camera, renamed with rename-raw-photos.py
                yyyymmdd_hhmm_nnnn.jpg
                yyyymmdd_hhmm_nnnn.raw
            1_EDIT/    -- edits from Lightroom/Darktable exported as full-sized TIFFs
            2_EXPORT/  -- not used by this script
            yyyymmdd_hhmm_nnnn.raw
            yyyymmdd_hhmm_nnnn.raw -- raw files selected for edit; copied from 0_RAW

This script can perfom following cleanups:
* remove edits from `YYYY-MM-DD <Description>/1_EDIT` - these files can
  always be re-exported from editing application
* remove images from `YYYY-MM-DD <Description>/2_EXPORT` - can be useful
  if files have been copied already elsewhere, e.g. to an online gallery
* use hard links for RAW selects in `YYYY-MM-DD <Description>`
  (link them to corresponding files in `YYYY-MM-DD <Description>/0_RAW`)
  to save disk space.

Script requires following tools to be installed:

* Python, obviously (`brew install python`)

* * *

Copyright 2025 Ivan Blazhko

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to
do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
import argparse
import hashlib
import os
import shutil
from pathlib import Path

PROJECT_RAW_SUBDIR = "0_RAW"
PROJECT_EDIT_SUBDIR = "1_EDIT"
PROJECT_EXPORT_SUBDIR = "2_EXPORT"
INDENT = "    "
FILE_RW_MASK = 0o000666


class ApplicationError(Exception):
    pass


def get_dry_run_info(dry_run: bool):
    if dry_run:
        return "ℹ️"  # noqa: RUF001
    else:
        return ""


def find_projects(library_path: Path) -> list[Path]:
    result = []
    subdirs = [x for x in library_path.iterdir() if x.is_dir()]
    if any(
        x.name in {PROJECT_RAW_SUBDIR, PROJECT_EDIT_SUBDIR, PROJECT_EXPORT_SUBDIR}
        for x in subdirs
    ):
        result.extend([library_path])
    else:
        for x in subdirs:
            result.extend(find_projects(x))
    return result


def remove_dot_files(project_path: Path, dry_run: bool):
    dry_run_info = get_dry_run_info(dry_run)
    for f in project_path.rglob("._*"):
        print(f"{dry_run_info}{INDENT}❌ {f}")
        if not dry_run:
            f.unlink()


def remove_subdir_files(project_path: Path, subdir: str, dry_run: bool):
    dry_run_info = get_dry_run_info(dry_run)
    export_dir = project_path / subdir
    if export_dir.is_dir():
        for x in export_dir.iterdir():
            if x.is_file():
                print(f"{dry_run_info}{INDENT}❌ {x}")
                if not dry_run:
                    x.unlink()
            elif x.is_dir():
                print(f"{dry_run_info}{INDENT}❌ {x}/")
                if not dry_run:
                    shutil.rmtree(x)


def get_file_md5_hash(file_path: Path) -> str:
    return hashlib.md5(file_path.read_bytes()).hexdigest()


def are_hardlinks_supported(path: Path) -> bool:
    dummy_file = path / ".dummy.dat"
    dummy_link = path / ".dummy.dat.link"
    try:
        dummy_file.write_text("TEST", encoding="utf-8")
        os.link(dummy_file, dummy_link)
        hardlinks_supported = True
    except (
        OSError,
        PermissionError,
        RuntimeError,
    ):
        hardlinks_supported = False
    finally:
        if dummy_link.exists():
            dummy_link.unlink()
        if dummy_file.exists():
            dummy_file.unlink()
    return hardlinks_supported


def hardlink_select_files(project_path: Path, dry_run: bool):
    dry_run_info = get_dry_run_info(dry_run)
    raw_dir = project_path / PROJECT_RAW_SUBDIR
    if raw_dir.is_dir():
        select_files = [
            x
            for x in project_path.iterdir()
            if x.is_file()
            and not (x.name.startswith(".") or x.is_junction() or x.is_symlink())
        ]
        for x in select_files:
            file_name = x.name
            raw_candidate = raw_dir / file_name
            if raw_candidate.exists() and not x.samefile(raw_candidate):
                select_md5 = get_file_md5_hash(x)
                raw_md5 = get_file_md5_hash(raw_candidate)
                if select_md5 == raw_md5:
                    print(
                        f"{dry_run_info}{INDENT}🔗 {x}"
                        f" <- {PROJECT_RAW_SUBDIR}/{file_name}"
                    )
                    if not dry_run:
                        x.unlink()
                        os.link(raw_candidate, x)
                else:
                    print(
                        f"{dry_run_info}{INDENT}⚠️ {x} content"
                        f" (MD5:{select_md5}) is different from"
                        f" {PROJECT_RAW_SUBDIR}/{x.name} (MD5:{raw_md5})"
                    )


def set_file_mode(path: Path, mode: int, display_path: str, dry_run: bool):
    dry_run_info = get_dry_run_info(dry_run)
    print(f"{dry_run_info}{INDENT}✔️ {oct(mode)} {display_path}")
    if not dry_run:
        path.chmod(mode)


def set_file_readonly(path: Path, display_path: str, dry_run: bool):
    mode = path.stat().st_mode
    if mode & 0o000333:
        new_mode = mode & 0o777444
        set_file_mode(path, new_mode, display_path, dry_run)


def set_file_readwrite(path: Path, display_path: str, dry_run: bool):
    mode = path.stat().st_mode
    if (mode & 0o000111) or ((mode & FILE_RW_MASK) != FILE_RW_MASK):
        new_mode = (mode & 0o777666) | FILE_RW_MASK
        set_file_mode(path, new_mode, display_path, dry_run)


def set_files_permissions(project_path: Path, hardlink_selects: bool, dry_run: bool):
    raw_path_set: set[Path] = set()

    raw_dir = project_path / PROJECT_RAW_SUBDIR
    if raw_dir.exists():
        for x in raw_dir.iterdir():
            if x.is_file():
                set_file_readonly(x, f"{PROJECT_RAW_SUBDIR}/{x.name}", dry_run)
                raw_path_set.add(x)

    for x in project_path.iterdir():
        if x.is_file():
            if hardlink_selects and (x in raw_path_set):
                continue
            if x.suffix.lower() == ".xmp":
                set_file_readwrite(x, x.name, dry_run)
            else:
                set_file_readonly(x, x.name, dry_run)


def cleanup_project(
    project_path: Path,
    remove_dotfiles: bool,
    remove_edits: bool,
    remove_exports: bool,
    hardlink_selects: bool,
    fix_permissions: bool,
    dry_run: bool,
):
    print(f"{project_path}:")
    if remove_dotfiles:
        remove_dot_files(project_path, dry_run)
    if remove_edits:
        remove_subdir_files(project_path, PROJECT_EDIT_SUBDIR, dry_run)
    if remove_exports:
        remove_subdir_files(project_path, PROJECT_EXPORT_SUBDIR, dry_run)
    if hardlink_selects:
        hardlink_select_files(project_path, dry_run)
    if fix_permissions:
        set_files_permissions(project_path, hardlink_selects, dry_run)
    print()


def cleanup_photo_library(
    library_path: Path,
    remove_dotfiles: bool,
    remove_edits: bool,
    remove_exports: bool,
    hardlink_selects: bool,
    fix_permissions: bool,
    dry_run: bool,
):
    if hardlink_selects:
        if are_hardlinks_supported(library_path):
            can_use_hardlinks = True
            hardlinks_description = f"{True}"
        else:
            can_use_hardlinks = False
            hardlinks_description = "⚠️ Filesystem does not support hardlinks"
    else:
        can_use_hardlinks = False
        hardlinks_description = f"{False}"

    print(f"Library          : {library_path}")
    print(f"Remove ._*       : {remove_dotfiles}")
    print(f"Remove edits     : {remove_edits}")
    print(f"Remove exports   : {remove_exports}")
    print(f"Hardlink selects : {hardlinks_description}")
    print(f"Fix permissions  : {fix_permissions}")
    if dry_run:
        print("(dry run)")
    print("---------------")

    for project_dir in find_projects(library_path):
        cleanup_project(
            project_dir,
            remove_dotfiles,
            remove_edits,
            remove_exports,
            hardlink_selects and can_use_hardlinks,
            fix_permissions,
            dry_run,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="cleanup-photo-library")
    parser.add_argument("library", type=str, help="photo library path")
    parser.add_argument(
        "--remove_dotfiles",
        help="remove ._* files",
        action=argparse.BooleanOptionalAction,
        default=True
    )
    parser.add_argument(
        "--remove_edits",
        help="remove files from 1_EDIT",
        action=argparse.BooleanOptionalAction,
        default=True
    )
    parser.add_argument(
        "--remove_exports",
        help="remove files from 2_EXPORT",
        action=argparse.BooleanOptionalAction,
        default=False
    )
    parser.add_argument(
        "--hardlink_selects",
        help="replace selects with hardlinks to matching files in 0_RAW",
        action=argparse.BooleanOptionalAction,
        default=True
    )
    parser.add_argument(
        "--fix_permissions",
        help="remove executable flag and make raw files read-only",
        action=argparse.BooleanOptionalAction,
        default=True
    )
    parser.add_argument(
        "--dry_run",
        help="print actions to be performed, but do not remove or modify any files",
        action=argparse.BooleanOptionalAction,
        default=False
    )

    args = parser.parse_args()

    if not Path(args.library).is_dir():
        raise ApplicationError(f'Photo library directory not found: "{args.library}"')

    cleanup_photo_library(
        Path(args.library),
        args.remove_dotfiles,
        args.remove_edits,
        args.remove_exports,
        args.hardlink_selects,
        args.fix_permissions,
        args.dry_run,
    )
