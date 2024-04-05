# Todo

## MLT

Currently, we can export an MLT for ShotCut.
Sadly, ShotCut doesn't do subtitles, so we'll have to add them ourselves later.
For that, we need to either parse the MLT file, or export a ShotCut-EDL file and parse that.
If possible, parsing the MLT will be cleaner.
But we need to make sure we can handle the edits ShotCut introduces.
Then, we just generate a `list[VideoParts]` from the `.mlt` file and we're good to go.