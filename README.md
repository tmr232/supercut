# Supercut

Subtitle-based automatic [supercut](https://en.wikipedia.org/wiki/Supercut) creation.

## Installation

```bash
pip install supercut
```

## Dependencies

Supercut depends on both [ffmpeg] and [VLC].

It expects ffmpeg to be present in the path.

VLC can either be in the path, or defined via the `SUPERCUT_VLC_PATH` environment variable.
On Windows, the default installation path (`C:\Program Files\VideoLAN\VLC\vlc.exe`) is the default.

[ffmpeg]: https://ffmpeg.org/
[VLC]: https://www.videolan.org/

## Usage

Before we start generating videos (which can be time-consuming),
we want to be sure we'll get any results.
We start by listing the speakers present in our videos (often present in SSA subtitles):

```text
>>> supercut names --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv"

┏━━━━━━━━━━━━━┳━━━━━━━┓
┃ Name        ┃ Count ┃
┡━━━━━━━━━━━━━╇━━━━━━━┩
│ Frieren     │ 200   │
│ Himmel      │ 120   │
│ Heiter      │ 118   │
│ Eisen       │ 32    │
│ Fern        │ 24    │
│ Sign        │ 12    │
│ King        │ 12    │
│ Shopkeeper  │ 6     │
│ Herbalist   │ 4     │
│ Attendant a │ 4     │
│ Eptitle     │ 2     │
│ Attendant d │ 2     │
│ Attendant c │ 2     │
│ Attendant b │ 2     │
└─────────────┴───────┘ 
```

Now we know which characters speak in those videos.
We can filter this down by using a query string - the words we expect them to say:

```text
>>> supercut names --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv" --query travel

┏━━━━━━━━━┳━━━━━━━┓
┃ Name    ┃ Count ┃
┡━━━━━━━━━╇━━━━━━━┩
│ Frieren │ 6     │
│ Himmel  │ 2     │
│ Heiter  │ 2     │
└─────────┴───────┘
```

Then, we can list the lines they speak:

```text
>>> supercut list --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv" --query travel

   0 | FRIEREN: I plan to travel around the central lands for the next hundred years or so.
   1 | HIMMEL: Traveling together like this makes me feel like we've returned to those days.
   2 | FRIEREN: We only traveled together for a mere ten years.
   3 | FRIEREN: I've been trying to get to know the people I meet on my travels as much as possible.
   4 | HEITER: Will you take her with you on your travels?
   5 | FRIEREN: I plan to travel around the central lands for the next hundred years or so.
   6 | HIMMEL: Traveling together like this makes me feel like we've returned to those days.
   7 | FRIEREN: We only traveled together for a mere ten years.
   8 | FRIEREN: I've been trying to get to know the people I meet on my travels as much as possible.
   9 | HEITER: Will you take her with you on your travels?

```

Or preview them in VLC:

```text
>>> supercut preview --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv" --query travel
```

We can also filter further using the `--name` flag.

If we're happy with the preview, we can go ahead and render it:

```text
>>> supercut render --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv" --query travel --output travel.mkv
```

### Editing

If we want to remove or reorder some of the lines, we need to use `edit`:

```text
supercut edit create --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv" --query travel --listfile edit.txt
```

This will generate a list, like the one we saw before.
We can edit it freely - reordering, removing, duplicating, or commenting-out lines:

```text
   0 | FRIEREN: I plan to travel around the central lands for the next hundred years or so.
   1 | HIMMEL: Traveling together like this makes me feel like we've returned to those days.
#   2 | FRIEREN: We only traveled together for a mere ten years.
   3 | FRIEREN: I've been trying to get to know the people I meet on my travels as much as possible.

   5 | FRIEREN: I plan to travel around the central lands for the next hundred years or so.
   6 | HIMMEL: Traveling together like this makes me feel like we've returned to those days.
   1 | HIMMEL: Traveling together like this makes me feel like we've returned to those days.
   7 | FRIEREN: We only traveled together for a mere ten years.
   8 | FRIEREN: I've been trying to get to know the people I meet on my travels as much as possible.
```

Once we are done, we can preview the list:

```text
supercut edit preview --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv" --query travel --listfile edit.txt
```

And if we're happy, render it:

```text
supercut edit preview --cache-dir ./workdir "Sousou No Frieren 01.mkv" "Sousou No Frieren 02.mkv" --query travel --listfile edit.txt --output travel.mkv
```

## Supported Formats

At the moment, the only export format is `.mkv`.

As for input, all ffmpeg-supported formats should be supported.
To read subs stored externally (a `.srt` file, for example) use the `--external-subs` flag.