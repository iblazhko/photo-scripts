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
* EXIF data can be modified using
    [--exif <overrides rules file>] (default=None)

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

import argparse
import copy
import glob
import json
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

OOC_FORMAT = "jpg"
EDIT_FORMAT = "tif"
EXPORT_FORMAT = "jpg"

BORDER_SEPARATOR_DARK_COLOR = "icc-color(gray, 0.6)"
BORDER_SEPARATOR_LIGHT_COLOR = "icc-color(gray, 0.8)"
BORDER_COLOR = "icc-color(gray, 0.96)"

EXIF_TAGS = [
    "Exif.Image.Artist",
    "Exif.Image.Copyright",
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


class ArgumentError(Exception):
    pass


class ApplicationError(Exception):
    pass


@dataclass
class ProjectLocations:
    project_dir: str
    raw_dir: str
    edit_dir: str
    export_dir: str


@dataclass
class BorderSeparatorOptions:
    color: str
    size: int


@dataclass
class BorderOptions:
    color: str
    size: int
    bottom_padding: int
    separators: list[BorderSeparatorOptions]


@dataclass
class ResizeOptions:
    image_width: int
    image_height: int
    border: BorderOptions
    quality: int


@dataclass
class ExifTag:
    key: str
    value: str
    value_type: str = "Ascii"


@dataclass
class MetadataOptions:
    overrides_file: str


@dataclass
class MetadataOverrideRule:
    pattern: ExifTag
    tags: list[ExifTag]


@dataclass
class ExportOptions:
    resize: ResizeOptions
    metadata: MetadataOptions


def pluralize(word, count):
    return word if count == 1 else f"{word}s"


def get_border_options(size: str) -> BorderOptions:
    match size:
        case "large":
            return BorderOptions(
                BORDER_COLOR,
                200,
                40,
                [
                    BorderSeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 2),
                    BorderSeparatorOptions(BORDER_SEPARATOR_DARK_COLOR, 2),
                ],
            )
        case "medium":
            return BorderOptions(
                BORDER_COLOR,
                36,
                0,
                [
                    BorderSeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 2),
                    BorderSeparatorOptions(BORDER_SEPARATOR_DARK_COLOR, 2),
                ],
            )
        case "small":
            return BorderOptions(
                BORDER_COLOR,
                2,
                0,
                [
                    BorderSeparatorOptions(BORDER_SEPARATOR_LIGHT_COLOR, 1),
                    BorderSeparatorOptions(BORDER_SEPARATOR_DARK_COLOR, 1),
                ],
            )
        case "none":
            return None
        case _:
            raise ArgumentError(f"Border option '{size}' is not supported")


def get_resize_options(size: str, border: BorderOptions) -> ResizeOptions:
    match size:
        case "large":
            return ResizeOptions(
                4000,
                3500,
                border,
                99,
            )
        case "medium":
            return ResizeOptions(
                2000,
                1500,
                border,
                97,
            )
        case "small":
            return ResizeOptions(
                900,
                800,
                border,
                95,
            )
        case _:
            raise ArgumentError(f"Resize option '{size}' is not supported")


def get_metadata_options(overrides_rules_file: str):
    return MetadataOptions(overrides_rules_file if overrides_rules_file else None)


def map_exif_tag_from_json(tag_json: object) -> ExifTag:
    return ExifTag(
        tag_json["tag"],
        tag_json["value"],
        tag_json["value_type"] if "value_type" in tag_json else "Ascii",
    )


def map_exif_override_rule_from_json(rule_json: object) -> MetadataOverrideRule:
    return MetadataOverrideRule(
        (
            map_exif_tag_from_json(rule_json["pattern"])
            if "pattern" in rule_json
            else None
        ),
        [map_exif_tag_from_json(x) for x in rule_json["tags"]],
    )


def get_metadata_override_rules(rules_file: str) -> list[MetadataOverrideRule]:
    if os.path.isfile(rules_file):
        rules_json = json.loads(Path(rules_file).read_text())
        return [map_exif_override_rule_from_json(x) for x in rules_json["rules"]]
    else:
        return []


def rule_match(exif_tags: list[str], rule: MetadataOverrideRule) -> bool:
    if rule.pattern:
        k = rule.pattern.key.replace(".", "\\.")
        v = rule.pattern.value
        p = re.compile(f".*{k}.*{v}.*", re.IGNORECASE)
        return next((True for t in exif_tags if p.match(t)), False)
    else:
        return True


def append_metadata_overrides(exif_tags: list[str], metadata_options: MetadataOptions):
    rules = get_metadata_override_rules(metadata_options.overrides_file)
    if rules:
        new_tags = copy.deepcopy(exif_tags)
        for rule in rules:
            if rule_match(exif_tags, rule):
                for t in rule.tags:
                    new_tags.extend([f"set {t.key} {t.value_type} {t.value}"])
        return new_tags
    else:
        return exif_tags


