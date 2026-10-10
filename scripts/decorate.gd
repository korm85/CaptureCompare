class_name Decorate
extends Node2D
## Decorate screen: reveal a toy, then drag clothes and stickers onto it. Tap the toy to make it
## react. Input goes through the Pointer helper; the smoke test calls _unhandled_input directly.

signal ready_to_decorate
signal new_egg_requested

const Content := preload("res://scripts/data.gd")
const ITEM_SCENE := preload("res://scenes/item.tscn")
const EGG_POS := Vector2(640, 340)
const TOY_POS := Vector2(400, 360)
const TOY_SCALE := 0.9
const LIFT := Vector2(0, -80)  # dragged copies sit above the fingertip so the child can see them
const SNAP_DISTANCE := 120.0
const SNAP_HINT_DISTANCE := 220.0
const TOY_TAP_HALF := Vector2(200, 230)
const SHELF_X := 842.0
const SHELF_RECT := Rect2(842, 18, 424, 684)
const SHELF_COLUMNS := [926.0, 1066.0, 1206.0]
const SHELF_ROWS := [170.0, 318.0, 466.0]
const TILE_SIZE := 136.0
const TAB_Y := 60.0
const TAB_SIZE := Vector2(124, 68)
const TABS := ["clothes", "sticker", "background"]
const TAB_ART := ["hat_party", "star", "swatch_sky"]
const NEW_EGG_CENTER := Vector2(1190, 620)
const NEW_EGG_RADIUS := 80.0
const TRASH_CENTER := Vector2(120, 620)
const TRASH_RADIUS := 72.0
const MINT := Color("8ee3c8")
const CORAL := Color("ff8a9b")
const TRASH_BLUE := Color("9fb8d6")
const TRASH_RED := Color("ff9aa8")

var toy_name := ""
var ready_to_play := false
var shelf_tab := "clothes"
var shelf_items: Array[DecorItem] = []
var shelf_tiles: Array[Vector2] = []
var dragging: DecorItem = null
var drag_offset := Vector2.ZERO
var placed_slots := {}  # anchor name -> DecorItem wearing it
var _pointer := Pointer.new()
var _idle_tween: Tween
var _react_tween: Tween

@onready var toy: Sprite2D = $Toy
@onready var backdrop: Sprite2D = $Backdrop
@onready var new_egg_icon: Sprite2D = $NewEgg
@onready var trash_icon: Sprite2D = $Trash
@onready var burst: CPUParticles2D = $Burst


func _ready() -> void:
	burst.color_initial_ramp = Effects.sparkle_ramp()
	new_egg_icon.texture = load("res://assets/art/egg_1.png")
	new_egg_icon.scale = Vector2.ONE * 0.26
	new_egg_icon.position = NEW_EGG_CENTER
	trash_icon.texture = load("res://assets/art/trash.png")
	trash_icon.scale = Vector2.ONE * 0.26
	trash_icon.position = TRASH_CENTER
	_build_tab_icons()
	_apply_background("sky")
	_show_tab("clothes")


func _unhandled_input(event: InputEvent) -> void:
	var result := _pointer.handle(event)
	match result[0]:
		Pointer.PRESS:
			press(result[1])
		Pointer.DRAG:
			drag(result[1])
		Pointer.RELEASE:
			release(result[1])


func start_reveal(id: String) -> void:
	toy_name = id
	toy.texture = load("res://assets/art/%s.png" % id)
	var anchors: Dictionary = Content.TOY_ANCHORS[id]
	for anchor in anchors:
		toy.get_node(anchor.capitalize()).position = anchors[anchor]
	toy.position = EGG_POS
	toy.scale = Vector2.ONE * 0.2
	toy.visible = true
	_bounce_in()


func press(pos: Vector2) -> void:
	if not ready_to_play:
		return
	for i in TABS.size():
		if _tab_rect(i).has_point(pos):
			_show_tab(TABS[i])
			return
	if pos.distance_to(NEW_EGG_CENTER) <= NEW_EGG_RADIUS:
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
			child.scale = Vector2.ONE * 1.08
			_sfx("boop")
			queue_redraw()
			return
	if Rect2(toy.global_position - TOY_TAP_HALF, TOY_TAP_HALF * 2.0).has_point(pos):
		_react_toy()


