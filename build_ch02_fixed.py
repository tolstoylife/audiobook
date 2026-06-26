#!/usr/bin/env python3
"""
ch02 flow-fix test build. Three text/config fixes over chapters_flow/ch02.txt:
  1. respell verb "live" -> "liv"  (Kokoro mis-said /laɪv/ for /lɪv/)
  2. pause between every SENTENCE, not just paragraphs (Johan: "longer pause")
  3. join the two paragraphs that break mid-sentence (~2:12 and ~2:33)
Output: ch02_flow_fixed.wav  (raw 24k mono, like ch02_flow.wav, for a fair A/B)

Usage:  python3 build_ch02_fixed.py --dry     # print sentence split only
        python3 build_ch02_fixed.py           # generate
"""
import subprocess, os, re, sys

VOICE    = "bm_daniel"
METHOD   = "synthesize"  # ponytail: was 'infinite' — its streaming step mangled long-sentence endings; 'synthesize' is clean
SENT_GAP = 0.45   # ponytail: tune to taste — pause between sentences in a paragraph
PARA_GAP = 0.85   # ponytail: Johan wanted longer para gaps (most paragraphs end on a George quote)
SR       = 24000
OUT      = f"ch02_{VOICE}_{METHOD}.wav"   # keyed by voice+method so the cache can't serve stale audio
CACHE    = f"wav_{VOICE}_{METHOD}"
DRY      = "--dry" in sys.argv

def split_paras(path):
    return [p.strip() for p in re.split(r"\n\s*\n", open(path).read()) if p.strip()]

def split_sents(text):
    text = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text)            # protect $1.40
    parts = re.split(r'(?<=[.!?"])\s+(?=["“(A-Z])', text)        # end-punct (+quote) then Cap/quote/paren
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]

# --- fix 3: join mid-sentence paragraph breaks (join next-index into the given one)
paras = split_paras("chapters_flow/ch02.txt")
JOINS = {3: 4, 6: 7}
merged, i = [], 0
while i < len(paras):
    if i in JOINS:
        merged.append(paras[i] + " " + paras[JOINS[i]]); i = JOINS[i] + 1
    else:
        merged.append(paras[i]); i += 1

# --- fix 1: live -> liv (whole word; "lives"/"lived"/"living" untouched)
merged = [re.sub(r"\blive\b", "liv", p) for p in merged]

# build sentence list with the gap that should follow each
units = []  # (text, gap_after)
for pi, p in enumerate(merged):
    sents = split_sents(p)
    for si, s in enumerate(sents):
        last_in_para = (si == len(sents) - 1)
        gap = PARA_GAP if last_in_para else SENT_GAP
        units.append((s, gap))
units[-1] = (units[-1][0], 0.0)  # no trailing gap

if DRY:
    for n, (s, g) in enumerate(units):
        print(f"[{n:02d}] (gap {g}) {s}")
    print(f"\n{len(merged)} paragraphs -> {len(units)} sentences")
    sys.exit(0)

os.makedirs(CACHE, exist_ok=True)
def run(cmd, **kw): subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
def make_sil(path, sec):
    if not os.path.exists(path):
        run(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono","-t",str(sec),"-c:a","pcm_s16le",path])

concat = open(f"{CACHE}/concat.txt", "w")
for n, (s, g) in enumerate(units):
    wav = f"{CACHE}/s{n:03d}.wav"
    if not os.path.exists(wav):
        print(f">> sentence {n+1}/{len(units)}")
        run(["kokoro-tts-tool","synthesize","--stdin","--output",wav,"--voice",VOICE], input=s + "\n")
        norm = wav + ".n.wav"
        run(["ffmpeg","-y","-i",wav,"-ar",str(SR),"-ac","1","-c:a","pcm_s16le",norm]); os.replace(norm, wav)
    concat.write(f"file '{os.path.abspath(wav)}'\n")
    if g > 0:
        sil = f"{CACHE}/_sil_{int(g*1000)}.wav"; make_sil(sil, g)
        concat.write(f"file '{os.path.abspath(sil)}'\n")
concat.close()
run(["ffmpeg","-y","-f","concat","-safe","0","-i",f"{CACHE}/concat.txt","-c","copy",OUT])
print(f">> Done: {OUT}")
