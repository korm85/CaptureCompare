extends Node2D
## Top-level state machine: EGG -> REVEAL -> DECORATE -> (New Egg) -> EGG.

enum State { EGG, REVEAL, DECORATE }

const EGG_SCENE := preload("res://scenes/egg.tscn")
const DECORATE_SCENE := preload("res://scenes/decorate.tscn")
const Content := preload("res://scripts/data.gd")

var state := State.EGG
var egg: Egg
var decorate: Decorate


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
	state = State.REVEAL
	egg.set_active(false)
	decorate = DECORATE_SCENE.instantiate() as Decorate
	add_child(decorate)
	decorate.ready_to_decorate.connect(_on_ready_to_decorate)
	decorate.new_egg_requested.connect(_on_new_egg_requested)
	decorate.start_reveal(Content.TOYS.pick_random())


func _on_ready_to_decorate() -> void:
	state = State.DECORATE


func _on_new_egg_requested() -> void:
	decorate.queue_free()
	decorate = null
	_start_egg()
