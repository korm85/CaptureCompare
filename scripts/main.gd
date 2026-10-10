extends Node2D
## Top-level state machine: EGG -> REVEAL -> DECORATE -> (New Egg) -> EGG.

enum State { EGG, REVEAL, DECORATE }

const EGG_SCENE := preload("res://scenes/egg.tscn")

var state := State.EGG
var egg: Egg


func _ready() -> void:
	egg = EGG_SCENE.instantiate() as Egg
	add_child(egg)
	egg.hatched.connect(_on_egg_hatched)
	_start_egg()


func _start_egg() -> void:
	state = State.EGG
	egg.reset()
	egg.set_active(true)


func _on_egg_hatched() -> void:
	# Reveal and decorate come in later milestones; for now, start a new egg.
	state = State.REVEAL
	egg.set_active(false)
	await get_tree().create_timer(1.5).timeout
	_start_egg()
