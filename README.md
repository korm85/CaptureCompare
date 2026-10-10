# Surprise Egg

A tap-only game for a four-year-old. Crack an egg, reveal a toy, dress it up, and start again.
No text, no losing, big touch targets, voice and sound feedback. Built with Godot 4.4 and exported to the Web.

## Run it

Open the project in the Godot 4.4 editor and press Play, or from the command line:

```bash
godot --path .          # opens the game window
```

## Checks

```bash
godot --headless --path . --import                                  # import assets (first run)
godot --headless --path . --quit                                    # loads main scene, surfaces script errors
godot --headless --path . --check-only --script res://scripts/egg.gd  # syntax check one script
godot --headless --path . --script res://tests/smoke.gd             # smoke test, exit 0 on pass
```

Any `SCRIPT ERROR` or `Parse Error` in the output is a failure.

## Export to Web

Export preset `Web` (single-threaded, so it runs on any static host) writes to `build/web/`:

```bash
mkdir -p build/web
godot --headless --path . --export-release "Web" build/web/index.html
```

Serve `build/web/` with any static server to try it, for example `python3 -m http.server 8000 -d build/web`,
then open `http://localhost:8000/` on a tablet or phone on the same network.

## Placeholder art and sound

`tools/make_placeholders.py` draws the art and generates the sounds. Re-run it from the project root:

```bash
pip install --break-system-packages pillow numpy
python3 tools/make_placeholders.py
```

Real art and sound can replace these files with the same names, with no code changes.

## Voice cues

Recorded voice clips go in `assets/voice/` as `.ogg`, `.wav` or `.mp3`. The game plays them by name:

| File | When it plays |
| --- | --- |
| `crack_it.ogg` | At the start of each egg |
| `wow.ogg` | When a toy is revealed |
| `dress_me.ogg` | When decorating starts |

Missing files are skipped silently, so the game works before any recording exists.

## How to add a toy or item

Content lives in `scripts/data.gd`.

**Add a toy** (for example, a frog):

1. Drop `assets/art/frog.png` (512x512, transparent background) in place.
2. Add `"frog"` to `TOYS`.
3. Optionally add `assets/sfx/toy_frog.wav` for its sound. Without it the toy is silent.

**Add a clothing item** (for example, a cap that sits on the head):

1. Drop `assets/art/cap_red.png` in place. Draw it centred on the canvas, with its attach point at the centre.
2. Add `"cap_red": "head"` to `CLOTHES`. The slot is `head`, `face`, `neck` or `body`.

**Add a sticker**:

1. Drop `assets/art/moon2.png` in place.
2. Add `"moon2"` to `STICKERS`.

Every toy needs the four anchors in `ANCHORS` (`head`, `face`, `neck`, `body`). They are offsets in texture pixels from the toy's centre, so one set works for every toy that is drawn to the same layout.

## Project layout

```
project.godot          engine settings, Audio autoload
export_presets.cfg     Web export preset
scenes/                main, egg, decorate, item
scripts/               main (state machine), egg, decorate, item, audio (autoload), data (content lists)
assets/art/            pictures
assets/sfx/            sound effects
assets/voice/          voice clips (optional, added by hand)
tools/                 make_placeholders.py
tests/smoke.gd         headless smoke test
```

## Controls

Everything is touch first. Godot maps touch to mouse, so one mouse code path covers tablets and desktops.

- **Egg:** tap to crack it. Four taps split it open.
- **Decorate:** drag from the shelf to make a copy. Clothes snap to their spot on the toy when dropped nearby.
  Stickers go anywhere. Drag a sticker onto the shelf or the trash can to remove it.
- **Tabs:** clothes, stickers, backgrounds.
- **New egg** (bottom right): starts a new round.
