class_name Effects
extends RefCounted
## Shared particle helpers, so every sparkle burst in the game looks the same.


static func sparkle_ramp() -> Gradient:
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.25, 0.5, 0.75, 1.0])
	gradient.colors = PackedColorArray([
		Color("ffffff"), Color("ffe27a"), Color("ff9ec0"), Color("9fe8d0"), Color("a9c8ff"),
	])
	return gradient


## Fires a one-shot burst at a position in the parent's coordinates.
static func burst(particles: CPUParticles2D, at: Vector2, strength := 1.0) -> void:
	particles.position = at
	particles.scale = Vector2.ONE * strength
	particles.restart()
