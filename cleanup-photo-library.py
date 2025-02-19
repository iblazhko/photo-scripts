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
  always be re-exported from editind application
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
from pathlib import Path

PROJECT_RAW_SUBDIR = "0_RAW"
PROJECT_EDIT_SUBDIR = "1_EDIT"
PROJECT_EXPORT_SUBDIR = "2_EXPORT"
INDENT = "    "


def find_projects(library_path):
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


def remove_dot_files(project_path, dry_run):
    for f in glob.glob(f"{project_path}/**/._*", recursive=True):
        print(f"{INDENT}Removing {f}")
        if not dry_run:
            Path.unlink(f)


def remove_edit_files(project_path, dry_run):
    export_dir = os.path.join(project_path, PROJECT_EDIT_SUBDIR)
    if os.path.isdir(export_dir):
        for x in os.scandir(export_dir):
            if x.is_file():
                print(f"{INDENT}Removing {x.path}")
                if not dry_run:
                    Path.unlink(x.path)
            elif x.is_dir():
                print(f"{INDENT}Removing {x.path}/")
                if not dry_run:
                    shutil.rmtree(x.path)


def get_file_md5_hash(file_path):
    return hashlib.md5(open(file_path, "rb").read()).hexdigest()


def are_hardlinks_supported(path):
    dummy_file = os.path.join(path, ".dummy.dat")
    dummy_link = f"{dummy_file}.link"
    try:
        with open(dummy_file, "w") as f:
            f.write("TEST")
        os.link(dummy_file, dummy_link)
        hardlinks_supported = True
    except (RuntimeError, PermissionError):
        hardlinks_supported = False
    finally:
        if os.path.exists(dummy_link):
            os.unlink(dummy_link)
        if os.path.exists(dummy_file):
            os.unlink(dummy_file)
    return hardlinks_supported


def hardlink_select_files(project_path, dry_run):
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
                        f"{INDENT}Linking {select_path} <- {PROJECT_RAW_SUBDIR}/{file_name}"
                    )
                    if not dry_run:
                        Path.unlink(select_path)
                        os.link(raw_candidate, select_path)
                else:
                    print(
                        f"{INDENT}WARNING: {x.path} content (MD5:{select_md5}) is different from {PROJECT_RAW_SUBDIR}/{x.name} (MD5:{raw_md5})"
                    )


def cleanup_project(
    project_path, remove_dotfiles, remove_edits, hardlink_selects, dry_run
):
    print(f'Cleaning "{project_path}":')
    if remove_dotfiles:
        remove_dot_files(project_path, dry_run)
    if remove_edits:
        remove_edit_files(project_path, dry_run)
    if hardlink_selects:
        hardlink_select_files(project_path, dry_run)
    print()


def cleanup_photo_library(
    library_path, remove_dotfiles, remove_edits, hardlink_selects, dry_run
):
    if hardlink_select_files:
        if are_hardlinks_supported(library_path):
            can_use_hardlinks = True
            hardlinks_description = f"{True}"
        else:
            can_use_hardlinks = False
            hardlinks_description = "Filesystem does not support hardlinks"
    else:
        can_use_hardlinks = False
        hardlinks_description = f"{False}"
    print(f"Library          : {library_path}")
    print(f"Remove ._*       : {remove_dotfiles}")
    print(f"Remove edits     : {remove_edits}")
    print(f"Hardlink selects : {hardlinks_description}")
    if dry_run:
        print("(dry run)")
    print("---------------")

    for project_dir in find_projects(library_path):
        cleanup_project(
            project_dir,
            remove_dotfiles,
            remove_edits,
            hardlink_selects and can_use_hardlinks,
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
        "--dry_run",
        type=bool,
        help="print actions to be performed, bu do not remove or modify any files",
        action=argparse.BooleanOptionalAction,
        default=False,
    )

    args = parser.parse_args()

    if not os.path.isdir(args.library):
        raise Exception(f'Photo library directory not found: "{args.library}"')

    cleanup_photo_library(
        args.library,
        args.remove_dotfiles,
        args.remove_edits,
        args.hardlink_selects,
        args.dry_run,
    )
