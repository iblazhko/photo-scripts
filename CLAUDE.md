# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A collection of three standalone Python CLI scripts for managing a personal photography library. No build system, no tests, no dependencies beyond the standard library and two external tools.

## External Tool Dependencies

- **exiv2** — reads and writes EXIF metadata (`rename-raw-photos.py`, `process-photos-for-export.py`)
- **ImageMagick** (`magick`) — resizes images and adds borders (`process-photos-for-export.py`)

## Running the Scripts

All scripts are executable and run directly. They must be run from the correct working directory:

```bash
# Run from inside a PROJECT directory (the one containing 0_RAW/, 1_EDIT/, 2_EXPORT/)
rename-raw-photos.py
process-photos-for-export.py --size medium --border medium --exif ../exif-voigtlander.json

# Run from anywhere, pass library path as argument
cleanup-photo-library.py $HOME/Pictures/Library
cleanup-photo-library.py $HOME/Pictures/Library --dry_run
```

## Library Structure

Scripts assume this directory layout:

```
LIBRARY/
    YYYY-MM-DD <Description>/     # project directory
        0_RAW/                    # camera files, renamed to YYYYMMDD_hhmm_nnnn.ext
        1_EDIT/                   # full-size TIFFs exported from editing app
        2_EXPORT/                 # final JPEGs produced by process-photos-for-export.py
        yyyymmdd_hhmm_nnnn.raw    # selects copied from 0_RAW for editing
```

## Script Responsibilities

**`rename-raw-photos.py`** — renames files in `0_RAW/` in-place. Extracts `DateTimeOriginal` from EXIF via `exiv2`, takes the last 4 digits of the original filename as the camera-assigned image number, produces `YYYYMMDD_hhmm_NNNN.ext` (extension lowercased). Must be run from the project directory.

**`process-photos-for-export.py`** — converts TIFFs from `1_EDIT/` to JPEGs in `2_EXPORT/`. Pipeline: resize with ImageMagick → strip EXIF → copy a curated subset of EXIF tags from the matching OOC JPEG or RAW → apply override rules. Must be run from the project directory. Falls back to `~/Pictures/Library/exif.json` if `--exif` is not specified.

**`cleanup-photo-library.py`** — walks the library tree (detecting project dirs by presence of `0_RAW`/`1_EDIT`/`2_EXPORT` subdirs), then optionally: removes `._*` dot files, removes `1_EDIT` contents, removes `2_EXPORT` contents, replaces select files in the project root with hard links to matching files in `0_RAW` (verified by MD5), and fixes file permissions (raw files read-only, XMP files read-write, executable bit stripped). Has `--dry_run` mode.

## EXIF Override Rules (`exif-voigtlander.json`)

JSON format: a `rules` array where each rule has an optional `pattern` (tag + regex value to match against existing EXIF) and a `tags` array of tags to set. Rules without a pattern always apply. Tag names and value types follow `exiv2` conventions. The included file maps TTArtisan M-Z 6-bit adapter lens identifiers ("Leica M XXmm") to correct Voigtlander lens metadata.
