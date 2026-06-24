#!/usr/bin/env python3
"""
flow_preprocess.py — reshape punctuation so a small TTS model phrases better.

Reads chapters/ch*.txt and writes chapters_flow/ch*.txt.
Conservative by default. The aggressive long-sentence split is opt-in.

  python3 flow_preprocess.py                 # semicolon + dash + ellipsis fixes
  python3 flow_preprocess.py --split-long 45 # also split sentences > 45 words

Rationale:
- A clause-joining semicolon -> period: the model gives a real terminal
  cadence instead of a flat mid-sentence blip.
- A semicolon before a coordinating conjunction (and/but/or...) -> comma:
  that's a lighter join, so a light pause fits.
- Em dashes get spaces so the model treats them as a beat.
- Ellipses normalized so they aren't read as three separate stops.
"""
import re, os, sys, glob

CONJ = r"(?:and|but|or|nor|yet|so|for)\b"

def fix_semicolons(t):
    # "; and" -> ", and"   (light join)
    t = re.sub(rf";\s+({CONJ})", r", \1", t)
    # remaining "; word" -> ". Word"  (full stop + capitalize)
    def cap(m): return ". " + m.group(1).upper()
    t = re.sub(r";\s+([a-zA-Z])", cap, t)
    return t

def fix_dashes(t):
    t = t.replace("—", " — ")          # ensure em dash is a spoken beat
    t = re.sub(r"\s{2,}", " ", t)
    t = t.replace(" — ", " — ")
    return t

def fix_ellipsis(t):
    t = t.replace("...", "…")          # single glyph, one trailing pause
    t = re.sub(r"\.\s*\.\s*\.", "…", t)
    return t

def split_long(t, maxwords):
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", t):
        words = sent.split()
        if len(words) <= maxwords:
            out.append(sent); continue
        # split at the comma nearest the midpoint
        commas = [i for i, w in enumerate(words) if w.endswith(",")]
        if not commas:
            out.append(sent); continue
        mid = len(words) // 2
        cut = min(commas, key=lambda i: abs(i - mid))
        left = " ".join(words[:cut+1]).rstrip(",") + "."
        right = " ".join(words[cut+1:])
        right = right[:1].upper() + right[1:]
        out.append(left); out.append(right)
    return " ".join(out)

def process(text, maxwords=None):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    done = []
    for p in paras:
        p = fix_ellipsis(p)
        p = fix_semicolons(p)
        p = fix_dashes(p)
        if maxwords:
            p = split_long(p, maxwords)
        done.append(p)
    return "\n\n".join(done) + "\n"

def main():
    maxwords = None
    if "--split-long" in sys.argv:
        maxwords = int(sys.argv[sys.argv.index("--split-long") + 1])
    os.makedirs("chapters_flow", exist_ok=True)
    for f in sorted(glob.glob("chapters/ch*.txt")):
        out = process(open(f).read(), maxwords)
        dst = os.path.join("chapters_flow", os.path.basename(f))
        open(dst, "w").write(out)
        print(f"  {f} -> {dst}")
    print("Done. Point build_audiobook.py at chapters_flow/ to A/B.")

if __name__ == "__main__":
    main()
