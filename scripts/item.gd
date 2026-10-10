class_name DecorItem
extends Node2D
## A clothing piece, sticker or background thumbnail. Shelf copies sit on the shelf,
## placed items sit on the toy.

const Content := preload("res://scripts/data.gd")
const SHELF_SIZE := 140.0  # touch target
const SHELF_ART := 118.0   # drawn size inside its tile
const STICKER_SCALE := 0.5

var item_name := ""
var kind := ""
var slot := ""
var on_shelf := false

@onready var sprite: Sprite2D = $Sprite


func setup(id: String, item_kind: String, shelf: bool, toy_scale: float) -> void:
	item_name = id
	kind = item_kind
	on_shelf = shelf
	slot = Content.CLOTHES.get(id, "")
	if kind == "background":
		sprite.texture = load("res://assets/art/swatch_%s.png" % id)
	else:
		sprite.texture = load("res://assets/art/%s.png" % id)
	if shelf:
		sprite.scale = Vector2.ONE * SHELF_ART / 512.0
	elif kind == "sticker":
		sprite.scale = Vector2.ONE * STICKER_SCALE
	else:
		sprite.scale = Vector2.ONE * toy_scale


func hit_rect() -> Rect2:
	var half := maxf(sprite.texture.get_width() * sprite.scale.x * 0.5, SHELF_SIZE * 0.5)
	return Rect2(global_position - Vector2.ONE * half, Vector2.ONE * half * 2.0)


func pop_in() -> void:
	scale = Vector2.ONE * 0.3
	create_tween().tween_property(self, "scale", Vector2.ONE, 0.3).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


func celebrate() -> void:
	var tween := create_tween()
	tween.tween_property(self, "scale", Vector2.ONE * 1.2, 0.1)
	tween.tween_property(self, "scale", Vector2.ONE, 0.15).set_trans(Tween.TRANS_BACK)
