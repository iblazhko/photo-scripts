#!/usr/bin/env python3

"""Convert edited photos to JPEGs suitable for sharing

Assuming following project structure:
    0_RAW/
        file1.dng
        file1.jpg
        file2.nef
        file2.jpg
        file3.raf
    1_EDIT/ -- assuming files here are full-size TIFFs
        file1.tif
        file1-BW.tif
        file2.tif
    2_EXPORT/

This script will convert TIFFs from 1_EDIT to JPEGs and put them
into 2_EXPORT:
    2_EXPORT/
        file1.jpg
        file1-BW.jpg
        file2.jpg

* Exported files are rescaled to fit small/medium/large export size and converted to JPEG
    [--size large|medium|small] (default=large)
* White border is added (around 5%, optional)
    [--border | --no-border] (default=True)
* Basic EXIF metadata is copied from raw / OOC JPEG files to resulting JPEGs
* Extra EXIF tags can be added using `--extra_exif key=value key=value ...`, e.g.
    --extra_exif Exif.Photo.LensMake=Voightlander 'Exif.Photo.LensModel=50mm f/2 APO Lanthar'

Script requires following tools to be installed:

* Imagemagick (`brew install imagemagick`)
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
import subprocess
import argparse
from dataclasses import dataclass

OOC_FORMAT = "jpg"  # Optional
EDIT_FORMAT = "tif"
EXPORT_FORMAT = "jpg"

BORDER_SEPARATOR_DARK_COLOR = "icc-color(gray, 0.6)"
BORDER_SEPARATOR_LIGHT_COLOR = "icc-color(gray, 0.8)"
BORDER_COLOR = "icc-color(gray, 0.96)"

EXIF_TAGS = [
    "Exif.Image.DateTime",
    "Exif.Image.Make",
    "Exif.Image.Model",
    "Exif.Image.Software",
    "Exif.Photo.ApertureValue",
    "Exif.Photo.BrightnessValue",
    "Exif.Photo.DateTimeDigitized",
    "Exif.Photo.DateTimeOriginal",
    "Exif.Photo.ExifVersion",
    "Exif.Photo.ExposureBiasValue",
    "Exif.Photo.ExposureProgram",
    "Exif.Photo.ExposureTime",
    "Exif.Photo.Flash",
    "Exif.Photo.FNumber",
    "Exif.Photo.FocalLength",
    "Exif.Photo.FocalLengthIn35mmFilm",
    "Exif.Photo.ISOSpeedRatings",
    "Exif.Photo.LensMake",
    "Exif.Photo.LensModel",
    "Exif.Photo.LensSpecification",
    "Exif.Photo.LightSource",
    "Exif.Photo.MaxApertureValue",
    "Exif.Photo.MeteringMode",
    "Exif.Photo.SensitivityType",
    "Exif.Photo.ShutterSpeedValue",
]


@dataclass
class ProjectLocations:
    project_dir: str
    raw_dir: str
    edit_dir: str
    export_dir: str


@dataclass
class SeparatorOptions:
    color: str
    size: int


@dataclass
class BorderOptions:
    color: str
    size: int
    bottom_padding: int
    separators: list[SeparatorOptions]


@dataclass
class ResizeOptions:
    image_width: str
    image_height: str
    border: BorderOptions
    quality: int


@dataclass
class ExifTag:
    key: str
    value: str


@dataclass
class MetadataOptions:
    artist: str
    copyright: str
    extra_exif: list[ExifTag]


@dataclass
class ExportOptions:
    resize: ResizeOptions
    metadata: MetadataOptions


def empty(x):
    return len(x) == 0


def pluralize(word, count):
    return word if count == 1 else f"{word}s"


def get_resize_options(size, add_border):
    match size:
        case "large":
            return ResizeOptions(
                4000,
                3500,
                (
                    BorderOptions(
                        BORDER_COLOR,
                        100,
                        20,
                        [
                            SeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 1),
                            SeparatorOptions(BORDER_SEPARATOR_DARK_COLOR, 2),
                            SeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 1),
                        ],
                    )
                    if add_border
                    else None
                ),
                99,
            )
        case "medium":
            return ResizeOptions(
                1500,
                1200,
                (
                    BorderOptions(
                        BORDER_COLOR,
                        40,
                        10,
                        [
                            SeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 1),
                            SeparatorOptions(BORDER_SEPARATOR_DARK_COLOR, 1),
                            SeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 1),
                        ],
                    )
                    if add_border
                    else None
                ),
                97,
            )
        case "small":
            return ResizeOptions(
                800,
                700,
                (
                    BorderOptions(
                        BORDER_COLOR,
                        20,
                        5,
                        [
                            SeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 1),
                            SeparatorOptions(BORDER_SEPARATOR_DARK_COLOR, 1),
                            SeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 1),
                        ],
                    )
                    if add_border
                    else None
                ),
                95,
            )
        case _:
            raise Exception(f"Size {size} is not supported")


def get_metadata_options(artist, copyright, extra_exif):
    extra_kvp = []
    if extra_exif:
        for x in extra_exif:
            kvp = x.split("=", 1)
            extra_kvp.append(ExifTag(kvp[0], kvp[1]))

    return MetadataOptions(
        artist if artist else None, copyright if copyright else None, extra_kvp
    )


def get_project_locations():
    project_dir = os.getcwd()

    raw_dir = os.path.join(project_dir, "0_RAW")
    edit_dir = os.path.join(project_dir, "1_EDIT")
    export_dir = os.path.join(project_dir, "2_EXPORT")

    if not os.path.isdir(raw_dir):
        raise Exception(f'Raw images directory not found: "{raw_dir}"')

    if not os.path.isdir(edit_dir):
        raise Exception(f'Edited images directory not found: "{edit_dir}"')

    if not os.path.isdir(export_dir):
        os.mkdir(export_dir)
        if not os.path.isdir(export_dir):
            raise Exception(f'Exported images directory not found: "{export_dir}"')

    return ProjectLocations(project_dir, raw_dir, edit_dir, export_dir)


def get_edited_files(edit_dir):
    edits_glob = os.path.join(edit_dir, f"*.{EDIT_FORMAT}")
    files = [pathlib.Path(f).stem for f in glob.glob(edits_glob)]

    if empty(files):
        raise Exception(f'No "{edits_glob}" files found')

    return files


def convert_tiff_to_jpeg(file, locations, resize_options):
    target_normalized_name = file.removesuffix("-Enhanced-NR")

    source_file = os.path.join(locations.edit_dir, f"{file}.{EDIT_FORMAT}")
    target_file = os.path.join(
        locations.export_dir, f"{target_normalized_name}.{EXPORT_FORMAT}"
    )

    # fmt: off
    border_options = []
    if resize_options.border:
        b = resize_options.border
        for s in b.separators:
            border_options.extend([
                "-bordercolor", f"{s.color}",
                "-border",      f"{s.size}",
            ])

        border_options.extend([
            "-bordercolor", f"{b.color}",
            "-border",      f"{b.size}",
            "-background",  f"{b.color}",
            "-extent",      f"0x%[fx:h+{b.bottom_padding}]",
        ])

    magick = [
                "magick",
                "-quiet",
                source_file,
                "-filter",  "LanczosSharp",
                "-resize",  f"{resize_options.image_width}x{resize_options.image_height}>",
            ] + border_options + [
                "-quality", f"{resize_options.quality}",
                target_file,
            ]
    # fmt: on

    subprocess.run(magick)


def copy_metadata(file, locations, metadata_options):
    source_normalized_name = file.removesuffix("-BW").removesuffix("-Enhanced-NR")
    target_normalized_name = file.removesuffix("-Enhanced-NR")

    source_file = os.path.join(
        locations.raw_dir, f"{source_normalized_name}.{OOC_FORMAT}"
    )
    target_file = os.path.join(
        locations.export_dir, f"{target_normalized_name}.{EXPORT_FORMAT}"
    )

    # prefer out of the camera JPEG as metadata source, otherwise use RAW or enhanced DNG
    if not os.path.isfile(source_file):
        pattern = f"{source_normalized_name}*.*"
        raw_file_glob = os.path.join(locations.raw_dir, pattern)
        matching_raw_files = glob.glob(raw_file_glob)
        if empty(matching_raw_files):
            raw_file_glob = os.path.join(locations.project_dir, pattern)
            matching_raw_files = glob.glob(raw_file_glob)
            if empty(matching_raw_files):
                raise Exception(f'No "{pattern}" files found to copy metadata from')
        source_file = matching_raw_files[0]

    exiv2_cleanup = ["exiv2", "rm", target_file]

    exiv2_tags_options = []
    for x in EXIF_TAGS:
        exiv2_tags_options.extend(["-K", x])

    exiv2_export = ["exiv2", "-PVk"] + exiv2_tags_options + [source_file]

    # fmt: off
    trim_trailing_spaces = [
        "sed",
        "-e", "s/^[[:space:]]*//",
        "-e", "s/[[:space:]]*$//",
    ]
    # fmt: on

    exiv2_import = ["exiv2", "-m-", target_file]

    subprocess.run(exiv2_cleanup)

    # exiv2 export output piped into exiv2 import input
    exiv2_export_process = subprocess.Popen(exiv2_export, stdout=subprocess.PIPE)

    # workaround for https://github.com/Exiv2/exiv2/issues/2836
    trim_trailing_spaces_process = subprocess.Popen(
        trim_trailing_spaces, stdin=exiv2_export_process.stdout, stdout=subprocess.PIPE
    )

    exiv2_import_process = subprocess.Popen(
        exiv2_import, stdin=trim_trailing_spaces_process.stdout
    )

    exiv2_import_process.wait()
    trim_trailing_spaces_process.wait()
    exiv2_export_process.wait()

    extra_tags = []
    if metadata_options.artist:
        extra_tags.extend(
            ["-M", f"set Exif.Image.Artist Ascii {metadata_options.artist}"]
        )

    if metadata_options.copyright:
        extra_tags.extend(
            ["-M", f"set Exif.Image.Copyright Ascii {metadata_options.copyright}"]
        )

    if metadata_options.extra_exif:
        for x in metadata_options.extra_exif:
            extra_tags.extend(["-M", f"set {x.key} Ascii {x.value}"])

    if not empty(extra_tags):
        exif_copyright = ["exiv2"] + extra_tags + [target_file]
        subprocess.run(exif_copyright)


def process_for_sharing(locations, resize_options, metadata_options):
    print(f'PROJECT:   "{locations.project_dir}"')
    print(f'RAW:       "{locations.raw_dir}"')
    print(f'EDIT:      "{locations.edit_dir}"')
    print(f'EXPORT:    "{locations.export_dir}"')
    print(f"Size:      {resize_options.image_width}x{resize_options.image_height}")
    print(f"Border:    {'True' if resize_options.border else 'False'}")
    print(f"Artist:    {metadata_options.artist if metadata_options.artist else 'N/A'}")
    print(
        f"Copyright: {metadata_options.copyright if metadata_options.copyright else 'N/A'}"
    )
    print("=" * 65)

    tiff_files = sorted(get_edited_files(locations.edit_dir))

    for f in tiff_files:
        print(f)
        convert_tiff_to_jpeg(f, locations, resize_options)
        copy_metadata(f, locations, metadata_options)
    count = len(tiff_files)
    print(f'Done ({count} {pluralize("file", count)})')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--size",
        type=str,
        choices=["large", "medium", "small"],
        help="exported image size",
        default="large",  # fmt: on
    )
    parser.add_argument(
        "--border",
        type=bool,
        help="add white border",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--artist",
        type=str,
        help="add artist tag",
        action=argparse.BooleanOptionalAction,
        default="Ivan Blazhko",
    )
    parser.add_argument(
        "--copyright",
        type=str,
        help="add copyright tag",
        action=argparse.BooleanOptionalAction,
        default="(C) Ivan Blazhko. All rights reserved.",
    )
    parser.add_argument(
        "--extra_exif", type=str, help="extra EXIF tags (key=value)", nargs="*"
    )

    args = parser.parse_args()

    locations = get_project_locations()
    resize_options = get_resize_options(args.size, args.border)
    metadata_options = get_metadata_options(
        args.artist, args.copyright, args.extra_exif
    )

    process_for_sharing(locations, resize_options, metadata_options)
