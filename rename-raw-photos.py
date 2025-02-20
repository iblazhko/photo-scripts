#!/usr/bin/env python3

"""Rename raw photos to include timestamp and the original camera file number

Assuming following project structure:
    0_RAW/     -- raw files; last 4 symbols of a file name are supposed to be
                  a photo number assigned by the camera that took the photo
        DSC_1234.JPG
        DSC_1234.NEF
        R0002345.JPG
        R0002345.DNG
    1_EDIT/    -- not used by this script
    2_EXPORT/  -- not used by this script

This script will:
* convert extensions to lowercase
* take last 4 digits of the raw file name, assuming this is a
  picture number assigned by a camera
* append datetime prefix
* rename raw files in 0_RAW in-place

Resulting file names will look like this:

    YYYYMMDD_hhmm_NNNN.raw

Script requires following tools to be installed:

* Exiv2 (`brew install exiv2`)
* Python, obviously (`brew install python`)

* * *

Copyright 2024 Ivan Blazhko

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

import os
import glob
import pathlib
import re
import subprocess

EXIV2_DATETIME_ORIGINAL = "Exif.Photo.DateTimeOriginal"

exiv2_datetime_re = re.compile(
    "set "
    + EXIV2_DATETIME_ORIGINAL.replace(".", "\\.")
    + "\\s*(Ascii)?\\s+(?P<year>\\d{4})\\:(?P<month>\\d{2})\\:(?P<day>\\d{2}) (?P<hour>\\d{2})\\:(?P<minute>\\d{2})\\:(?P<second>\\d{2})",
    re.IGNORECASE,
)


class ApplicationError(Exception):
    pass


def get_raw_path():
    project_dir = os.getcwd()

    raw_dir = os.path.join(project_dir, "0_RAW")
    if not os.path.isdir(raw_dir):
        raise ApplicationError(f'Raw images directory not found: "{raw_dir}"')

    return raw_dir


def get_raw_files(raw_dir: str):
    files = [
        (pathlib.Path(f).stem, pathlib.Path(f).suffix)
        for f in glob.glob(os.path.join(raw_dir, "*.*"))
    ]

    if not any(files):
        raise ApplicationError(f'No files found in "{raw_dir}"')

    return sorted(files, key=lambda x: f"{x[0]}.{x[1]}")


def construct_new_raw_filename(raw_dir: str, raw_file: str, ext: str):
    camera_number = raw_file[-4:]
    if not camera_number:
        raise ApplicationError(
            f'Could not extract camera number: "{raw_dir}/{raw_file}{ext}"'
        )

    raw_file_path = os.path.join(raw_dir, f"{raw_file}{ext}")

    # fmt: off
    exiv2_timestamp = [
        "exiv2",
        "-PVk",
        "-K", EXIV2_DATETIME_ORIGINAL,
        raw_file_path,
    ]
    # fmt: on

    exiv2_proc = subprocess.Popen(exiv2_timestamp, stdout=subprocess.PIPE)
    exiv2_output = exiv2_proc.communicate()[0].decode("utf-8")

    if not exiv2_output:
        raise ApplicationError(f'Could not extract EXIF timestamp: "{raw_file_path}"')

    match = exiv2_datetime_re.match(exiv2_output)
    if not match:
        raise ApplicationError(f'Could not extract EXIF timestamp: "{raw_file_path}"')

    timestamp_year = match.group("year")
    timestamp_month = match.group("month")
    timestamp_day = match.group("day")
    timestamp_hour = match.group("hour")
    timestamp_minute = match.group("minute")

    if not (
        timestamp_year
        and timestamp_month
        and timestamp_day
        and timestamp_hour
        and timestamp_minute
    ):
        raise ApplicationError(f'Could not extract EXIF timestamp: "{raw_file_path}"')

    new_name = f"{timestamp_year}{timestamp_month}{timestamp_day}_{timestamp_hour}{timestamp_minute}_{camera_number}"

    return (new_name, ext.lower())


def rename_raw_file(
    raw_dir: str,
    original_name: str,
    original_extension: str,
    new_name: str,
    new_extension: str,
):
    original_file = os.path.join(raw_dir, f"{original_name}{original_extension}")
    new_file = os.path.join(raw_dir, f"{new_name}{new_extension}")
    os.rename(original_file, new_file)


def rename_all_raw_files():
    raw_dir = get_raw_path()
    print(f'RAW: "{raw_dir}"')
    print("=" * 65)

    raw_files = get_raw_files(raw_dir)
    if not any(raw_files):
        print(f'No files found in "{raw_dir}"')
    else:
        for f, e in raw_files:
            new_name, new_extension = construct_new_raw_filename(raw_dir, f, e)
            print(f"{f}{e} -> {new_name}{new_extension}")
            rename_raw_file(raw_dir, f, e, new_name, new_extension)
        print("Done")


if __name__ == "__main__":
    rename_all_raw_files()