def get_project_locations() -> ProjectLocations:
    project_dir = os.getcwd()

    raw_dir = os.path.join(project_dir, "0_RAW")
    edit_dir = os.path.join(project_dir, "1_EDIT")
    export_dir = os.path.join(project_dir, "2_EXPORT")

    if not os.path.isdir(raw_dir):
        raise ApplicationError(f'Raw images directory not found: "{raw_dir}"')

    if not os.path.isdir(edit_dir):
        raise ApplicationError(f'Edited images directory not found: "{edit_dir}"')

    if not os.path.isdir(export_dir):
        os.mkdir(export_dir)
        if not os.path.isdir(export_dir):
            raise ApplicationError(
                f'Exported images directory not found: "{export_dir}"'
            )

    return ProjectLocations(project_dir, raw_dir, edit_dir, export_dir)


def get_edited_files(edit_dir: str) -> list[str]:
    edits_glob = os.path.join(edit_dir, f"*.{EDIT_FORMAT}")
    files = [pathlib.Path(f).stem for f in glob.glob(edits_glob)]

    if not any(files):
        raise ApplicationError(f'No "{edits_glob}" files found')

    return files


def convert_tiff_to_jpeg(
    file: str, locations: ProjectLocations, resize_options: ResizeOptions, verbose: bool
):
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

    if verbose:
        print()
        print(" ".join(magick))
    subprocess.run(magick)


def copy_metadata(
    file: str,
    locations: ProjectLocations,
    metadata_options: MetadataOptions,
    verbose: bool,
):
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
        if not any(matching_raw_files):
            raw_file_glob = os.path.join(locations.project_dir, pattern)
            matching_raw_files = glob.glob(raw_file_glob)
            if not any(matching_raw_files):
                raise ApplicationError(
                    f'No "{pattern}" files found to copy metadata from'
                )
        source_file = matching_raw_files[0]

    exiv2_cleanup = ["exiv2", "rm", target_file]

    if verbose:
        print()
        print(" ".join(exiv2_cleanup))
    exiv2_cleanup_process = subprocess.run(exiv2_cleanup)
    if exiv2_cleanup_process.returncode != 0:
        raise ApplicationError(f"Could not clean metadata for {target_file}")

    exiv2_tags_options = []
    for x in EXIF_TAGS:
        exiv2_tags_options.extend(["-K", x])
    exiv2_export = ["exiv2", "-PVk"] + exiv2_tags_options + [source_file]

    if verbose:
        print()
        print(" ".join(exiv2_export))
    exiv2_export_process = subprocess.run(
        exiv2_export, capture_output=True, encoding="utf-8"
    )
    if exiv2_export_process.returncode != 0:
        raise ApplicationError(f"Could not get metadata from {source_file}")

    # '.strip()' is a workaround for https://github.com/Exiv2/exiv2/issues/2836
    exif_tags = append_metadata_overrides(
        [x.strip() for x in exiv2_export_process.stdout.splitlines()], metadata_options
    )

    exiv2_import_input = os.linesep.join(exif_tags)

    if verbose:
        print()
        print(f"exiv2 -m- {target_file} <<EOF")
        print(exiv2_import_input)
        print("EOF")
    exiv2_import = ["exiv2", "-m-", target_file]
    exiv2_import_process = subprocess.run(
        exiv2_import, input=exiv2_import_input, text=True
    )
    if exiv2_import_process.returncode != 0:
        raise ApplicationError(f"Could not set metadata for {target_file}")


def process_for_sharing(
    locations: ProjectLocations,
    resize_options: ResizeOptions,
    metadata_options: MetadataOptions,
    verbose: bool,
):
    if not metadata_options.overrides_file:
        default_exif_json = str(Path.home() / "Pictures" / "Library" / "exif.json")
        if os.path.isfile(default_exif_json):
            metadata_options.overrides_file = default_exif_json

    print(f'PROJECT        : "{locations.project_dir}"')
    print(f'RAW            : "{locations.raw_dir}"')
    print(f'EDIT           : "{locations.edit_dir}"')
    print(f'EXPORT         : "{locations.export_dir}"')
    print("---------------")
    print(
        f"Size           : {resize_options.image_width}x{resize_options.image_height}"
    )
    print(
        f"Border         : {resize_options.border.size if resize_options.border else 'None'}"
    )
    print(
        f"EXIF overrides : {metadata_options.overrides_file if metadata_options.overrides_file else 'None'}"
    )
    print("=" * 80)

    tiff_files = sorted(get_edited_files(locations.edit_dir))

    for f in tiff_files:
        if verbose:
            print("---")
        print(f)
        convert_tiff_to_jpeg(f, locations, resize_options, verbose)
        copy_metadata(f, locations, metadata_options, verbose)
        if verbose:
            print()
    count = len(tiff_files)
    if verbose and count > 0:
        print("---")
    print(f'Done ({count} {pluralize("file", count)})')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--size",
        type=str,
        choices=["large", "medium", "small"],
        help="exported image size",
        default="large",
    )
    parser.add_argument(
        "--border",
        type=str,
        choices=["large", "medium", "small", "none"],
        help="border size",
        default="medium",
    )
    parser.add_argument("--exif", type=str, help="EXIF override rules file")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print commands to be executed",
    )

    args = parser.parse_args()

    locations = get_project_locations()
    border_options = get_border_options(args.border)
    resize_options = get_resize_options(args.size, border_options)
    metadata_options = get_metadata_options(args.exif)

    process_for_sharing(locations, resize_options, metadata_options, args.verbose)
