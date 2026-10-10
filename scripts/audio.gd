extends Node
## Plays sound effects from a small player pool and voice cues when present.
## Missing files are skipped silently, so real recordings can be dropped in later.

const POOL_SIZE := 8
const SFX_PATH := "res://assets/sfx/%s.wav"
const VOICE_EXTENSIONS := [".ogg", ".wav", ".mp3"]

var _players: Array[AudioStreamPlayer] = []
var _cache := {}


func _ready() -> void:
	for i in POOL_SIZE:
		var player := AudioStreamPlayer.new()
		add_child(player)
		_players.append(player)


func play(sound_name: String) -> void:
	var stream := _load_sfx(sound_name)
	if stream == null:
		return
	for player in _players:
		if not player.playing:
			player.stream = stream
			player.play()
			return
	_players[0].stream = stream
	_players[0].play()


## Plays a voice cue from assets/voice/. Returns its length in seconds, or 0.0 if missing.
func play_voice(voice_name: String) -> float:
	for ext in VOICE_EXTENSIONS:
		var path := "res://assets/voice/%s%s" % [voice_name, ext]
		if ResourceLoader.exists(path):
			var stream := load(path) as AudioStream
			if stream == null:
				return 0.0
			var player := AudioStreamPlayer.new()
			add_child(player)
			player.stream = stream
			player.finished.connect(player.queue_free)
			player.play()
			return stream.get_length()
	return 0.0


func _load_sfx(sound_name: String) -> AudioStream:
	if _cache.has(sound_name):
		return _cache[sound_name]
	var path := SFX_PATH % sound_name
	var stream: AudioStream = null
	if ResourceLoader.exists(path):
		stream = load(path)
	_cache[sound_name] = stream
	return stream
