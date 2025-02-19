# Photo Scripts

Various photo manipulation scripts.

These scripts assume following library structure:

```
LIBRARY/
    PROJECT/            -- typically "YYYY-MM-DD <Description>"
        0_RAW/          -- files from camera
            file1.dng
            file1.jpg   -- typically filenames are in
            file2.nef   -- YYYYMMDD_hhmm_nnnn format   
            file2.jpg
            file3.raf
        1_EDIT/         -- files exported from editing application
            file1.tif
            file1-BW.tif
            file2.tif
        2_EXPORT/       -- final images suitable for viewing / sharing
            file1.jpg
            file1-BW.jpg
            file2.jpg
        file1.dng       -- files selected for edit copied to the project's root
        file3.raf
```

Workflow looks like this:

1. Create a project directories following the structure above
2. Copy files from camera to `PROJECT/0_RAW`
3. Run `rename-raw-photos.py`
4. Cull and select photos for edit, copy selects to `PROJECT/`
5. Edit selected photos `PROJECT/` (using Lightroom, Darktable etc.)
6. Export edits as full-size TIFFs to `PROJECT/1_EDIT`
7. Run `process-photos-for-export.py`, take final images from `PROJECT/1_EXPORT`
8. Optional: clean up temporary files and optimise disk usage:
   run `clean-photo-library.py`

## Renaming raw files

`rename-raw-photos.py` script renames files to have following naming convention:

```
YYYYMMDD_hhmm_nnnn.ext
```

i.e. a file name is composed from timestamp (date + time with minutes precision)
followed by image number assigned by the camera.

Timestamp value is based on EXIF metadata, so make sure that the camera datetime
is set correctly.

Having file number assigned by the camera as a suffix

- makes it easy to find images just by looking for 4-digit suffix
- makes sure that RAW + JPG pairs have same base file name
- prevents file names clashes caused by timestamp having only minutes precision,
  multiple images taken within same minute will have different numbers

Usage example:

```bash
rename-raw-photos.py
```

## Processing photos for export / sharing

`process-photos-for-export.py` script prepares final files suitable for sharing
online.

- Images are resized to around 12MP (`--size large`) / 3MP (`--size medium`) /
  1MP (`--size small`)
- Border is added to visually separate image from background they are
  displayed on
- Only a minimal subset of EXIF metadata is retained (camera make and model,
  lens make and model, exposure information)
- There is an option to alter EXIF metadata (see below)

Usage example:

```bash
process-photos-for-export.py --size medium --exif ../exif.json
```

### EXIF metadata overrides

When using manual lenses with no electronic communication on a modern digital
camera, there is no lens information or aperture value recorded in EXIF
metadata.

There are adapters (like TTArtisan M-Z 6-bit adapter) that record _some_ EXIF
metadata, but it may be misleading, e.g in the case of TTArtisan M-Z 6-bit,
it may record lens as a "Leica M XXmm" regardless of what lens is actually
attached, lens focal length is there (provided that you configured the adapter
correctly) but the lens make and model are wrong.

`process-photos-for-export.py` script may help with this to some extent.
`--exif` parameter allows to specify a file with rules for overriding EXIF
metadata.

Format of the override rule is as following:

```json
{
    "pattern": { # optional
        "tag": "tag to look for in the original EXIF metadata",
        "value": "value search pattern (regular expression)"
    },
    "tags": [ # tags that will be added / replaced if the match is found
        {
            "tag": "tag name",
            "value": "tag value",
            "value_type": "tag value type", # optional
        },
    ]
}
```

EXIF tags names and value types follow [`exiv2`](https://exiv2.org/) naming
conventions.

#### Example 1. Adding EXIF metadata

```json
{
    "rules": [
        {
            "tags": [
                {
                    "tag": "Exif.Image.Artist",
                    "value": "John Smith"
                },
                {
                    "tag": "Exif.Image.Copyright",
                    "value": "(C) John Smith. All rights reserved."
                }
            ]
        },
```

Having no `pattern` search condition means that tags in this rule will always
be applied. This can be useful for adding copyright if your camera is not
configured to record it.

#### Example 2. Replacing lens make and model

```json
{
    "rules": [
        {
            "pattern": {
                "tag": "Exif.Photo.LensModel",
                "value": "Leica M 35mm"
            },
            "tags": [
                {
                    "tag": "Exif.Photo.LensMake",
                    "value": "Voigtlander"
                },
                {
                    "tag": "Exif.Photo.LensModel",
                    "value": "Voigtlander 35mm f1.5 Nokton VM"
                },
                {
                    "tag": "Exif.Photo.LensSpecification",
                    "value": "350/10 350/10 150/100 1600/100",
                    "value_type": "Rational"
                }
            ]
        },
```

When we find lens model `Leica M 35mm` recorded by the TTArtisan M-Z 6-bit
adapter, we want to replace this information with the actual lens make and
model.

See [exif.json](./exif-voigtlander.json) in this repository for a complete example.

## Library cleanup

`cleanup-photo-library.py` script

* removes edits from `PROJECT/1_EDIT` - these files can
  always be re-exported from editind application
* uses hard links for RAW selects in `PROJECT/`
  (links them to corresponding files in `PROJECT/0_RAW`)
  to save disk space.

Usage example:

```bash
cleanup-photo-library.py $HOME/Pictures/Library
```