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
## Toy anchor offsets in texture pixels, measured from the toy's centre.
const ANCHORS := {
	"head": Vector2(0, -156),
	"face": Vector2(0, -31),
	"neck": Vector2(0, 64),
	"body": Vector2(0, 134),
}
## Optional background swatches as [top, bottom] gradient colours.
const BACKGROUNDS := {
	"sky": [Color("9fd8ff"), Color("e8f7ff")],
	"mint": [Color("b8f2d8"), Color("f0fff8")],
	"peach": [Color("ffd2b0"), Color("fff4ec")],
	"lilac": [Color("d7c4ff"), Color("f7f0ff")],
}
