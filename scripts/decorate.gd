class_name Decorate
extends Node2D
## Decorate screen. Reveals a toy with a bounce, then the child dresses it.

signal ready_to_decorate

const Content := preload("res://scripts/data.gd")
const EGG_POS := Vector2(640, 340)
const TOY_POS := Vector2(500, 360)
const TOY_SCALE := 0.9

var toy_name := ""

@onready var toy: Sprite2D = $Toy


func start_reveal(name: String) -> void:
	toy_name = name
	toy.texture = load("res://assets/art/%s.png" % name)
	for anchor in Content.ANCHORS:
		toy.get_node(anchor.capitalize()).position = Content.ANCHORS[anchor]
	toy.position = EGG_POS
	toy.scale = Vector2.ONE * 0.2
	toy.visible = true
	_bounce_in()


func _bounce_in() -> void:
	_sfx("jingle")
	var move := create_tween()
	move.tween_property(toy, "position", TOY_POS, 0.5).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	var squash := create_tween()
	squash.tween_property(toy, "scale", Vector2(TOY_SCALE * 1.3, TOY_SCALE * 0.7), 0.25).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	squash.tween_property(toy, "scale", Vector2(TOY_SCALE * 0.85, TOY_SCALE * 1.15), 0.12)
	squash.tween_property(toy, "scale", Vector2.ONE * TOY_SCALE, 0.12)
	await squash.finished
	_sfx("toy_" + toy_name)
	var voice_length := _voice("wow")
	await get_tree().create_timer(maxf(voice_length, 0.6)).timeout
	ready_to_decorate.emit()


func _sfx(sound: String) -> void:
	# Looked up at runtime so the script also compiles under --script and --check-only.
	var audio := get_node_or_null("/root/Audio")
	if audio:
		audio.play(sound)


func _voice(cue: String) -> float:
	var audio := get_node_or_null("/root/Audio")
	return audio.play_voice(cue) if audio else 0.0
