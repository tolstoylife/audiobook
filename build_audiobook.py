#!/usr/bin/env python3
"""
Build the full chaptered, mastered M4B of "A Great Iniquity".

Pipeline and findings: README.md (this folder) and ../../docs/audiobook-pipeline.md.
  - voice bm_daniel, synthesized PER SENTENCE via `synthesize`
    (NOT `infinite` — its streaming step mangled long-sentence endings; an A/B
     on ch02 confirmed `synthesize` lands sentence endings cleanly)
  - sentence / paragraph / chapter pauses, mastered, chapter markers,
    M4B muxed with +faststart (iOS Books refuses the file without it)

Reads chapters_flow/ (flow-preprocessed text). Resumable: re-running skips
sentences whose WAV already exists.

  python3 build_audiobook.py [voice] [--dry]
Requires: kokoro-tts-tool, ffmpeg, ffprobe.
"""
import subprocess, os, re, sys, json

ARGS     = [a for a in sys.argv[1:] if not a.startswith("--")]
VOICE    = ARGS[0] if ARGS else "bm_daniel"
SENT_GAP = 0.45   # pause between sentences within a paragraph
PARA_GAP = 0.85   # pause between paragraphs (most end on a George quote — Johan wanted longer)
CHAP_GAP = 2.0    # pause between Parts (research: section breaks ~2–2.5s; clearly > paragraph)
BITRATE  = "128k"
SR       = 24000  # Kokoro's native rate
CACHE    = f"wav_full_{VOICE}"
MASTER   = "highpass=f=70,deesser=i=0.4,loudnorm=I=-19:TP=-2:LRA=7"

# The text-shaping rules (flow fixes, pronunciation respellings, sentence split,
# spoken headers) used to live here. They now live in reader/speech.py + reader/
# segment.py so the segmenter owns them and segments.json carries final speech text.
# This build reads segments.json and only does audio: synth + master + time.

# ── Pure clip + timeline logic (the only arithmetic worth a test) ──────────────
def iter_clips(seg):
    """Flatten one version's segments.json into ordered synth clips.
    Heading first per section, then each sentence. gap_after = PARA_GAP for the
    last sentence in a paragraph, else SENT_GAP. The CHAP_GAP between sections is
    silence the builder inserts between section files, not a clip's gap."""
    clips = []
    for sec in seg["sections"]:
        clips.append({"id": sec["id"], "speech": sec["headingSpeech"],
                      "gap_after": SENT_GAP, "section": sec["id"],
                      "is_section_start": True})
        for para in sec["paragraphs"]:
            sents = para["sentences"]
            for i, s in enumerate(sents):
                clips.append({"id": s["id"], "speech": s["speech"],
                              "gap_after": PARA_GAP if i == len(sents) - 1 else SENT_GAP,
                              "section": sec["id"], "is_section_start": False})
    return clips

def build_timeline(clips, duration_of):
    """Per-section relative begin/end. Each section's audio file restarts at 0;
    the gap *after* a clip is silence that lives inside that section's file."""
    out = {}
    cur_section = None
    cum = 0.0
    for c in clips:
        if c["section"] != cur_section:
            cur_section, cum = c["section"], 0.0
        begin = round(cum, 3)
        end = round(cum + duration_of(c["id"]), 3)
        out[c["id"]] = {"section": c["section"], "begin": begin, "end": end}
        cum = end + c["gap_after"]
    return {"clips": out}

# ── I/O helpers (untested side-effects, same as before) ────────────────────────
def run(cmd, **kw): subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
def dur(path):
    return float(subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0", path], text=True).strip())
def make_sil(path, sec):
    if not os.path.exists(path):
        run(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono","-t",str(sec),"-c:a","pcm_s16le", path])

# ponytail: merge_short (gluing 2–4 word clips into a neighbour for cadence) is
# dropped — it changed sentence count, which would break the 1 sentence = 1 SMIL
# <par> read-along mapping. Add back as an audio-only speechGroup field in
# segments.json if Chapter I's short dialogue lines read poorly. Known ceiling:
# a 2–4 word clip synthesized alone can rise instead of fall.
# ponytail: the whole-book .m4b mux is dropped here too — the read-along proof
# needs per-section .m4a + timing.json, and the standalone .m4b is independent of
# that contract. Rebuild it from the per-section concat lists if wanted.

def synth_clip(clip):
    """Synthesize one clip's speech to a normalized mono wav, cached by segment ID."""
    wav = f"{CACHE}/{clip['id']}.wav"
    if not os.path.exists(wav):
        print(f">> synth {clip['id']}: {clip['speech'][:50]!r}")
        run(["kokoro-tts-tool","synthesize","--stdin","--output",wav,"--voice",VOICE],
            input=clip["speech"] + "\n")
        norm = wav + ".n.wav"
        run(["ffmpeg","-y","-i",wav,"-ar",str(SR),"-ac","1","-c:a","pcm_s16le", norm])
        os.replace(norm, wav)
    return wav

def main():
    # The reader bundle's build/ folder is the contract: segments.json comes in,
    # timing.json + per-section audio land beside it (so audio → <bundle>/build/audio/).
    seg_path = os.environ.get("SEG_JSON",
        "../../docs/reader/non-fiction/essays-and-criticism/the-great-sin/build/segments.en-1905.json")
    out_dir   = os.path.dirname(os.path.abspath(seg_path))   # the bundle's build/ dir
    audio_dir = f"{out_dir}/audio"
    timing_path = f"{out_dir}/timing.{json.load(open(seg_path, encoding='utf-8'))['version']}.json"

    seg = json.load(open(seg_path, encoding="utf-8"))
    clips = iter_clips(seg)
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # 1) synth every clip so durations are known, then compute the timeline
    for c in clips:
        synth_clip(c)
    timing = build_timeline(clips, duration_of=lambda cid: dur(f"{CACHE}/{cid}.wav"))

    # 2) per-section mastered audio: concat clip wavs + their gap silences
    sil = {}
    for g in {SENT_GAP, PARA_GAP, CHAP_GAP}:
        sil[g] = f"{CACHE}/_sil_{int(g*1000)}.wav"; make_sil(sil[g], g)

    timing["audio"] = {}
    by_section = {}
    for c in clips:
        by_section.setdefault(c["section"], []).append(c)

    for sec_id, sec_clips in by_section.items():
        listfile = f"{CACHE}/_concat_{sec_id}.txt"
        with open(listfile, "w") as f:
            for c in sec_clips:
                f.write(f"file '{os.path.abspath(CACHE)}/{c['id']}.wav'\n")
                if c["gap_after"] > 0:
                    f.write(f"file '{os.path.abspath(sil[c['gap_after']])}'\n")
        out_audio = f"{audio_dir}/{seg['work']}.{sec_id}.m4a"
        run(["ffmpeg","-y","-f","concat","-safe","0","-i",listfile,
             "-af",MASTER,"-ar","44100","-c:a","aac","-b:a",BITRATE,
             "-movflags","+faststart", out_audio])
        timing["audio"][sec_id] = f"audio/{seg['work']}.{sec_id}.m4a"

    json.dump(timing, open(timing_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f">> wrote {timing_path} ({len(timing['clips'])} clips, {len(timing['audio'])} sections)")

if __name__ == "__main__":
    main()
