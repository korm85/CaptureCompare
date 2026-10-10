class_name Decorate
extends Node2D
## Decorate screen: reveal a toy, then drag clothes and stickers onto it.
## Input goes through press(), drag() and release() so the smoke test can drive them.

signal ready_to_decorate
signal new_egg_requested

const Content := preload("res://scripts/data.gd")
const ITEM_SCENE := preload("res://scenes/item.tscn")
const EGG_POS := Vector2(640, 340)
const TOY_POS := Vector2(400, 360)
const TOY_SCALE := 0.9
const SNAP_DISTANCE := 120.0
const SHELF_X := 856.0
const SHELF_COLUMNS := [926.0, 1066.0, 1206.0]
const SHELF_ROWS := [170.0, 318.0, 466.0]
const TAB_Y := 60.0
const TABS := ["clothes", "sticker", "background"]
const LIFT := Vector2(0, -80)  # dragged copies sit above the fingertip so the kid can see them
const NEW_EGG_CENTER := Vector2(1190, 620)
const NEW_EGG_SIZE := 160.0
const TRASH_CENTER := Vector2(120, 620)
const TRASH_RADIUS := 80.0

var toy_name := ""
var ready_to_play := false
var shelf_items: Array[DecorItem] = []
var dragging: DecorItem = null
var drag_offset := Vector2.ZERO
var placed_slots := {}  # anchor name -> DecorItem wearing it
var _pointer := Pointer.new()

@onready var toy: Sprite2D = $Toy
@onready var backdrop: Sprite2D = $Backdrop
@onready var tab_highlight: ColorRect = $TabHighlight
@onready var new_egg_icon: Sprite2D = $NewEgg
@onready var trash_icon: Sprite2D = $Trash


func _ready() -> void:
	new_egg_icon.texture = load("res://assets/art/egg_1.png")
	new_egg_icon.scale = Vector2.ONE * NEW_EGG_SIZE / 512.0
	new_egg_icon.position = NEW_EGG_CENTER
	trash_icon.texture = load("res://assets/art/trash.png")
	trash_icon.scale = Vector2.ONE * TRASH_RADIUS * 2.0 / 512.0
	trash_icon.position = TRASH_CENTER
	_build_tab_icons()
	_apply_background("sky")
	_show_tab("clothes")


func start_reveal(id: String) -> void:
	toy_name = id
	toy.texture = load("res://assets/art/%s.png" % id)
	for anchor in Content.ANCHORS:
		toy.get_node(anchor.capitalize()).position = Content.ANCHORS[anchor]
	toy.position = EGG_POS
	toy.scale = Vector2.ONE * 0.2
	toy.visible = true
	_bounce_in()


func _unhandled_input(event: InputEvent) -> void:
	var result := _pointer.handle(event)
	match result[0]:
		Pointer.PRESS:
			press(result[1])
		Pointer.DRAG:
			drag(result[1])
		Pointer.RELEASE:
			release(result[1])


func press(pos: Vector2) -> void:
	if not ready_to_play:
		return
	for i in TABS.size():
		if _tab_rect(i).has_point(pos):
			_show_tab(TABS[i])
			return
	if Rect2(NEW_EGG_CENTER - Vector2.ONE * NEW_EGG_SIZE / 2.0, Vector2.ONE * NEW_EGG_SIZE).has_point(pos):
		new_egg_requested.emit()
		return
	for item in shelf_items:
		if item.hit_rect().has_point(pos):
			_pick_from_shelf(item, pos)
			return
	var children := get_children()
	children.reverse()
	for child in children:
		if child is DecorItem and not child.on_shelf and child.hit_rect().has_point(pos):
			dragging = child
			drag_offset = pos - child.global_position
			_sfx("boop")
			return


func drag(pos: Vector2) -> void:
	if dragging:
		dragging.global_position = pos - drag_offset


