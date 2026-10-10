extends SceneTree
## Headless smoke test. Run: godot --headless --path . --script res://tests/smoke.gd
## Exits 0 when all checks pass, 1 otherwise.

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
