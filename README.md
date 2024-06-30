# Photo Scripts

Various photo manipulation scripts.

These scripts assume following project structure:

```
PROJECT/
    0_RAW/
        file1.dng
        file1.jpg
        file2.nef
        file2.jpg
        file3.raf
    1_EDIT/
        file1.tif
        file1-BW.tif
        file2.tif
    2_EXPORT/
        file1.jpg
        file1-BW.jpg
        file2.jpg
```

Workflow looks like this:

1. Create a project directories following the structure above
2. Copy files from camera to `0_RAW`
3. Run `rename_raw_photos.py`
4. Optional: cull and select photos for edit 
5. Edit photo (Lightroom, Darktable etc)
6. Export edits as full-size TIFFs to `1_EDIT`
7. Run `process-photos-for-export.py`
