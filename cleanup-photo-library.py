#!/usr/bin/env python3

"""Remove temporary files and reduce disk usage

Assuming following library structure:
    Library/
        YYYY-MM-DD <Description>/
            0_RAW/     -- raw files copied from camera and renamed using rename-raw-photos.py
                yyyymmdd_hhmm_nnnn.jpg
                yyyymmdd_hhmm_nnnn.raw
            1_EDIT/    -- edits made in Lightroom/Darktable etc.; usually exported from editing app as full-sized TIFFs
            2_EXPORT/  -- not used by this script
            yyyymmdd_hhmm_nnnn.raw
            yyyymmdd_hhmm_nnnn.raw -- raw files selected for edit; copied from 0_RAW

This script will:
* remove edits from `YYYY-MM-DD <Description>/1_EDIT` - these files can
  always be re-exported from editing application
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
import glob
import os
import shutil

PROJECT_RAW_SUBDIR = "0_RAW"
PROJECT_EDIT_SUBDIR = "1_EDIT"
PROJECT_EXPORT_SUBDIR = "2_EXPORT"
INDENT = "    "


class ApplicationError(Exception):
    pass


def find_projects(library_path: str) -> list[str]:
    result = []
    subdirs = [x for x in os.scandir(library_path) if x.is_dir()]
    if any(
        x.name == PROJECT_RAW_SUBDIR
        or x.name == PROJECT_EDIT_SUBDIR
        or x.name == PROJECT_EXPORT_SUBDIR
        for x in subdirs
    ):
        result.extend([library_path])
    else:
        for x in subdirs:
            result.extend(find_projects(x.path))
    return result


def remove_dot_files(project_path: str, dry_run: bool):
    for f in glob.glob(f"{project_path}/**/._*", recursive=True):
        print(f"{INDENT}❌ {f}")
        if not dry_run:
            os.unlink(f)


def remove_edit_files(project_path: str, dry_run: bool):
    export_dir = os.path.join(project_path, PROJECT_EDIT_SUBDIR)
    if os.path.isdir(export_dir):
        for x in os.scandir(export_dir):
            if x.is_file():
                print(f"{INDENT}❌ {x.path}")
                if not dry_run:
                    os.unlink(x.path)
            elif x.is_dir():
                print(f"{INDENT}❌ {x.path}/")
                if not dry_run:
                    shutil.rmtree(x.path)


def get_file_md5_hash(file_path: str) -> str:
    return hashlib.md5(open(file_path, "rb").read()).hexdigest()


def are_hardlinks_supported(path: str) -> bool:
    dummy_file = os.path.join(path, ".dummy.dat")
    dummy_link = f"{dummy_file}.link"
    try:
        with open(dummy_file, "w", encoding="utf-8") as f:
            f.write("TEST")
        os.link(dummy_file, dummy_link)
        hardlinks_supported = True
    except (
        OSError,
        PermissionError,
        RuntimeError,
    ):
        hardlinks_supported = False
    finally:
        if os.path.exists(dummy_link):
            os.unlink(dummy_link)
        if os.path.exists(dummy_file):
            os.unlink(dummy_file)
    return hardlinks_supported


def hardlink_select_files(project_path: str, dry_run: bool):
    raw_dir = os.path.join(project_path, PROJECT_RAW_SUBDIR)
    if os.path.isdir(raw_dir):
        select_files = [
            x
            for x in os.scandir(project_path)
            if x.is_file()
            and not (x.name.startswith(".") or x.is_junction() or x.is_symlink())
        ]
        for x in select_files:
            file_name = x.name
            select_path = x.path
            raw_candidate = os.path.join(raw_dir, file_name)
            if os.path.exists(raw_candidate) and not os.path.samefile(
                select_path, raw_candidate
            ):
                select_md5 = get_file_md5_hash(select_path)
                raw_md5 = get_file_md5_hash(raw_candidate)
                if select_md5 == raw_md5:
                    print(
                        f"{INDENT}🔗 {select_path} <- {PROJECT_RAW_SUBDIR}/{file_name}"
                    )
                    if not dry_run:
                        os.unlink(select_path)
                        os.link(raw_candidate, select_path)
                else:
                    print(
                        f"{INDENT}⚠️ {x.path} content (MD5:{select_md5}) is different from {PROJECT_RAW_SUBDIR}/{x.name} (MD5:{raw_md5})"
                    )


def set_file_mode(path: str, mode: int, display_path: str, dry_run: bool):
    print(f"{INDENT}✔️ {oct(mode)} {display_path}")
    if not dry_run:
        os.chmod(path, mode)


def set_file_readonly(path: str, display_path: str, dry_run: bool):
    mode = os.stat(path).st_mode
    if mode & 0o000333 :
        new_mode = mode & 0o777444
        set_file_mode(path, new_mode, display_path, dry_run)


def set_file_readwrite(path: str, display_path: str, dry_run: bool):
    mode = os.stat(path).st_mode
    if (mode & 0o000111) or ((mode & 0o000666) != 0o000666):
        new_mode = (mode & 0o777666) | 0o000666
        set_file_mode(path, new_mode, display_path, dry_run)


def set_files_permissions(project_path: str, hardlink_selects: bool, dry_run: bool):
    raw_path_set = set()

    raw_dir = os.path.join(project_path, PROJECT_RAW_SUBDIR)
    if os.path.exists(raw_dir):
        raw_files = [x for x in os.scandir(raw_dir) if x.is_file()]
        for x in raw_files:
            set_file_readonly(x.path, f"{PROJECT_RAW_SUBDIR}/{x.name}", dry_run)
            raw_path_set.add(x.path)

    project_root_files = [x for x in os.scandir(project_path) if x.is_file()]
    for x in project_root_files:
        if hardlink_selects and (x.path in raw_path_set):
            continue
        else:
            _, file_extension = os.path.splitext(x.path)
            if file_extension.lower() == '.xmp':
                set_file_readwrite(x.path, x.name, dry_run)
            else:
                set_file_readonly(x.path, x.name, dry_run)


def cleanup_project(
    project_path: str,
    remove_dotfiles: bool,
    remove_edits: bool,
    hardlink_selects: bool,
    fix_permissions: bool,
    dry_run: bool,
):
    print(f"{project_path}:")
    if remove_dotfiles:
        remove_dot_files(project_path, dry_run)
    if remove_edits:
        remove_edit_files(project_path, dry_run)
    if hardlink_selects:
        hardlink_select_files(project_path, dry_run)
    if fix_permissions:
        set_files_permissions(project_path, hardlink_selects, dry_run)
    print()


def cleanup_photo_library(
    library_path: str,
    remove_dotfiles: bool,
    remove_edits: bool,
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
            hardlink_selects and can_use_hardlinks,
            fix_permissions,
            dry_run,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="cleanup-photos")
    parser.add_argument("library", type=str, help="photo library path")
    parser.add_argument(
        "--remove_dotfiles",
        type=bool,
        help="remove ._* files",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--remove_edits",
        type=bool,
        help="remove files from 1_EDIT",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--hardlink_selects",
        type=bool,
        help="replace selects with hardlinks to matching files in 0_RAW",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--fix_permissions",
        type=bool,
        help="remove executable flag and make raw files read-only",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--dry_run",
        type=bool,
        help="print actions to be performed, but do not remove or modify any files",
        action=argparse.BooleanOptionalAction,
        default=False,
    )

    args = parser.parse_args()

    if not os.path.isdir(args.library):
        raise ApplicationError(f'Photo library directory not found: "{args.library}"')

    cleanup_photo_library(
        args.library,
        args.remove_dotfiles,
        args.remove_edits,
        args.hardlink_selects,
        args.fix_permissions,
        args.dry_run,
    )
