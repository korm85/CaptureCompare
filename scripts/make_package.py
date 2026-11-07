"""Bundle code, input photos, results and findings into one shareable zip.

    python scripts/make_package.py --out DepthCapture_package.zip

Expects results/final/ from regenerating every run with the current code
(set1_ref_frame_N/, set2_ref_light_N/, synthetic/, *.log) and the injected-glare
evaluation logs in results/final/injected_*.txt.
NOTE: the package contains the input face photos; share it only with people
who should see them.
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FINAL = os.path.join(ROOT, "results", "final")


def _read_report(d):
    with open(os.path.join(d, "report.json")) as f:
        return json.load(f)


def _stack_compare(dirs, out_path, width=1400, cols=(0, 1)):
    rows = []
    for d in dirs:
        c = cv2.imread(os.path.join(d, "compare.jpg"))
        w = c.shape[1] // 3
        t = np.hstack([c[:, i * w:(i + 1) * w] for i in cols])
        rows.append(cv2.resize(t, (width, int(t.shape[0] * width / t.shape[1]))))
    cv2.imwrite(out_path, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])


def _stack_masks(dirs, out_path, width=1500):
    rows = []
    for d in dirs:
        m = cv2.imread(os.path.join(d, "masks.jpg"))
        rows.append(cv2.resize(m, (width, int(m.shape[0] * width / m.shape[1]))))
    cv2.imwrite(out_path, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])


def _thumbs(paths, out_path, h=360):
    ims = []
    for p in paths:
        im = cv2.imread(p)
        ims.append(cv2.resize(im, (int(im.shape[1] * h / im.shape[0]), h)))
    cv2.imwrite(out_path, np.hstack(ims), [cv2.IMWRITE_JPEG_QUALITY, 88])


def _table(headers, rows):
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def run_rows(dirs):
    rows = []
    for d in dirs:
        r = _read_report(d)
        s = r["stats"]
        used = [v["file"] for v in r["views"] if v["ok"]]
        rows.append([
            html.escape(r["reference"]),
            f'{len(used)} of {len(r["views"])}' + (f' <span class="m">({", ".join(map(html.escape, used))})</span>' if used else ""),
            f'{s.get("holdout_psnr_db", "–")} dB' if s.get("holdout_psnr_db") else "–",
            f'{s["glare_mask_px"]:,}',
            f'{s["filled_from_other_views_px"]:,} / {s["filled_single_image_px"]:,}',
            f'{100 * s["filled_from_other_views_px"] / max(s["glare_mask_px"], 1):.0f} %',
        ])
    return rows


CSS = """
:root{--bg:#fbfaf8;--fg:#1d1c1a;--mut:#6b6862;--card:#fff;--line:#e4e1db;--acc:#2f6fdb;--good:#1f8a4c;--warn:#b26b00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141413;--fg:#eceae6;--mut:#a29f98;--card:#1d1d1b;--line:#33322f;--acc:#7aa7ff;--good:#5cc98b;--warn:#f0b35a}}
:root[data-theme="dark"]{--bg:#141413;--fg:#eceae6;--mut:#a29f98;--card:#1d1d1b;--line:#33322f;--acc:#7aa7ff;--good:#5cc98b;--warn:#f0b35a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1060px;margin:0 auto;padding:32px 16px 80px}h1{font-size:30px;margin:0 0 6px}h2{font-size:21px;margin:44px 0 10px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:17px;margin:26px 0 8px}p,li{max-width:76ch}.lead{color:var(--mut);font-size:17px;margin:0 0 20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.card b{display:block;font-size:24px;margin-bottom:2px}.card span{color:var(--mut);font-size:14px}
.tw{overflow-x:auto;margin:10px 0}table{border-collapse:collapse;width:100%;font-size:14.5px;background:var(--card)}th,td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}th{background:color-mix(in srgb,var(--line) 45%,transparent)}
.m{color:var(--mut);font-size:13px}figure{margin:14px 0}figure img{width:100%;height:auto;border-radius:8px;border:1px solid var(--line);display:block}figcaption{color:var(--mut);font-size:14px;margin-top:6px}
code{background:color-mix(in srgb,var(--line) 55%,transparent);padding:1px 5px;border-radius:4px;font-size:14px}pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow-x:auto;font-size:13.5px}
.note{border-left:4px solid var(--warn);background:var(--card);padding:10px 14px;border-radius:6px;margin:14px 0}.ok{color:var(--good);font-weight:600}a{color:var(--acc)}
"""


def build_html(ctx):
    s1, s2 = ctx["set1_rows"], ctx["set2_rows"]
    inj = ctx["injected"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DepthCapture findings</title><style>{CSS}</style></head><body><main>
<h1>DepthCapture: removing wet-teeth reflections</h1>
<p class="lead">Findings, data and code from a proof of concept that removes specular reflections from photos of teeth, using one or several photos of the same smile. Generated {html.escape(ctx["date"])} from commit <code>{html.escape(ctx["commit"])}</code>.</p>

<div class="note"><b>Privacy:</b> this package contains the original face photos (in <code>data/</code> and in the result images). Share it only with people who should see them.</div>

<div class="cards">
<div class="card"><b>12 → 27 dB</b><span>artificial glints on real photos, removed from a single photo (set 1)</span></div>
<div class="card"><b>{inj["s2_single"]} → {inj["s2_multi"]} dB</b><span>one photo vs all 5 light-moved photos (set 2)</span></div>
<div class="card"><b>~12 % → ~50 %</b><span>share of glare filled with real pixels from other photos: camera moved vs light moved</span></div>
<div class="card"><b>35 dB</b><span>surrounding clean enamel after editing, i.e. practically untouched</span></div>
</div>

<h2>1. Verdict</h2>
<ul>
<li><b>Sharp glints are removed reliably</b>, from a single photo or several, without damaging the teeth.</li>
<li><b>Moving the light between frontal shots works better than moving the camera.</b> With a fixed light (window), the shine sits on the same part of the tooth in every frontal shot, and profile shots can't be aligned to a frontal one. With the light moved, the reflection moves while the tooth stays, so about half the glare can be replaced with real enamel from another photo.</li>
<li><b>Now limited by alignment</b> (hand-held, slight zoom and pose changes). The next gain would come from a phone stand, fixed zoom and the same bite in every shot. Cross-polarised lighting would remove the reflections optically in one shot.</li>
<li>The neural depth model (Depth Anything V2) turned out to be unnecessary: it neither detects nor removes reflections.</li>
</ul>

<h2>2. What the pipeline does</h2>
<h3>What counts as a reflection</h3>
<p>Inside the teeth area (MediaPipe face mesh, or an enamel-colour fallback for close-ups), a pixel is a reflection when it is:</p>
<ul><li>brighter than its neighbourhood at two scales (glints are about 5–60 px wide at 1024 px);</li>
<li>brighter than the <i>local</i> clean enamel by more than 0.05 (0–1 scale), so teeth in shadow are judged fairly;</li>
<li>nearly colourless (saturation below 0.15). A reflection has the light's colour, white; enamel, gums and stains don't. Clipped pixels always count.</li></ul>
<p>With several photos, a pixel is also a reflection if it is clearly brighter than the same spot in the other photos and those agree with each other. Bright regions larger than a glint are treated as lit enamel, and only their strong core is kept.</p>
<h3>What colour replaces it</h3>
<ol><li><b>The real colour from other photos</b>, where another photo saw that spot without glare. It is aligned (EfficientLoFTR, then homography, dense field and optical flow), corrected for exposure and for that photo's different shading, and used only if it is darker, looks like enamel there, and isn't on a strong edge.</li>
<li><b>Otherwise, an estimate from the same photo</b>: the average colour of the clean, bright enamel around the glint, plus 35 % of the original fine texture, never brighter than the original.</li>
<li><b>Two safety rules:</b> replacement strength follows the amount of added light (strong glints are fully replaced, faint ones barely), and the result can never be darker than the clean enamel nearby, because a reflection only ever adds light. The second rule removed the dark marks earlier versions introduced.</li></ol>

<h2>3. Data</h2>
<figure><img src="images/inputs_set1.jpg" alt="Set 1 input photos"><figcaption>Set 1: 6 photos, camera moved around the smile (front and both sides), fixed window light.</figcaption></figure>
<figure><img src="images/inputs_set2.jpg" alt="Set 2 input photos"><figcaption>Set 2: 5 roughly frontal photos, light source moved between shots.</figcaption></figure>

<h2>4. Results on the light-moved photos (set 2)</h2>
<figure><img src="images/set2_before_after.jpg" alt="Set 2 before and after"><figcaption>Before | after, each photo used once as the reference (light_1 … light_5, top to bottom).</figcaption></figure>
<figure><img src="images/set2_masks.jpg" alt="Set 2 reflection masks"><figcaption>Reflection masks only, photos unedited. Red: found in that photo. Blue: added because the other photos are darker there. Yellow outline: large bright area deliberately left alone. Right: final mask.</figcaption></figure>
{_table(["Reference", "Other photos used", "Fusion hold-out", "Glare px", "From other photos / single-photo estimate", "Real-pixel share"], s2)}
<p class="m">Hold-out: on clean enamel of the reference, how closely the other aligned photos reproduce it. That is the expected accuracy of a borrowed pixel.</p>

<h2>5. Results on the camera-moved photos (set 1)</h2>
<figure><img src="images/set1_before_after.jpg" alt="Set 1 before and after"><figcaption>Before | after with frame_3, frame_4 and frame_5 as the reference.</figcaption></figure>
<figure><img src="images/set1_masks.jpg" alt="Set 1 reflection masks"><figcaption>Reflection masks for set 1, photos unedited.</figcaption></figure>
{_table(["Reference", "Other photos used", "Fusion hold-out", "Glare px", "From other photos / single-photo estimate", "Real-pixel share"], s1)}
<p>The side profiles can't be warped onto a frontal reference (they show different tooth surfaces), so the pipeline rejects them automatically.</p>

<h2>6. Accuracy with ground truth</h2>
<p>Real photos have no "true" glare-free version, so artificial glints shaped like real ones (4–25 px, soft, some clipped) were painted onto clean enamel. The pipeline then had to restore the original photo. Scores are <b>PSNR</b>, a standard image-accuracy measure: 10·log10(1/mean squared error), pixels on a 0–1 scale. Higher is better, +6 dB means half the typical pixel error, and it is unrelated to sound.</p>
{_table(["Test", "With glints", "After removal", "Surrounding enamel", "Filled from other photos"], [
    ["Set 1, single photo (frames 3–5, 3 layouts)", f'{inj["s1_before"]} dB', f'<span class="ok">{inj["s1_single"]} dB</span>', f'{inj["s1_ring"]} dB', "0 %"],
    ["Set 2, photo alone (each photo, 2 layouts)", f'{inj["s2_before"]} dB', f'{inj["s2_single"]} dB', f'{inj["s2_ring_single"]} dB', "0 %"],
    ["Set 2, all 5 light-moved photos", f'{inj["s2_before"]} dB', f'<span class="ok">{inj["s2_multi"]} dB</span>', f'{inj["s2_ring_multi"]} dB', f'{inj["s2_views"]} %'],
])}
<p>Rough feel: 12 dB ≈ 25 % typical error, 22 dB ≈ 8 %, 27 dB ≈ 4.5 %, 35 dB under 2 %.</p>

<h3>Synthetic sanity check</h3>
<p>A rendered glossy dental arch with known ground truth is kept only as a sanity check: its fake highlights are long streaks over strongly shaded fake teeth, which don't resemble real wet glare. Output: <code>results/synthetic/</code>.</p>
<pre>{html.escape(ctx["synthetic_table"])}</pre>

<h2>7. Limits</h2>
<ul><li>Where no photo saw a spot clean, the fill is an estimate from the surrounding enamel, not the true surface.</li>
<li>The glariest reference (light_2) improves least. Pick the least shiny sharp photo as the reference; automatic selection does this.</li>
<li>Blue mask specks along lips, gums and edges are partly false alarms from slight misalignment.</li>
<li>Overexposed areas, where enamel itself clips to white, can't be recovered.</li></ul>

<h2>8. How to capture next time</h2>
<ol><li>Phone on a stand, same zoom, same bite in every shot.</li><li>Small light 20–30 cm away, moved left, right, up, down and centre between shots. Dim room light.</li><li>Fixed exposure if the camera app allows it.</li><li>Best of all: cross-polarised light (polariser on the light, crossed polariser on the lens).</li></ol>

<h2>9. Reproduce</h2>
<pre>cd code
pip install -r requirements-depthcapture.txt
python -m pytest -q tests
python scripts/run_pipeline.py ../data/smile_set2/*.jpg --reference 4 --out out_ref5      # edit
python scripts/run_pipeline.py ../data/smile_set2/*.jpg --reference 4 --masks-only --out m # masks only
python scripts/eval_injected.py ../data/smile_set2/*.jpg --multi                          # accuracy</pre>
<p>Contents: <code>code/</code> (source, tests, docs), <code>data/</code> (input photos), <code>results/</code> (every run: output, masks, compare image, JSON report), <code>logs/</code> (evaluation output), <code>images/</code> (figures in this page). The detailed write-up is <code>code/docs/DepthCapture.md</code>.</p>
</main></body></html>"""