func release(pos: Vector2) -> void:
	if dragging == null:
		return
	var item := dragging
	dragging = null
	if _in_trash(pos):
		_remove(item)
	elif item.kind == "clothes":
		_drop_clothes(item)
	elif item.kind == "sticker":
		if pos.x >= SHELF_X:
			_remove(item)
		else:
			_celebrate(item)


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
	ready_to_play = true
	_voice("dress_me")
	ready_to_decorate.emit()


func _pick_from_shelf(item: DecorItem, pos: Vector2) -> void:
	if item.kind == "background":
		_apply_background(item.item_name)
		_sfx("boop")
		return
	var copy := _spawn(item.item_name, item.kind, false)
	copy.global_position = pos + LIFT
	dragging = copy
	drag_offset = -LIFT


func _drop_clothes(item: DecorItem) -> void:
	var anchor: Marker2D = toy.get_node(item.slot.capitalize())
	if item.global_position.distance_to(anchor.global_position) > SNAP_DISTANCE:
		_remove(item)
		return
	item.global_position = anchor.global_position
	var previous = placed_slots.get(item.slot)
	if previous and previous != item and is_instance_valid(previous):
		_remove(previous)
	placed_slots[item.slot] = item
	_sfx("cheer")
	item.celebrate()


func _remove(item: DecorItem) -> void:
	if placed_slots.get(item.slot) == item:
		placed_slots.erase(item.slot)
	_sfx("whoosh")
	var tween := create_tween()
	tween.tween_property(item, "scale", Vector2.ZERO, 0.15)
	tween.tween_callback(item.queue_free)


func _celebrate(item: DecorItem) -> void:
	_sfx("boop")
	item.celebrate()


func _in_trash(pos: Vector2) -> bool:
	return pos.distance_to(TRASH_CENTER) <= TRASH_RADIUS


func _build_tab_icons() -> void:
	var tab_art := ["hat_party", "star", ""]
	for i in TABS.size():
		var icon := Sprite2D.new()
		if tab_art[i] == "":
			icon.texture = DecorItem.gradient_texture(Content.BACKGROUNDS["sky"], 512, 512)
		else:
			icon.texture = load("res://assets/art/%s.png" % tab_art[i])
		icon.scale = Vector2.ONE * 56.0 / 512.0
		icon.position = _tab_rect(i).get_center()
		add_child(icon)


func _tab_rect(index: int) -> Rect2:
	return Rect2(Vector2(SHELF_COLUMNS[index] - 70, TAB_Y - 40), Vector2(140, 80))


func _show_tab(tab: String) -> void:
	tab_highlight.position = _tab_rect(TABS.find(tab)).position
	for item in shelf_items:
		item.queue_free()
	shelf_items.clear()
	var ids: Array
	if tab == "clothes":
		ids = Content.CLOTHES.keys()
	elif tab == "sticker":
		ids = Content.STICKERS
	else:
		ids = Content.BACKGROUNDS.keys()
	for i in ids.size():
		var row := i / 3
		if row >= SHELF_ROWS.size():
			break
		var item := _spawn(ids[i], tab, true)
		item.position = Vector2(SHELF_COLUMNS[i % 3], SHELF_ROWS[row])
		item.pop_in()
		shelf_items.append(item)


func _spawn(id: String, item_kind: String, shelf: bool) -> DecorItem:
	var item := ITEM_SCENE.instantiate() as DecorItem
	add_child(item)
	item.setup(id, item_kind, shelf, TOY_SCALE)
	return item


func _apply_background(id: String) -> void:
	backdrop.texture = DecorItem.gradient_texture(Content.BACKGROUNDS[id], 1280, 720)


func _sfx(sound: String) -> void:
	# Looked up at runtime so the script also compiles under --script and --check-only.
	var audio := get_node_or_null("/root/Audio")
	if audio:
		audio.play(sound)


func _voice(cue: String) -> float:
	var audio := get_node_or_null("/root/Audio")
	return audio.play_voice(cue) if audio else 0.0
