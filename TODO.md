# Todo

## MLT

Currently, we can export an MLT for ShotCut.
Sadly, ShotCut doesn't do subtitles, so we'll have to add them ourselves later.
For that, we need to either parse the MLT file, or export a ShotCut-EDL file and parse that.
If possible, parsing the MLT will be cleaner.
But we need to make sure we can handle the edits ShotCut introduces.
Then, we just generate a `list[VideoParts]` from the `.mlt` file and we're good to go.


A good way to do this is to use either the name or the ID of the Supercut playlist.
This should be easy as long as the person editing the video is disciplined and only does cuts.

Additionally, we should scale-down the video instead of pre-cutting it, as it makes for better editing experience,
and allows for a faster re-export if needed.
So instead of adding a `--cut` option, we add a `util scale-to --width 480` option, work with that,
then replace the video after the import from MLT.