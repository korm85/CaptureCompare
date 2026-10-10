class_name Pointer
extends RefCounted
## Turns raw touch and mouse events into PRESS, DRAG and RELEASE.
## Godot also sends events emulated from the other kind of input (mouse from touch, and touch
## from mouse). Those carry device DEVICE_ID_EMULATION and are ignored, so each tap is handled
## once. Only the first finger is tracked.

const NONE := 0
const PRESS := 1
const DRAG := 2
const RELEASE := 3

var _touch_index := -1


## Returns [action, position]. Action is NONE for events this helper does not use.
func handle(event: InputEvent) -> Array:
	if event.device == InputEvent.DEVICE_ID_EMULATION:
		return [NONE, Vector2.ZERO]
	if event is InputEventScreenTouch:
		if event.pressed and _touch_index == -1:
			_touch_index = event.index
			return [PRESS, event.position]
		if not event.pressed and event.index == _touch_index:
			_touch_index = -1
			return [RELEASE, event.position]
	elif event is InputEventScreenDrag:
		if event.index == _touch_index:
			return [DRAG, event.position]
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		return [PRESS if event.pressed else RELEASE, event.position]
	elif event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_MASK_LEFT:
		return [DRAG, event.position]
	return [NONE, Vector2.ZERO]