func drag(pos: Vector2) -> void:
	if dragging:
		dragging.global_position = pos - drag_offset
		queue_redraw()


func release(pos: Vector2) -> void:
	if dragging == null:
		return
	var item := dragging
	dragging = null
	item.scale = Vector2.ONE
	queue_redraw()
	if _in_trash(pos):
		_remove(item)
	elif item.kind == "clothes":
		_drop_clothes(item)
	elif item.kind == "sticker":
		if pos.x >= SHELF_X:
			_remove(item)
		else:
			_celebrate(item)
			Effects.burst(burst, item.global_position, 0.5)


func _draw() -> void:
	draw_style_box(_style(Color(1, 1, 1, 0.8), 40, Color(0.35, 0.2, 0.45, 0.16), 24), SHELF_RECT)
	for i in TABS.size():
		var active: bool = TABS[i] == shelf_tab
		var fill := MINT if active else Color(1, 1, 1, 0.92)
		draw_style_box(_style(fill, 30, Color(0.3, 0.2, 0.4, 0.16 if active else 0.08), 10 if active else 5), _tab_rect(i))
	for centre in shelf_tiles:
		draw_style_box(_style(Color(1, 1, 1, 0.96), 30, Color(0.3, 0.2, 0.4, 0.12), 8),
			Rect2(centre - Vector2.ONE * TILE_SIZE / 2.0, Vector2.ONE * TILE_SIZE))
	draw_circle(NEW_EGG_CENTER + Vector2(0, 8), NEW_EGG_RADIUS + 3, Color(0.25, 0.15, 0.35, 0.22))
	draw_circle(NEW_EGG_CENTER, NEW_EGG_RADIUS, CORAL)
	draw_arc(NEW_EGG_CENTER, NEW_EGG_RADIUS - 7, 0, TAU, 48, Color(1, 1, 1, 0.75), 5.0)
	var over_trash := dragging != null and _in_trash(dragging.global_position)
	var trash_radius := TRASH_RADIUS + (8 if over_trash else 0)
	draw_circle(TRASH_CENTER + Vector2(0, 6), trash_radius + 3, Color(0.25, 0.15, 0.35, 0.18))
	draw_circle(TRASH_CENTER, trash_radius, TRASH_RED if over_trash else TRASH_BLUE)
	if dragging and dragging.kind == "clothes" and toy.has_node(dragging.slot.capitalize()):
		var anchor: Marker2D = toy.get_node(dragging.slot.capitalize())
		var distance := dragging.global_position.distance_to(anchor.global_position)
		if distance <= SNAP_HINT_DISTANCE:
			var strength := 0.95 if distance <= SNAP_DISTANCE else 0.35
			draw_arc(anchor.global_position, 104, 0, TAU, 56, Color(1, 0.85, 0.35, strength), 11.0)


func _bounce_in() -> void:
	_sfx("jingle")
	var move := create_tween()
	move.tween_property(toy, "position", TOY_POS, 0.5).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	var squash := create_tween()
	squash.tween_property(toy, "scale", Vector2(TOY_SCALE * 1.3, TOY_SCALE * 0.7), 0.25).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	squash.tween_property(toy, "scale", Vector2(TOY_SCALE * 0.85, TOY_SCALE * 1.15), 0.12)
	squash.tween_property(toy, "scale", Vector2.ONE * TOY_SCALE, 0.12)
	await squash.finished
	Effects.burst(burst, toy.global_position, 1.2)
	_sfx("toy_" + toy_name)
	var voice_length := _voice("wow")
	await get_tree().create_timer(maxf(voice_length, 0.6)).timeout
	ready_to_play = true
	_start_idle()
	_voice("dress_me")
	ready_to_decorate.emit()


func _start_idle() -> void:
	if _idle_tween and _idle_tween.is_valid():
		_idle_tween.kill()
	_idle_tween = create_tween().set_loops()
	_idle_tween.tween_property(toy, "scale", Vector2(TOY_SCALE * 0.99, TOY_SCALE * 1.02), 1.4).set_trans(Tween.TRANS_SINE)
	_idle_tween.tween_property(toy, "scale", Vector2.ONE * TOY_SCALE, 1.4).set_trans(Tween.TRANS_SINE)


