extends SceneTree
## Headless smoke test. Run: godot --headless --path . --script res://tests/smoke.gd
## Exits 0 when all checks pass, 1 otherwise.

const Content := preload("res://scripts/data.gd")

var _failures := 0


func _init() -> void:
	_run()


func _check(ok: bool, label: String) -> void:
	print(("PASS " if ok else "FAIL ") + label)
	if not ok:
		_failures += 1


func _run() -> void:
	await process_frame
	await _test_egg()
	await _test_reveal()
	await _test_decorate()
	await _test_touch_input()
	await _test_main_background()
	_test_art()
	_test_no_blocking_controls()
	print("FAILURES: %d" % _failures)
	quit(1 if _failures > 0 else 0)


func _test_egg() -> void:
	var egg: Egg = (load("res://scenes/egg.tscn") as PackedScene).instantiate() as Egg
	root.add_child(egg)
	egg.reset()
	var hatched := [false]
	egg.hatched.connect(func(): hatched[0] = true)
	for i in 3:
		egg.hit()
	_check(egg.stage == 3 and not egg.busy, "egg is cracked to stage 3 without splitting")
	egg.hit()
	_check(egg.busy, "fourth hit starts the split")
	await create_timer(1.3).timeout
	_check(hatched[0], "egg emits hatched after the split")
	egg.queue_free()


func _test_reveal() -> void:
	var decorate: Decorate = (load("res://scenes/decorate.tscn") as PackedScene).instantiate() as Decorate
	root.add_child(decorate)
	var revealed := [false]
	decorate.ready_to_decorate.connect(func(): revealed[0] = true)
	decorate.start_reveal("dog")
	_check(decorate.toy.texture != null, "toy texture loads for dog")
	var head: Marker2D = decorate.toy.get_node("Head")
	_check(head.position == Content.TOY_ANCHORS["dog"]["head"], "toy has head anchor at its data offset")
	await create_timer(2.5).timeout
	_check(revealed[0], "reveal finishes and emits ready_to_decorate")
	decorate.queue_free()


func _test_art() -> void:
	var missing := []
	for name in Content.TOYS + Content.STICKERS + Content.CLOTHES.keys():
		if not ResourceLoader.exists("res://assets/art/%s.png" % name):
			missing.append(name)
	for name in Content.BACKGROUNDS:
		for prefix in ["bg_", "swatch_"]:
			if not ResourceLoader.exists("res://assets/art/%s%s.png" % [prefix, name]):
				missing.append(prefix + name)
	for name in ["shadow", "spark", "confetti", "hammer", "trash", "egg_0", "crack_1"]:
		if not ResourceLoader.exists("res://assets/art/%s.png" % name):
			missing.append(name)
	_check(missing.is_empty(), "every toy, sticker and clothing item has art (missing: %s)" % str(missing))


func _test_decorate() -> void:
	var decorate: Decorate = (load("res://scenes/decorate.tscn") as PackedScene).instantiate() as Decorate
	root.add_child(decorate)
	decorate.start_reveal("cat")
	await create_timer(2.5).timeout
	var head_pos: Vector2 = decorate.toy.get_node("Head").global_position

	# Clothes tab: the first shelf item is the party hat, first column first row.
	decorate.press(Vector2(926, 170))
	decorate.drag(head_pos + Vector2(10, 5))
	decorate.release(head_pos + Vector2(10, 5))
	_check(decorate.placed_slots.has("head"), "hat snaps to the head anchor when released nearby")

	# Far release: the bow goes back to the shelf and does not replace the hat.
	var hat = decorate.placed_slots["head"]
	decorate.press(Vector2(1066, 170))
	decorate.drag(Vector2(600, 620))
	decorate.release(Vector2(600, 620))
	_check(decorate.placed_slots["head"] == hat, "far release does not snap or replace the hat")

	# Sticker tab: place a star on the toy, then drag it to the shelf to remove it.
	decorate._show_tab("sticker")
	var before := decorate.get_child_count()
	decorate.press(Vector2(926, 170))
	decorate.drag(Vector2(330, 470))
	decorate.release(Vector2(330, 470))
	_check(decorate.get_child_count() == before + 1, "star sticker is placed on the toy")
	var star: DecorItem = decorate.get_children().back()
	decorate.press(Vector2(330, 470))
	decorate.drag(Vector2(1000, 300))
	decorate.release(Vector2(1000, 300))
	await create_timer(0.3).timeout
	_check(not is_instance_valid(star) or star.is_queued_for_deletion(), "sticker dropped on the shelf is removed")

	# New egg button emits the signal.
	var asked := [false]
	decorate.new_egg_requested.connect(func(): asked[0] = true)
	decorate.press(Decorate.NEW_EGG_CENTER)
	_check(asked[0], "new egg button emits new_egg_requested")
	decorate.queue_free()


