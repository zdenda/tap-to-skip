# Tap to skip

Skips YouTube ads on a Windows PC for you. Two ways:

- **Double-tap your Pixel Buds A** (the "next track" gesture) while an ad is
  playing, and the Skip button gets clicked.
- **Automatic mode:** when you are away from the computer, the Skip button
  gets clicked without any tap at all.

A single tap (play/pause) is never touched.

## Setup

1. Download `tap_to_skip.exe` from the latest build: **Actions** tab → newest
   run → `tap_to_skip-windows` (a zip with the .exe inside).
2. Put the .exe in a folder it can stay in (for example `C:\Users\<you>\TapToSkip`)
   and copy `skip.png` next to it. `skip.png` is a tight crop of the Skip
   button's text and icon.
3. Start `tap_to_skip.exe`. It appears as a blue icon in the system tray
   (click the `^` arrow if Windows hides it). There is no window.

## Automatic mode

Every 1.5 seconds the program looks at the lower-right part of the screen and
clicks the Skip button if it is there. To stay out of your way it only does
this when **both** of these are true:

- the mouse and keyboard have not been touched for 30 seconds (taps on the
  buds and the program's own clicks do not count), and
- the active window's title contains "YouTube" (a browser tab with YouTube in
  front, also in fullscreen).

So while you are working, nothing happens on its own; use the double tap. If
a "button" does not disappear after 3 clicks, it is left alone until it goes
away. Automatic mode is on by default and the choice is remembered in
`tap_to_skip.ini`.

## Tray menu

| Item | What it does |
|------|--------------|
| Paused | Stop reacting to double taps (they skip tracks again as normal) and stop automatic mode. The icon turns gray. |
| Automatic mode | Automatic clicking on or off. |
| Start with Windows | Start automatically when you sign in. Turn it on only after the .exe is in its final folder. |
| Test skip.png (in 5 s) | Switch to the browser with an ad on screen; after 5 seconds a message shows the match score, the active window's title and the idle time. |
| Reload skip.png | Pick up a changed `skip.png` without restarting. |
| Quit | Stop the program. |

## Notes

- Without `skip.png`, a double tap clicks at the current cursor position and
  automatic mode does nothing.
- `tap_to_skip.exe --test` runs only the test and exits.
- Files: `tap_to_skip.log` and `tap_to_skip.ini` next to the .exe (or in
  `%LOCALAPPDATA%\TapToSkip` if the .exe's folder is read-only).
- Settings are at the top of `tap_to_skip.py`: match threshold, search area,
  timeouts, and for automatic mode the idle time (`AUTO_IDLE_SECONDS`), the
  check interval and the window keyword. Changing them needs a rebuild (just
  commit the change).
- Starting the program twice shows a message instead of a second copy.
