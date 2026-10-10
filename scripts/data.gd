extends RefCounted
## Game content lists. Adding a toy or item: drop a PNG in assets/art/ and add one line here.
## Loaded with preload() rather than as an autoload, so headless --script tests can compile the
## scripts that use it.

const TOYS := ["cat", "dog", "bunny", "dino", "unicorn", "bear", "duck"]
const CLOTHES := {
	"hat_party": "head", "bow_pink": "head", "glasses_round": "face",
	"scarf_red": "neck", "shirt_blue": "body", "crown_gold": "head",
}
const STICKERS := ["star", "heart", "flower", "rainbow", "sun", "moon", "butterfly", "ice_cream"]
## Backgrounds: assets/art/bg_<name>.png is the full scene, swatch_<name>.png the shelf thumbnail.
const BACKGROUNDS := ["sky", "mint", "peach", "lilac"]
## Where each toy's head, face, neck and body sit, as offsets in texture pixels from the toy's
## centre. Each toy is drawn differently, so each needs its own set.
const TOY_ANCHORS := {
	"cat": {"head": Vector2(0, -158), "face": Vector2(0, -44), "neck": Vector2(0, 60), "body": Vector2(0, 116)},
	"dog": {"head": Vector2(0, -156), "face": Vector2(0, -42), "neck": Vector2(0, 62), "body": Vector2(0, 116)},
	"bunny": {"head": Vector2(0, -128), "face": Vector2(0, -20), "neck": Vector2(0, 58), "body": Vector2(0, 118)},
	"dino": {"head": Vector2(106, -136), "face": Vector2(132, -48), "neck": Vector2(74, 64), "body": Vector2(-20, 110)},
	"unicorn": {"head": Vector2(28, -136), "face": Vector2(25, -26), "neck": Vector2(28, 64), "body": Vector2(0, 120)},
	"bear": {"head": Vector2(0, -152), "face": Vector2(0, -46), "neck": Vector2(0, 68), "body": Vector2(0, 116)},
	"duck": {"head": Vector2(0, -166), "face": Vector2(2, -80), "neck": Vector2(0, 44), "body": Vector2(0, 110)},
}