func _test_no_blocking_controls() -> void:
	# A Control that stops mouse events would swallow taps before _unhandled_input sees them.
	var blockers := []
	for path in ["res://scenes/main.tscn", "res://scenes/decorate.tscn", "res://scenes/egg.tscn"]:
		var scene: Node = (load(path) as PackedScene).instantiate()
		for node in _all_descendants(scene):
			if node is Control and node.mouse_filter != Control.MOUSE_FILTER_IGNORE:
				blockers.append("%s:%s" % [path.get_file(), node.name])
		scene.free()
	_check(blockers.is_empty(), "no Control blocks mouse input (blockers: %s)" % str(blockers))


func _all_descendants(node: Node) -> Array:
	var out := []
	for child in node.get_children():
		out.append(child)
		out.append_array(_all_descendants(child))
	return out


func _touch(target: Node, kind: int, index: int, pos: Vector2, pressed := true) -> void:
	# Headless runs do not deliver injected input to the viewport, so call the screen's input
	# handler directly with the same event a finger would produce.
	if kind == 0:
		var down := InputEventScreenTouch.new()
		down.index = index
		down.pressed = pressed
		down.position = pos
		target._unhandled_input(down)
	else:
		var move := InputEventScreenDrag.new()
		move.index = index
		move.position = pos
		target._unhandled_input(move)


func _test_touch_input() -> void:
	var decorate: Decorate = (load("res://scenes/decorate.tscn") as PackedScene).instantiate() as Decorate
	root.add_child(decorate)
	decorate.start_reveal("cat")
	await create_timer(2.5).timeout
	var head_pos: Vector2 = decorate.toy.get_node("Head").global_position

	# An emulated mouse press from a finger must not start a second drag.
	var emulated := InputEventMouseButton.new()
	emulated.button_index = MOUSE_BUTTON_LEFT
	emulated.pressed = true
	emulated.position = Vector2(926, 170)
	emulated.device = InputEvent.DEVICE_ID_EMULATION
	decorate._unhandled_input(emulated)
	_check(decorate.dragging == null, "emulated mouse event from touch is ignored")

	_touch(decorate, 0, 0, Vector2(926, 170))
	_check(decorate.dragging != null, "touch press on a shelf item starts a drag")
	_touch(decorate, 1, 0, head_pos + Vector2(10, 85))
	_touch(decorate, 1, 0, head_pos + Vector2(10, 80))
	_touch(decorate, 0, 0, head_pos + Vector2(10, 80), false)
	_check(decorate.placed_slots.has("head"), "touch drag and release snaps the hat to the head")
	decorate.queue_free()

	var egg: Egg = (load("res://scenes/egg.tscn") as PackedScene).instantiate() as Egg
	root.add_child(egg)
	egg.reset()
	_touch(egg, 0, 0, Vector2(640, 340))
	_check(egg.stage == 1, "touch tap on the egg cracks it")
	egg.queue_free()


func _test_main_background() -> void:
	# Main's sky sprite is drawn behind the decorate screen, so it must be hidden there or it hides
	# the chosen backdrop.
	var main: Node2D = (load("res://scenes/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var egg: Egg = main.egg
	for i in 4:
		egg.hit()
	await create_timer(1.3).timeout
	_check(not main.background.visible, "main sky is hidden while decorating")
	main.decorate.new_egg_requested.emit()
	_check(main.background.visible, "main sky returns for a new egg")
	main.queue_free()

