# Audiobook pipeline

Local text-to-speech audiobooks for tolstoy.life works — one `.m4b` per work,
to sit beside the existing EPUBs. First subject: **A Great Iniquity** (Tolstoy,
~10k words, single-narrator essay, intro + 9 Parts).

Everything runs locally on the Mac (no API keys, no cloud): Kokoro TTS + ffmpeg.

## Status

- **A Great Iniquity is done.** `a_great_iniquity_bm_daniel.m4b` — 54:45, 10
  chapters, mastered, imports into Apple Books.
- The core question is settled: **Kokoro is good enough** for publication
  quality. No heavier model needed.
- Narrator voice: **bm_daniel** (British male, "warm, regular-guy").

The deep "why" behind every setting lives in
[../../docs/audiobook-pipeline.md](../../docs/audiobook-pipeline.md).

## How to run

```sh
# Full audiobook  ->  a_great_iniquity_<voice>.m4b   (resumable; ~40 min cold)
python3 build_audiobook.py            # defaults to bm_daniel
python3 build_audiobook.py --dry      # show chapter/sentence structure, no audio

# Audition voices on the 3 hardest sentences  ->  audition_<voice>.wav
python3 audition.py

# Reshape punctuation for better phrasing  (chapters/ -> chapters_flow/)
python3 flow_preprocess.py
```

Requires `kokoro-tts-tool`, `ffmpeg`, `ffprobe` (and `espeak-ng`). The build
reads `chapters_flow/`, synthesizes one WAV per sentence (cached in
`wav_full_<voice>/`, so re-runs only redo what changed), splices in pauses,
masters, adds chapter markers, and muxes the M4B with `+faststart`.

> Sideloaded audiobooks do **not** iCloud-sync. To get the `.m4b` onto a phone:
> AirDrop → Files → Share → Copy to Books (or Finder cable sync).

## Layout

```
build_audiobook.py     the builder (full book; the one you run)
flow_preprocess.py     punctuation reshaping for cleaner Kokoro phrasing
audition.py            render the 3 problem sentences in any set of voices
chapters/              source narration text, one file per section (ch00..ch09)
chapters_flow/         chapters/ after flow_preprocess — what the build narrates
wav_full_bm_daniel/    per-sentence audio cache (gitignored; resume lives here)
_resources/            scratch reference audio (gitignored)
IDEAS.md               parked feature ideas (read-along)
```

Audio (`*.wav`, `*.m4b`) and caches are gitignored — they regenerate from the
scripts + chapter text.

## Open / next

- **Semicolons.** The build narrates `chapters_flow/` (George's semicolons
  rewritten to periods/commas). Now that phrasing is good, worth testing whether
  we can narrate the original text (semicolons intact) and retire that step.
- **Short-sentence pitch wobble** — a minor Kokoro trait; possibly soften by not
  synthesizing very short sentences alone.
- **Proper-noun pronunciation** not yet validated (Yasnaya Polyana, Novikoff…).
- **Nightly pipeline** for the whole corpus: hash each work, regenerate only on
  change, Whisper transcript check, output to `_generated/audio/<work>.m4b`.
- **Read-along** (synced text+audio) — see [IDEAS.md](IDEAS.md).
