# Tap to skip

Double-tap your Pixel Buds A (the "next track" gesture) while a YouTube ad is
playing on your Windows PC, and the Skip button gets clicked for you.
A single tap (play/pause) is never touched.

## Setup

1. Download `tap_to_skip.exe` from the latest build: **Actions** tab → newest
   run → `tap_to_skip-windows` (a zip with the .exe inside).
2. Put the .exe in a folder it can stay in (for example `C:\Users\<you>\TapToSkip`)
   and copy `skip.png` next to it. `skip.png` is a tight crop of the Skip
   button's text and icon.
3. Start `tap_to_skip.exe`. It appears as a blue icon in the system tray
   (click the `^` arrow if Windows hides it). There is no window.

## Tray menu

| Item | What it does |
|------|--------------|
| Paused | Stop reacting to double taps; they skip tracks again as normal. The icon turns gray. |
| Start with Windows | Start automatically when you sign in. Turn it on only after the .exe is in its final folder. |
| Test skip.png (in 5 s) | Switch to the browser with an ad on screen; after 5 seconds a message shows the match score. |
| Reload skip.png | Pick up a changed `skip.png` without restarting. |
| Quit | Stop the program. |

## Notes

- Without `skip.png`, a double tap clicks at the current cursor position.
- `tap_to_skip.exe --test` runs only the test and exits.
- Log: `tap_to_skip.log` next to the .exe (or in `%LOCALAPPDATA%\TapToSkip`
  if the .exe's folder is read-only).
- Settings (match threshold, search area, timeouts) are at the top of
  `tap_to_skip.py`; changing them needs a rebuild (just commit the change).
- Starting the program twice shows a message instead of a second copy.
