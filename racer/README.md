# Rainbow Racers

A never-ending, one-finger racing game for little kids.

- Slide a finger to steer. Tap your own car to honk.
- Collect stars, hit rainbow pads for a speed boost, grab surprise gifts.
- Race four animal cars. Bumping them is silly, never a crash. No game over.
- The road travels through six lands that change about every minute:
  Flower Meadow, Sunny Beach, Under the Sea, Snowy Land, Candy Town, Starry Space.

## Files

- `game.html` – the whole game (one file, no dependencies).
- `RainbowRacers.apk` – ready-to-install Android app (works offline).
- `android/` – the small WebView app that wraps `game.html`.

## Install on Android

Download `RainbowRacers.apk` on the tablet/phone, open it, and allow
"Install unknown apps" when asked.

## Rebuild the APK

```
cd android
echo "sdk.dir=/path/to/android-sdk" > local.properties
gradle assembleRelease
```
The APK is at `android/app/build/outputs/apk/release/app-release.apk`.
