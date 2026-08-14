# Audiobook pipeline

Local text-to-speech audiobooks for tolstoy.life works — one `.m4b` per work,
to sit beside the existing EPUBs. First subject: **A Great Iniquity** (Tolstoy,
~10k words, single-narrator essay, intro + 9 Parts).

Everything runs locally on the Mac (no API keys, no cloud): Kokoro TTS + ffmpeg.

## Status

- **A Great Iniquity's read-along audio is live** in the reader bundle
  (`docs/reader/non-fiction/essays-and-criticism/the-great-sin/build/`) — 10
  sections, mastered, synced via `timing.en-1905.json`. The `.m4b` in this
  folder (`a_great_iniquity_bm_daniel.m4b`, 54:45) is a snapshot from the
  first pilot build; the current build no longer produces an `.m4b` at all
  (see "How to run" below), so treat that file as a point-in-time export, not
  a live artifact.
- The core question is settled: **Kokoro is good enough** for publication
  quality. No heavier model needed.
- Narrator voice: **bm_daniel** (British male, "warm, regular-guy").

The deep "why" behind every setting lives in
[../../docs/audiobook-pipeline.md](../../docs/audiobook-pipeline.md).

## How to run

```sh
# Synth + master + time -> writes audio/*.m4a + timing.<version>.json into
# the reader bundle's build/ folder, beside segments.<version>.json.
# Resumable: re-running skips any sentence whose WAV is already cached in
# wav_full_<voice>/. No --dry mode — every run synthesizes for real; there is
# no flag that previews structure without producing audio.
python3 build_audiobook.py            # defaults to bm_daniel

# Audition voices on the 3 hardest sentences  ->  audition_<voice>.wav
python3 audition.py
```

Requires `kokoro-tts-tool`, `ffmpeg`, `ffprobe` (and `espeak-ng`). The build
reads `segments.<version>.json` from the reader bundle (the text-shaping
rules live in the main repo's `reader/speech.py` + `reader/segment.py`, which
own the final speech text) and only does audio: synth each clip, splice in
pauses, master, write one `.m4a` per section + `timing.<version>.json`.

There are two kinds of pause. The gaps *between* clips — sentence, paragraph and Part — are silences the build inserts itself (the `SENT_GAP` / `PARA_GAP` / `CHAP_GAP` constants; easy to change). The pauses at commas, dashes and semicolons *inside* a sentence are baked into Kokoro's audio (~0.14s, with no setting to change them), so to lengthen those the build post-processes each synthesized clip: it finds the quiet runs inside the sentence and splices a little more silence into each — `PAUSE_PAD` seconds per pause (tuned by ear to 0.02s, so a comma goes ~0.14s → ~0.16s). The padded clips are rebuilt from the raw cache on every run into `wav_full_<voice>_pad/`, so the raw voice cache is never touched and a re-run can't stack pause on pause. `python3 build_audiobook.py --selftest` checks the splice arithmetic.

**`chapters/`, `chapters_flow/`, and `flow_preprocess.py` are not read by
this build** — a leftover from an earlier version of the pipeline, before it
moved to reading segments.json directly. They're kept in sync by hand as a
convenience (plain-text reference, and Kokoro voice audition input for
`audition.py`), but editing them alone does nothing to the actual audio; the
source of truth is the bundle's `.md` in the main Tolstoy repo.

> Sideloaded audiobooks do **not** iCloud-sync. To get the `.m4b` onto a phone:
> AirDrop → Files → Share → Copy to Books (or Finder cable sync).

## Layout

```
build_audiobook.py     the builder (reads segments.json; the one you run)
flow_preprocess.py     punctuation reshaping — not read by the build (see above)
audition.py            render the 3 problem sentences in any set of voices
chapters/              plain-text reference copy, one file per section (ch00..ch09) — not read by the build
chapters_flow/         chapters/ after flow_preprocess — not read by the build
wav_full_bm_daniel/    per-sentence audio cache (gitignored; resume lives here)
wav_full_bm_daniel_pad/  padded clips: raw cache with internal comma pauses lengthened (gitignored; rebuilt each run)
_resources/            scratch reference audio (gitignored)
IDEAS.md               parked feature ideas (read-along)
```

Audio (`*.wav`, `*.m4b`) and caches are gitignored — they regenerate from the
scripts + chapter text.

## Open / next

- **Semicolons.** The bundle's speech text (George's semicolons rewritten to
  periods/commas — now in `reader/speech.py`, main repo) is what gets narrated.
  Now that phrasing is good, worth testing whether we can narrate the original
  text (semicolons intact) and retire that rewrite.
- ~~**Short-sentence pitch wobble**~~ — done: the build merges very short
  sentences (and Part headers) into a neighbour so they don't get synthesized
  alone. See `merge_short` in `build_audiobook.py`.
- ~~**Proper-noun pronunciation**~~ — done by ear for the names that fumbled
  (Labouchère, Radischeff, Yasnaya Poliana) via the `SUBS` dict in the build.
- **Nightly pipeline** for the whole corpus: hash each work, regenerate only on
  change, Whisper transcript check, output to `_generated/audio/<work>.m4b`.
- **Read-along** (synced text+audio) — see [IDEAS.md](IDEAS.md).