def parse_injected(path_single_set1, path_set2):
    def grab(txt, key, which=0):
        import re
        vals = re.findall(key, txt)
        return vals[which] if vals else "–"
    t1 = open(path_single_set1).read()
    t2 = open(path_set2).read()
    out = {
        "s1_before": grab(t1, r"before: ([\d.]+) dB"),
        "s1_single": grab(t1, r"single: after ([\d.]+) dB"),
        "s1_ring": grab(t1, r"single: after [\d.]+ dB \| surrounding enamel ([\d.]+) dB"),
        "s2_before": grab(t2, r"before: ([\d.]+) dB"),
        "s2_single": grab(t2, r"single: after ([\d.]+) dB"),
        "s2_ring_single": grab(t2, r"single: after [\d.]+ dB \| surrounding enamel ([\d.]+) dB"),
        "s2_multi": grab(t2, r"multi : after ([\d.]+) dB"),
        "s2_ring_multi": grab(t2, r"multi : after [\d.]+ dB \| surrounding enamel ([\d.]+) dB"),
        "s2_views": grab(t2, r"multi : .*filled from other photos (\d+)%"),
    }
    for k in out:
        if out[k] != "–" and "." in out[k]:
            out[k] = f"{float(out[k]):.1f}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "DepthCapture_package.zip"))
    args = ap.parse_args()
    stage = os.path.join(ROOT, "package_build", "DepthCapture_package")
    shutil.rmtree(os.path.dirname(stage), ignore_errors=True)
    os.makedirs(os.path.join(stage, "images"))

    # code at the committed HEAD (no photos: they are git-ignored)
    commit = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], text=True).strip()
    code_dir = os.path.join(stage, "code")
    os.makedirs(code_dir)
    arc = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", code_dir], input=arc, check=True)

    shutil.copytree(os.path.join(ROOT, "data"), os.path.join(stage, "data"))
    res_dir = os.path.join(stage, "results")
    os.makedirs(res_dir)
    for d in sorted(glob.glob(os.path.join(FINAL, "set*_ref_*"))):
        if os.path.isdir(d):
            shutil.copytree(d, os.path.join(res_dir, os.path.basename(d)))
    if os.path.isdir(os.path.join(FINAL, "synthetic")):
        shutil.copytree(os.path.join(FINAL, "synthetic"), os.path.join(res_dir, "synthetic"))
    for sub in ["injected", "injected_set2"]:
        src = os.path.join(ROOT, "results", sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(res_dir, sub))
    logs = os.path.join(stage, "logs")
    os.makedirs(logs)
    for p in glob.glob(os.path.join(FINAL, "*.log")) + glob.glob(os.path.join(FINAL, "*.txt")):
        shutil.copy(p, logs)

    s1 = sorted(glob.glob(os.path.join(FINAL, "set1_ref_frame_*/")))
    s2 = sorted(glob.glob(os.path.join(FINAL, "set2_ref_light_*/")))
    img = os.path.join(stage, "images")
    _stack_compare(s1, os.path.join(img, "set1_before_after.jpg"))
    _stack_compare(s2, os.path.join(img, "set2_before_after.jpg"))
    _stack_masks(s1, os.path.join(img, "set1_masks.jpg"))
    _stack_masks(s2, os.path.join(img, "set2_masks.jpg"))
    _thumbs(sorted(glob.glob(os.path.join(ROOT, "data", "smile_set1", "*.jpg"))), os.path.join(img, "inputs_set1.jpg"))
    _thumbs(sorted(glob.glob(os.path.join(ROOT, "data", "smile_set2", "*.jpg"))), os.path.join(img, "inputs_set2.jpg"))

    synth = open(os.path.join(FINAL, "synthetic_eval.txt")).read().strip() if os.path.exists(
        os.path.join(FINAL, "synthetic_eval.txt")) else "(not run)"
    import datetime

    ctx = {
        "date": datetime.date.today().isoformat(), "commit": commit,
        "set1_rows": run_rows(s1), "set2_rows": run_rows(s2),
        "injected": parse_injected(os.path.join(FINAL, "injected_set1.txt"), os.path.join(FINAL, "injected_set2.txt")),
        "synthetic_table": synth,
    }
    with open(os.path.join(stage, "index.html"), "w") as f:
        f.write(build_html(ctx))
    with open(os.path.join(stage, "README.txt"), "w") as f:
        f.write("DepthCapture package\n\nOpen index.html in a browser for the findings.\n"
                "code/ = source (see code/docs/DepthCapture.md), data/ = input photos (contain a face),\n"
                "results/ = every run's outputs, masks and JSON reports, logs/ = evaluation output.\n")
    base = os.path.splitext(args.out)[0]
    shutil.make_archive(base, "zip", os.path.dirname(stage), "DepthCapture_package")
    print(base + ".zip", f"{os.path.getsize(base + '.zip') / 1e6:.1f} MB")


if __name__ == "__main__":
    sys.exit(main())
