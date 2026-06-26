# Audiobook / tolstoy.life — feature ideas

Parked ideas surfaced during the audiobook work. Not committed; not scheduled.

## Read-along (synchronized text + audio highlight)

Show the text highlighted in sync with the narration, so you read while listening.
Surfaced 2026-06-25 while reviewing the ch02 audiobook — Johan read along to the
audio for the first time and wanted it as a tolstoy.life feature.

**Where it earns its place:** not as a blanket comprehension aid, but to **anchor
proper nouns** — names of people and places that slip past in audio but stick when
seen spelled. So it's most valuable for the philosophical / fact-dense works full of
references (e.g. *What Is Art?* — Schopenhauer, Baumgarten, Véron…), less so for
narrative prose. Johan's analogy: he keeps English subtitles on American films even
when Swedish ones exist, to remember the characters' names.

**Synergy with the audiobook:** also cancels the proper-noun *pronunciation* risk
(Kokoro mangling Yasnaya Polyana, Novikoff, Radischeff) — even if the voice fumbles
a name, the reader sees it spelled correctly.

**Why the pipeline is well-placed:** the build synthesizes one WAV per sentence with
known durations, so sentence-level timing is essentially a free byproduct. Word-level
needs forced alignment, but Whisper (already planned for transcript validation) gives
word timestamps.

**How:**
- Ebook: **EPUB3 Media Overlays** (W3C, a SMIL profile — pairs HTML-id'd text to audio
  start/end times; Apple Books does highlight + tap-to-play). Tool: syncabook.
- Website: native `<audio>` + a JSON map of `sentence-id → start/end` + ~30 lines of JS
  highlighting on `timeupdate`, seek-on-click. Lean-web, no framework.

Status: parked behind finishing the audiobook.