func _react_toy() -> void:
	_sfx("toy_" + toy_name)
	Effects.burst(burst, toy.global_position, 0.7)
	if _idle_tween and _idle_tween.is_valid():
		_idle_tween.kill()
	if _react_tween and _react_tween.is_valid():
		_react_tween.kill()
	_react_tween = create_tween()
	_react_tween.tween_property(toy, "scale", Vector2(TOY_SCALE * 1.12, TOY_SCALE * 0.9), 0.1).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_react_tween.tween_property(toy, "scale", Vector2(TOY_SCALE * 0.96, TOY_SCALE * 1.06), 0.12)
	_react_tween.tween_property(toy, "scale", Vector2.ONE * TOY_SCALE, 0.15).set_trans(Tween.TRANS_BACK)
	_react_tween.tween_callback(_start_idle)
	var hop := create_tween()
	hop.tween_property(toy, "position", TOY_POS + Vector2(0, -18), 0.12).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	hop.tween_property(toy, "position", TOY_POS, 0.3).set_trans(Tween.TRANS_BOUNCE)


func _pick_from_shelf(item: DecorItem, pos: Vector2) -> void:
	if item.kind == "background":
		_apply_background(item.item_name)
		_sfx("boop")
		Effects.burst(burst, pos, 0.6)
		return
	var copy := _spawn(item.item_name, item.kind, false)
	copy.global_position = pos + LIFT
	copy.scale = Vector2.ONE * 1.08
	dragging = copy
	drag_offset = -LIFT
	queue_redraw()


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
	Effects.burst(burst, anchor.global_position, 0.9)


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
	return pos.distance_to(TRASH_CENTER) <= TRASH_RADIUS + 20


func _tab_rect(index: int) -> Rect2:
	return Rect2(Vector2(SHELF_COLUMNS[index] - TAB_SIZE.x / 2.0, TAB_Y - TAB_SIZE.y / 2.0), TAB_SIZE)


func _show_tab(tab: String) -> void:
	shelf_tab = tab
	for item in shelf_items:
		item.queue_free()
	shelf_items.clear()
	shelf_tiles.clear()
	var ids: Array
	if tab == "clothes":
		ids = Content.CLOTHES.keys()
	elif tab == "sticker":
		ids = Content.STICKERS
	else:
		ids = Content.BACKGROUNDS
	for i in ids.size():
		var row := i / 3
		if row >= SHELF_ROWS.size():
			break
		var centre := Vector2(SHELF_COLUMNS[i % 3], SHELF_ROWS[row])
		shelf_tiles.append(centre)
		var item := _spawn(ids[i], tab, true)
		item.position = centre
		item.pop_in()
		shelf_items.append(item)
	queue_redraw()


func _build_tab_icons() -> void:
	for i in TABS.size():
		var icon := Sprite2D.new()
		icon.texture = load("res://assets/art/%s.png" % TAB_ART[i])
		icon.scale = Vector2.ONE * 52.0 / 512.0
		icon.position = _tab_rect(i).get_center()
		add_child(icon)


func _spawn(id: String, item_kind: String, shelf: bool) -> DecorItem:
	var item := ITEM_SCENE.instantiate() as DecorItem
	add_child(item)
	item.setup(id, item_kind, shelf, TOY_SCALE)
	return item


func _apply_background(id: String) -> void:
	backdrop.texture = load("res://assets/art/bg_%s.png" % id)


func _style(fill: Color, radius: int, shadow_color: Color, shadow_size: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.set_corner_radius_all(radius)
	style.shadow_color = shadow_color
	style.shadow_size = shadow_size
	style.shadow_offset = Vector2(0, 6)
	style.anti_aliasing = true
	return style


func _sfx(sound: String) -> void:
	# Looked up at runtime so the script also compiles under --script and --check-only.
	var audio := get_node_or_null("/root/Audio")
	if audio:
		audio.play(sound)


func _voice(cue: String) -> float:
	var audio := get_node_or_null("/root/Audio")
	return audio.play_voice(cue) if audio else 0.0
