class_name Egg
extends Node2D
## One egg round: tap to crack it through four stages, then it splits open.

signal hatched

const STAGES := 4
const VARIANT_COUNT := 5
const BODY_SCALE := 0.9
const HIT_RECT := Rect2(-240, -250, 480, 500)
const HAMMER_REST := Vector2(170, -160)

var stage := 0
var variant := 0
var busy := false
var _wobble: Tween
var _squash: Tween
var _hammer_tween: Tween
var _split_tween: Tween

@onready var body: Sprite2D = $Body
@onready var crack: Sprite2D = $Crack
@onready var hammer: Sprite2D = $Hammer
@onready var half_left: Sprite2D = $HalfLeft
@onready var half_right: Sprite2D = $HalfRight
@onready var confetti: CPUParticles2D = $Confetti


func _ready() -> void:
	confetti.color_initial_ramp = _confetti_colors()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if HIT_RECT.has_point(to_local(event.position)):
			get_viewport().set_input_as_handled()
			hit()


func set_active(on: bool) -> void:
	set_process_unhandled_input(on)
	visible = on


func reset() -> void:
	for tween in [_wobble, _squash, _hammer_tween, _split_tween]:
		if tween and tween.is_valid():
			tween.kill()
	stage = 0
	busy = false
	variant = randi() % VARIANT_COUNT
	rotation = 0.0
	body.texture = load("res://assets/art/egg_%d.png" % variant)
	body.scale = Vector2.ONE * BODY_SCALE
	body.visible = true
	crack.visible = false
	hammer.visible = false
	half_left.visible = false
	half_right.visible = false
	half_left.modulate = Color.WHITE
	half_right.modulate = Color.WHITE
	confetti.emitting = false


func hit() -> void:
	if busy:
		return
	stage += 1
	_sfx("tok")
	_swing_hammer()
	_do_wobble()
	if stage < STAGES:
		crack.texture = load("res://assets/art/crack_%d.png" % stage)
		crack.visible = true
	else:
		_split()


func _swing_hammer() -> void:
	if _hammer_tween and _hammer_tween.is_valid():
		_hammer_tween.kill()
	hammer.visible = true
	hammer.position = HAMMER_REST
	hammer.rotation = -1.0
	_hammer_tween = create_tween()
	_hammer_tween.tween_property(hammer, "rotation", 0.3, 0.12)
	_hammer_tween.tween_property(hammer, "rotation", -1.0, 0.2)
	_hammer_tween.tween_callback(hammer.hide)


func _do_wobble() -> void:
	if _wobble and _wobble.is_valid():
		_wobble.kill()
	if _squash and _squash.is_valid():
		_squash.kill()
	_wobble = create_tween()
	_wobble.tween_property(self, "rotation", 0.1, 0.08)
	_wobble.tween_property(self, "rotation", -0.1, 0.12)
	_wobble.tween_property(self, "rotation", 0.0, 0.1)
	_squash = create_tween()
	_squash.tween_property(body, "scale", Vector2.ONE * BODY_SCALE * 1.08, 0.08)
	_squash.tween_property(body, "scale", Vector2.ONE * BODY_SCALE, 0.25).set_trans(Tween.TRANS_ELASTIC)


func _split() -> void:
	busy = true
	hammer.visible = false
	body.visible = false
	crack.visible = false
	var tex: Texture2D = load("res://assets/art/egg_%d.png" % variant)
	for half in [half_left, half_right]:
		half.texture = tex
		half.region_enabled = true
		half.visible = true
	half_left.region_rect = Rect2(0, 0, 256, 512)
	half_right.region_rect = Rect2(256, 0, 256, 512)
	half_left.position = Vector2(-128 * BODY_SCALE, 0)
	half_right.position = Vector2(128 * BODY_SCALE, 0)
	_sfx("pop")
	confetti.restart()
	_split_tween = create_tween().set_parallel(true)
	_split_tween.tween_property(half_left, "position", Vector2(-260, -140), 0.9).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_split_tween.tween_property(half_right, "position", Vector2(260, -140), 0.9).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_split_tween.tween_property(half_left, "rotation", -0.7, 0.9)
	_split_tween.tween_property(half_right, "rotation", 0.7, 0.9)
	_split_tween.tween_property(half_left, "modulate:a", 0.0, 0.5).set_delay(0.4)
	_split_tween.tween_property(half_right, "modulate:a", 0.0, 0.5).set_delay(0.4)
	await get_tree().create_timer(1.0).timeout
	if busy:
		hatched.emit()


func _sfx(sound: String) -> void:
	# Looked up at runtime so the script also compiles under --script and --check-only.
	var audio := get_node_or_null("/root/Audio")
	if audio:
		audio.play(sound)


func _confetti_colors() -> Gradient:
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.25, 0.5, 0.75, 1.0])
	gradient.colors = PackedColorArray([
		Color("ff6b8a"), Color("ffd166"), Color("06d6a0"), Color("3a86ff"), Color("c77dff"),
	])
	return gradient
