# Getting Started

This page walks you through the first launch and the everyday tasks: placing overlays, configuring them and finding options. Make sure your game is set up first: see [Game Setup](Game-Setup.md).

## First launch

On first launch, the **setup wizard** asks a few questions. Every choice can be changed later, and nothing is applied before `Finish Setup`: closing the wizard (`Esc` or the window close button, after a confirmation) keeps everything as it was. The steps are listed on the left: click one to go back to it, `Enter` goes to the next one.

1. **Welcome**: `English` or `Français`. The wizard switches language at once, the app once setup is finished.
2. **Game**: the game to read telemetry from (`Le Mans Ultimate` or `rFactor 2`). A game running now is marked `Running` and picked for you.
3. **Units**: `Metric` (km/h, °C, L, kPa, kg) or `Imperial` (mph, °F, gal, psi, lb), saved in the preset. A preset with mixed units can keep them (`Keep current units`). Each unit can be changed later in the preset units.
4. **Appearance**: the window theme (`Modern Dark`, `Modern Grey`, `Modern White` or `Legacy Grey`, each drawn in its colors), the overlay theme (the same four, with an overlay drawn in each), `Colorblind Colors` and the modern font (values in monospace JetBrains Mono, labels in Barlow; off: each overlay in its own font). A preview shows overlays in the chosen style.
5. **Overlays**: create a new preset (the name is checked as you type) or pick an existing one, then check the overlays to show, each shown as a picture: Relative, Standings, Deltabest, Fuel, Virtual Energy, Pedal, Gear, Steering Wheel, Tyre Temperature, Brake Temperature, Flag, Session, Weather, Radar, Track Map and Trailing. `Recommended` checks Relative, Deltabest, Fuel, Pedal, Gear and Flag. With an existing preset, the overlays it already shows are checked, and unchecking one turns it off; overlays not listed keep their state.
6. **Streaming** (optional): `Show my overlays on stream` turns on the stream overlay server once setup is finished; `Copy Address` copies the address of the layout source (every overlay at its place, 1920 x 1080) to add as a browser source in OBS, Streamlabs, XSplit or vMix. `Next` without it keeps streaming off. See [Connections](Connections.md#stream-overlays-obs-streamlabs-xsplit-vmix).
7. **Ready**: every choice, with `Change` to go back to its step, what happens once finished (both on by default: the `Overlays` page opens in Screen view to move overlays, and overlays on screen show a simulated race for a few seconds, `Test on Screen`), and tips for the first drive.

Overlay pictures are drawn with the overlay settings on a simulated race (a GT3 mid race at Road Atlanta), so you see what each overlay shows before you drive.

The wizard is shown once. Open it again from `Help` > `Setup Wizard…`.

## The main window

The navigation bar on the left gives access to pages and tools:

| Entry | What it does |
|---|---|
| `Home` | Checks, game and session state, driver ranks, overlay lock & preset, last session & its debrief, this week, next races, quick access |
| `Races` | [Upcoming Races](Upcoming-Races.md): online races to come (Le Mans Ultimate) |
| `Overlays` | Turn overlays on or off and configure them |
| `Stats` | [Driver Stats](Driver-Stats.md) |
| `Results` | Results of past sessions: classification, laps, sectors, incidents and penalties |
| `Telemetry` | [Telemetry Viewer](Telemetry-Viewer.md) |
| `Presets` | Load, create and manage presets, see [Presets and Settings](Presets-and-Settings.md) |
| `More` | Unfolds every page left out of the bar: [Broadcast Director](Broadcast-Director.md), [Stream Overlays](Connections.md#stream-overlays-obs-streamlabs-xsplit-vmix), [Race Calculator](Race-Calculator.md), Data Editors, Settings... Click one to open it, its `+` adds it to the bar, or drag it there |

The buttons under the bar: overlay lock, auto hide and VR compatibility switches and the game API state (dot: green while the game runs, click for the API menu). With the Windows title bar (option `enable_modern_title_bar` off, or Linux) they also hold `Settings` (gear, `Ctrl+,`: every global option of the app, see [Presets and Settings](Presets-and-Settings.md#global-config)), the command palette, the **notification center** (bell, with the number of unread messages) and help (`?`: the page of this guide about the page shown), and the back and forward arrows sit at the top of the bar; with the modern title bar (Windows default) these are in the title bar, see below. Back and forward go back and forth between pages, like a browser (`Alt+Left` / `Alt+Right`, mouse back and forward buttons).

- The bar is yours: drag an entry to move it, drag it onto `More` to take it out, drag a page from `More` into the bar (or click its `+`) to add it. `Alt+Up` / `Alt+Down` move the focused entry; right-click an entry for `Move Up`, `Move Down` and `Remove from Navigation Bar`, the bar for `Reset Navigation Bar…`. `Editors` ([Data Editors](Presets-and-Settings.md#style-presets)) and `Settings` are not in the bar by default (nor `Broadcast`, `Stream` and `Calculator` since 0.29.0, kept in bars set up before): add them there, or open them from `More`, the `Tools` menu (also in the menu button `☰` of the modern title bar), the command palette (`Ctrl+K`) or the Home page quick access. The main window has three pages, `Home`, `Overlays` and `Presets`, every other entry is a tool page. Since 0.29.0 the former `Modules` and `Hotkeys` pages are categories of the `Settings` page, `Spectate` is a tab of the [Broadcast Director](Broadcast-Director.md), the editors, the track map viewer and `Pacenotes` are tabs of `Data Editors`, and the `Tools` page is the `Tools` menu: their entries in your bar or quick access open their new place. In 0.23.0 the bar of every user was set once to this default (`Broadcast` in place of `Spectate`); after 0.25.0, `Stream` was added after `Broadcast` in every bar. `Ctrl+1` to `Ctrl+9` open the first nine entries.
- Tools, editors and settings open as pages inside the window, under a header showing the page you opened them from (`Home › Race Calculator`, `Overlays › Overlay Options`: click it to go back there), the page title and a single `Close` button. Tools of the navigation bar show their title the same way, without breadcrumb or `Close` (pages like any other). The `Tools` menu lists the pages left out of the navigation bar, main pages first, then tools by section. `Alt+Left` or the mouse back button goes back to the previous page, `Alt+Right` or the mouse forward button forward again (a tool page closed meanwhile opens again). A page you leave closes by itself, unless it has unsaved changes. Navigation bar tools stay as you left them while the app runs. At the next start, only the page shown last is reopened, the other tools open when you click them (`Window` > `Reopen Pages at Startup`).
- `Ctrl+K` opens the **command palette**: type to find and run pages (main pages and tools in one `Pages` group), every menu command (updates, bug report, log, restart, theme...), settings, overlays, modules, presets and options; recent commands come first. Start with `>` for commands only, `@` for options, `#` for presets. `Ctrl+F` searches the page shown (its search field), `Ctrl+Shift+F` finds any option. `Ctrl+/` or `F1` shows every keyboard shortcut.
- The **notification center** (bell) lists the modes on under `Now` (locked preset, spectate, pace notes, setup backup, Broadcast Director: `Open` goes to their page or tab), then the messages of the app in groups by day: background problems (an overlay that crashed, a file that could not be saved, with `View Log` and `Create Bug Report…`), updates found and race reminders (`Open Upcoming Races`). Filter them by level, search them, copy or remove one, `Don't Show Again` on a warning or an error that keeps coming back, `Clear All` (`Undo` while it is open); a message is marked read when you click it. The gear button opens the notification settings. The last 100 are kept after a restart, and messages show in the app language even after a language change. The count on the bell is red with an unread error, yellow with an unread warning, grey otherwise. An update found shows as a chip in the title bar (or in the status bar with the Windows title bar).
- **Windows notifications**: while the window is hidden in the tray or minimized, errors and warnings show as a Windows notification (at most one a minute, the next one telling how many came meanwhile; click it to open the notification center), held while you drive if you turn on `Hold Notifications While Driving`. Race reminders and RaceControl news of your registered races (server ready, race cancelled) always show one (click: `Upcoming Races`; `Remind Me in 2 Min` in the bell), optionally a last reminder a few minutes before the start, a sound (by default only while Windows hides its notifications, your own sound file if you want) and a flashing taskbar button. Several notifications clicked later from Windows open the bell, which lists them all. Each kind can be turned off in `Settings` > `Notification`. Windows may hide notifications over a full screen game: the `Race notifications` overlay shows them in game (option `show_app_messages`), and the `Web Dashboard` page of your phone shows them as a banner (it vibrates).
- A dot (`•`) marks pages with unsaved changes (and each tab of `Data Editors` with unsaved changes). `Ctrl+S` saves the page shown (in `Data Editors`, the tab shown). Invalid values are outlined in red with the reason while you type.
- **Modern title bar** (Windows, on by default): from left to right, the menu button `☰` (`F10`, or `Alt` pressed alone) with the `Overlay`, `API`, `Settings`, `Tools`, `Window` and `Help` menus, back and forward, the app version, the name of the page shown in the middle (with `*` while it has unsaved changes; pages no longer repeat it at their top), the update chip when one is found, the command palette, the notification center, `Settings` and help, then minimize, maximize and close. Drag the bar to move the window, double-click it to maximize, right-click it (or `Alt+Space`) for the window menu; hovering maximize shows the Windows 11 Snap Layouts. Other windows (setup wizard, messages) get their title bar in the window colors on Windows 11. Turn `enable_modern_title_bar` off in `Settings` > `Application` (restart) to get the Windows title bar, the menu bar and the status bar back; the title bar then follows the window theme (dark or light).
- **Window size**: at first launch the window opens at a comfortable size, centered on the screen. Its size, position and maximized state are remembered (`Window` > `Remember Size` and `Remember Position`), saved a moment after each change so a crash keeps them too. Wide tools (race results, telemetry, layout editor...) grow the window while they are open, keeping it inside the screen, and give it back its size and place once closed: the grown size is never remembered. The window can never be made so small that pages overlap or get cut: the page area keeps a minimum size (about 650 × 445 pixels at 100% scale), larger while the telemetry viewer (its toolbar and three panels stay whole, in every language) or driver stats are shown. The navigation bar keeps its width, and its selected entry stays in view when the window is short. The window is also brought back on screen if it was left on a monitor that is no longer there. `Window` > `Reset Window Size and Position` (also in the command palette) puts it back to the default size, centered.

The app also has a **tray icon**. Click it to show the main window, right-click it for the loaded preset, `Presets` (switch preset), `Open NeoPedal` and the overlay menu (`Lock Overlay`, `Auto Hide`, `Reload`, `Quit`...). With `Window` > `Minimize to Tray`, the window close button hides the app to the tray instead of quitting (told once by a notification the first time). On a desktop without a notification area (some Linux desktops), the window is minimized to the taskbar instead, never hidden with no way back.

## Home page

The `Home` page shows at a glance:

- the **status** on top. When all is well it is one slim line (`Ready · Game connected, overlays on.`), and on track with nothing to tell there is none (the game card tells the session). Else it is a banner: its title is the verdict, the game state or the most important check (`Game not running`, `Game running without data`...), with the button that fixes it, then the other checks, most important first, each with its button: `Game running without data` (Le Mans Ultimate is open but sends nothing: enable `Settings > Gameplay > Enable plugins` in the game, then restart it), `Game not running` (game setup reminder of the selected game: display mode, plugin), `Active State Override is on`, `No overlay enabled`, `Spectate Mode Enabled`, `Lap recording is off` (the session debrief and the telemetry need recorded laps). `Update Available · v1.2.3` shows there once a new version is out. The version, `What's New` and `Check for Updates` are in the help menu (`?`, or `☰` > `Help`);
- the game card with the circuit & car logos; click it for the API options of the game. On track it takes the whole row: position, lap (of the race laps) and time left in big type, with `Live Calculator` (Race Calculator on its `Live` tab), `Broadcast Director` (Le Mans Ultimate) and `Lock Overlay` / `Unlock Overlay` at hand;
- your **driver card**: name, flag, team and number, badge, Driver Rank & Safety Rank in big type in their colors with the change since the previous rank, the progress to the next tier and a line of each rank over time, race record of the results files. When the ranks shown are the last ones known (`Last ranks known · 3 days ago`, date and time in its tooltip, in the warning color after a week), `Refresh` asks RaceControl for them again (online ranks option on, the game must be running, at most every few minutes);
- the **Overlays** card: the preset in use (`Switch Preset` loads one of your latest presets), locked or not (one-click `Lock Overlay` / `Unlock Overlay`, in the game card on track), overlays and modules turned on, `Modules` for the `Modules` category of the Settings page (click the card for the Overlays page);
- the **last session** you drove (click it to open the Driver Stats page on its track and car; how long ago it was, the date and time in its tooltip) and its **session debrief**, made from the laps recorded while you drove: best lap in big type against your personal best (or `New personal best`), the lap times of the session as bars (best lap full height, invalid laps faint, lap and time in their tooltip), number of laps, pace and consistency (average and spread of the valid laps within 103 % of your best), theoretical best (best game sectors), fuel per lap, and `Work on`: the three corners where your best lap loses most time against your older personal best lap, with the likely cause (`Brakes 6 m earlier`, `Minimum speed 4 km/h lower`...). When the session is your new personal best, a typical lap of the session is compared with its best lap instead. **Click a corner** (or `Tab` to it, then `Enter`) to open the telemetry with both laps, the `Corners` tab and the charts zoomed on that corner; `Open Telemetry` opens both laps. The lap time goal of the track and car (set on the Driver Stats page) is shown with what is left to find and a progress bar;
- **This Week**, as on the Driver Stats page: sessions, driving time and laps of the last 7 days, the driving time of each day as bars (today in the accent color), with the goals reached, new personal bests and goals within reach (click it for the Driver Stats page). Not shown when you did not drive in the last 7 days;
- **Next Races** (Le Mans Ultimate): the next daily races of the public RaceControl site; the time to a start counts down to the second in its last 10 minutes, and the race starting soon is outlined; solo races open to registration, the game running);
- **Quick Access** buttons (by default: Data Editors, Settings, Broadcast Director, Overlay Performance and Create Bug Report). Entries of the navigation bar are not repeated there (`In Navigation Bar` in the list). Use `Customize…` next to `Quick Access`, or right-click the buttons, to choose tools, pages and actions.

Cards read in background (driver card, debrief, this week) keep their place with a spinner until read, then fade in: the page never jumps. Cards are placed row by row: driver and overlays, then last session and this week (side by side on a narrower window), each row filled from edge to edge.

## When overlays are shown

Overlays appear when your car is on track and hide when you are in menus or not driving (`Auto Hide`, on by default in the tray menu). Each overlay can also be limited to some sessions or to the pits: see [Overlays](Overlays.md#visibility-by-session-and-pit).

## Move overlays

While the overlay is unlocked you can move overlays with the mouse; once locked, they stay in place and clicks go through to the game. The lock state is kept between starts.

1. **Unlock**: `Unlock Overlay` on the Home page, tray icon menu > uncheck `Lock Overlay`, the command palette or the `overlay_lock` hotkey. Overlays stay as they are: move the mouse over one to see its outline, name and corner handle. For the **edit mode**, right-click an overlay > `Edit Mode`: a toolbar shows up at the top of the game screen, and every overlay shows its outline and name, also the ones that draw nothing yet and the ones hidden by `Auto Hide` or their visibility context (so you can place them from the game menus too). To start the edit mode at each unlock, turn on `enable_edit_mode_on_unlock` (`Settings` > `Overlay Style` > `Overlay Editing`).
2. **Drag** an overlay to move it. It snaps to screen edges, screen center and the edges and centers of the other overlays; hold `Ctrl` to move freely, `Shift` to keep the move horizontal or vertical. Alignment guides and the position of the overlay show while dragging. `Grid Move` moves overlays on a grid.
3. **Fine-tune with the keyboard**: click an overlay to select it (solid outline), then arrow keys move it by one pixel (`Shift`: 10 pixels, one grid step with `Grid Move`). `Ctrl+Z` / `Ctrl+Y` undo and redo, `Delete` turns the overlay off, `Esc` unselects it.
4. **Resize** an overlay with its corner handle: its size options (font size, bar size...) are scaled.
5. Right-click an overlay for `Options…`, `Center Horizontally`, `Center Vertically`, `Move to Screen` (same place on another monitor), `Visibility`, `Opacity`, `Undo`, `Reload` and `Disable`.
6. **Lock** again when done: `Lock Overlay` in the right-click menu, tray menu or Home page (`Done` on the edit mode toolbar).

The toolbar has `Snap` (option `enable_magnetic_snap`), `Grid` and `Guides` toggles, `Undo` / `Redo`, `Overlays` (active overlays, uncheck one to turn it off, or open the Overlays page) and `Done`. Drag it by its grip. Its `✕` hides it and leaves the overlay unlocked; right-click an overlay > `Edit Mode` brings it back. Everything done while unlocked can be undone until the overlay is locked.

Without the edit mode (and for an overlay already unlocked when the app starts), the outline and corner handle only show under the mouse, so nothing stays on screen if you drive with the overlay unlocked.

![Overlay edit mode](https://raw.githubusercontent.com/Keenny38/NeoPedal/master/docs/changelog/0.22.0-overlay-edit-mode.png)

Positions are saved in the preset, and remembered per screen setup (screens plugged, resolution) in a `<preset>.layouts` file next to it: a file held for a moment by an antivirus or cloud sync is never saved over, and a damaged one is kept as a backup. To make every overlay bigger or smaller at once, set `overlay_scale` in `Settings` > `Overlay Style`.

### Layout editor

The screen view of the `Overlays` page (see below) places overlays without the game running: `Background` > `Capture Screen` shows a picture of the screen shown (the app window is hidden a moment), `Load Screenshot…` a game screenshot (placed on the screen of its size), `Remove Background` takes it away. The picture is kept until the app closes, never saved. The former `Tools` > `Layout Editor` is this view now.

## Configure an overlay

1. Open the `Overlays` page. Each overlay is a card with a preview drawn with your settings, its category and its switch; hover a card a moment and its overlay plays on a moving simulated race (a corner driven in a loop), and its tooltip says what it shows. The buttons at top right switch to a compact list (category and what each overlay shows, preview in a tooltip) or to the screen view (see below); the choice is kept (`show_overlay_previews` in `Settings` > `Application`).
2. Turn an overlay on or off with its switch. Type part of a name in the search box (accents and case ignored, several words allowed), choose `All`, `Active` or `Inactive` (each with its number of overlays), or click a chip: a category, `Favorites` (overlays you marked with the star of their card, `Ctrl+D` on the selected one, kept for every preset) or `Recently Edited` (overlays whose options you saved last, last first). Click a chip again to show all. The sort button sorts by name, enabled overlays first or category; a switched overlay stays where it is until you choose a sort again.
3. Click a card (or the gear button shown on its preview) to open its options in the **Overlay Options** page. Right-click a card for its menu: `Options…`, enable or disable, add to or remove from favorites, `Test on Screen` (the overlays on screen show a simulated race for 10 seconds), `Export Options…`, show only its category.
4. Change options, then `Apply` (`Ctrl+S`): the preset is saved and the edited overlays restart. See [The Overlay Options page](#the-overlay-options-page).

A card shows a small badge when its overlay is not always shown: the sessions or pit state of its `Visibility Context` option (`Race`, `In Pits`...), `Stream Only` or `Screen Only`. The loaded preset is named at top: click it to load another preset (most recent first) or open the `Presets` page.

The screen view shows the running overlays at their place on your screens, with their picture, one screen at a time (the main screen first; a choice per screen, or `All Screens`, when several are plugged). Overlays covering part of another one are outlined, with their number at top. Drag an overlay to move it: it snaps to the edges and centers of the other overlays and of the screens, with guide lines (`Snap` switch, or hold `Alt` to move it freely). Or press `Tab` to reach an overlay (focus ring), then the arrows move it by 1 pixel (`Shift`: 10 pixels) and `Enter` opens its options; a click opens them too. Every move is saved and can be undone (`Undo` in the message shown after, or `Ctrl+Z` on an unlocked overlay). Locked overlays (`Lock Overlay`) cannot be moved here either, as in game: `Overlays locked` says so, with `Unlock Overlay`. In a locked preset, moves are not saved (`Preset Locked`, with `Unlock Preset`): the message says it.

At the bottom, `Enable (12)` and `Disable (3)` switch at once the overlays shown that are off, or on (every overlay without a search or filter, which then also shows how many overlays are shown), with `Undo` in the message shown after. An overlay that is on but could not start shows an `Error` badge, with a notice at top to open the log. Every option is described in its tooltip and in the [settings reference](https://github.com/Keenny38/NeoPedal/blob/master/docs/customization.md#widgets).

Keyboard: type anywhere on the page to search, `Ctrl+F` or `/` jumps to the search box, arrows move between overlays, `Space` switches the selected overlay, `Enter` opens its options, `Ctrl+D` marks it as favorite, `Esc` clears the search.

### The Overlay Options page

One page holds the options of every overlay: the overlays on the left (by category, a filled dot when the overlay is on), the options of the selected one in the middle, and a live preview on the right drawn with the values you have not applied yet (on narrower windows, `Preview` at top shows it beside the options, `Esc` or its `✕` hides it). The switch at top turns the overlay on or off at once, as on the `Overlays` page (never a pending change); `Test on Screen` at top shows the race situation chosen under the preview on the overlays on screen. It also opens from a right-click on an overlay on screen, `Find Option` and the command palette (`Ctrl+K`).

- **Sections**: `General`, `Position & Layout`, `Font`, then one section per item the overlay shows (Speed, Time Gap, Fuel Level Bar...). The on/off switch of an item is in the title of its section; while it is off, its options are dimmed. Click a section title to fold it (`Collapse All` / `Expand All` at top), its `Reset` button puts its options back to default. `Display Order` is a list moved with the arrows. Relative, Standings and Rivals have a `Columns` list instead: the columns from left to right, each one with its on/off switch, moved by drag or arrows, and their live preview shows a sample race.
- **Only the options of the design in use** are shown: switch `Enable Classic Layout` and the options of the classic layout show up at once.
- **Search** (`Ctrl+F`): in `This overlay` or in `Every overlay`, for example `opacity` to set it for all overlays in one list. The `Filters` menu (number of filters on in its name): `Changed Only` lists the options changed from their default (in one overlay or in all of them; the overlay list shows how many options each overlay has changed), `Used Only` hides the options doing nothing with the current values (dimmed), `Advanced Options` for overlays with a simple mode.
- **Numbers have limits**: the tooltip of a number shows the values allowed (`Allowed: 0 - 4000`). A value out of range in a preset file is brought within the limits when the preset loads; `Check Preset` (Presets page menu) lists and repairs them.
- **Live preview**: the race situation menu (`Racing`, `Yellow & Blue Flags`, `In Pits`, `Damage`, `Rain`) shows what an overlay draws only then; `Test on Screen` (top of the page) shows it on the overlays on screen for 10 seconds; `Other Design` draws the same values with the other design (modern or classic).
- **`...` button of an option**: `Reset to Default`, `Apply to All Overlays` (the value goes to every overlay having this option: font, opacity, update interval, theme...), `Copy Option Name`.
- **Changes stay pending** until `Apply`, for as many overlays as you like: the overlay list shows how many changes each one has, `Undo` / `Redo` (`Ctrl+Z` / `Ctrl+Y`) and `Discard` are in the bar at the bottom. An invalid value is marked at once with the reason and blocks `Apply` (click the message to show it). `Apply` saves the preset once and restarts only the overlays you changed.
- **Dashboard HUD** (formerly Black box): its own sections, `Advanced Options` in `Filters` (simple mode shows the main items), the `Theme` menu (default or colorblind safe colors), display profile (options set by the profile say so; changing one switches to `Custom`) with the `Profile` menu to save the items shown as one of your own profiles, and a click on a part of the picture shows its options.

### Find any option

Press `Ctrl+F` (`Settings` > `Find Option…`) to search all options of all overlays, modules, the preset and the application, in English or in the current language (accents and case are ignored). Best matches come first, with the current value of each option; a dot marks options changed from their default.

- Click a result (or `Enter`) to open it: the `Overlay Options` page or the `Settings` page scrolled to the option (a module option: the category of the module).
- On / off options have a switch in the list (or `Space`): the change is saved and applied at once, with `Undo` in the notice; `Ctrl+Z` / `Ctrl+Y` undo and redo switches and resets of the page.
- The chips (`Overlays`, `Modules`, `Preset`, `Application`) narrow the results; `Changed Only` lists every option set apart from its default, even without search words.
- Right-click a result: `Reset to Default`, `Copy Option Key` (the name used in setting files and in the [settings reference](https://github.com/Keenny38/NeoPedal/blob/master/docs/customization.md)).

### Units

`Settings` > `Units` sets units for distance, fuel, speed, temperature, pressures, power and weight. Overlays, tools and the web dashboard follow them.

## Data modules

Modules compute the data that overlays show: lap times and deltas, fuel and energy, positions of every car, tyre and brake wear, track map... The `Modules` category of the `Settings` page (first category of `In the loaded preset`; `Modules` in the Overlays card of the Home page, or the command palette `Ctrl+K`) shows each module as a card:

- what it computes, its state (`Running`, `Disabled`, or `Error` when it could not start: see the log) and its update interval;
- how many enabled overlays use its data (their names in the tooltip) and the modules using it. A module turned off that enabled overlays or modules need is flagged in orange, and `Enable Them` at the top of the page turns those modules back on;
- its switch and its gear (`Options…`: update intervals and options of the module, in their category of the same Settings page). Right-click a card to reset its saved data: delta best (Delta), fuel and energy delta (Fuel), consumption history (Stint), sector best (Sectors), track map (Mapping).

Search, `All` / `Active` / `Inactive` and the keyboard work as on the `Overlays` page. `Performance` at the top opens the `Overlay Performance` page (CPU time of each overlay and module, game data state). Keep every module on unless you know an overlay does not need it.

## Presets

A preset stores the layout and options of all overlays and modules. You can keep several (one per car class, one for VR...), load one with a double-click on the `Preset` page, and have one loaded automatically per class or track. See [Presets and Settings](Presets-and-Settings.md).

## Hotkeys

The `Hotkeys` category of the `Settings` page (after `Notification`) binds keys, mouse buttons and game controller buttons (wheel, button box, joystick, gamepad) to commands: show, hide or lock the overlay, reload or switch presets, restart the API, spectate the next driver, cycle the delta best source, show the next Dashboard HUD incident, bring the main window in front of the game and focus it, even from the tray (`show_main_window`), drive the [Broadcast Director](Broadcast-Director.md#hotkeys) (`director_*` commands), turn any overlay or module on or off, load a given preset, restart or quit the app.

Hotkeys are always on: a command runs as soon as a key is bound to it (no key is bound by default). Click the key button of a command (or `Enter` on its row) and press a key or key combination, a mouse button (middle, back, forward) or a controller button, then `Save`. `Clear` in the dialog empties it; preset commands also ask which preset to load. If the key is already used, the dialog names the command using it and its button becomes `Assign Anyway`.

Commands are in sections (`General`, `Spectate`, `Broadcast Director`, `Preset`, `Overlays`, `Module`) that fold, each with how many keys are assigned. `Search hotkeys` (`Ctrl+F`, `/` or just typing) finds a command, `Assigned only` lists bound commands only. Commands sharing a key are marked on both rows (`Same key as: …`). The cross of a row (or `Delete`) clears its key, `Clear All` every key: both at once, with `Undo` in the toast (`Ctrl+Z`).

Combinations with `Ctrl`, `Shift` and `Alt` work with any key, also the ones the app itself uses (`Ctrl+K`, `Ctrl+1`, `Ctrl+S`, `Alt`, `Enter`, `Space`...): while the key binding dialog is shown, keys only go to it (`Esc` still closes it), and held modifiers are shown (`Ctrl + Shift + …`) until you press the key. Modifiers must match exactly: a hotkey on `C` does not run with `Ctrl+C`, and `Ctrl+A` does not run with `Ctrl+Shift+A`.

Controller buttons are named after the device and the button (`Joy1 Button 5`, `Joy2 Pov Up` for the d-pad), and can be combined with `Ctrl`, `Shift` or `Alt`. Up to 16 devices with 128 buttons and a d-pad each are read, virtual controllers included: buttons of the SimHub Control Mapper (`SimHub Controller Remapper Bridge` or vJoy device) are bound like any other, and a short pulse (rotary encoder step) is still caught. A button held when the key binding dialog opens (a switch or rotary of a button box) is ignored until released. The device number follows the order Windows gives to controllers: if you plug or unplug a device, check the bindings again.

Hotkeys do not block the key or button for other programs (the game still sees it). On Linux, only controller buttons work (`/dev/input/js*`), keyboard hotkeys are not supported. The same commands can be run by other programs (Stream Deck, SimHub...): see [Connections](Connections.md#remote-control).

## Spectate

The `Spectate` tab of the [Broadcast Director](Broadcast-Director.md) page shows the data of another driver in your overlays (delta, fuel, timing, inputs...): in a replay, or while watching a session. It works with Le Mans Ultimate and rFactor 2: the page opens on this tab when the selected game API is not Le Mans Ultimate (the `Director` tab needs Le Mans Ultimate).

1. Turn on the switch at top right (or click any driver: spectate mode turns on).
2. Click a driver to follow it. The card on top shows the driver followed, with place, class, car and best lap; the arrows (`Alt+Left`, `Alt+Right`) go to the previous or next driver by place, `Stop` follows nobody.
3. Search by driver, car or class, keep one class with its chip, sort by position or name. Your own car is marked `You`.

Drivers are read only while the tab is shown. The `spectate_mode`, `spectate_next_driver` and `spectate_previous_driver` hotkeys do the same from the game. Open it from `Broadcast` (navigation bar or its `More`), the `Tools` menu or the command palette; the `Spectate Mode Enabled` notice and Home check open this tab. To cast a whole race with cameras and graphics, use the `Director` tab (LMU).

## Next steps

- [Overlays](Overlays.md): designs, themes and the list of all overlays.
- [Telemetry Viewer](Telemetry-Viewer.md): analyze your laps.
- [Race Calculator](Race-Calculator.md): plan fuel, energy and tyres.
- [Troubleshooting](Troubleshooting.md) if something does not show up.
