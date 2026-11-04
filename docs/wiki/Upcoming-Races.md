# Upcoming Races

The **Upcoming Races** page lists the daily online races of Le Mans Ultimate to come, by tier (Beginner, Intermediate, Advanced), with your personal best on their track.

Open it with the `Races` entry of the navigation bar, the `Tools` menu, the command palette (`Ctrl+K`, type "races"), or the `Next Races` card of the Home page.

## Where the races come from

The races are read from the **public home page of RaceControl** (www.racecontrol.gg), as a web browser shows it: no game ticket, no account, nothing about you is sent. The page is read once an hour at most (`Read Again`, `F5`, reads it at once, at most every 5 minutes), shown while the game is closed, and the header tells when it was read (`Last read: 5 min ago`).

- That page gives the **title, tier, length, track and start times** of the next daily races (about the next 9 hours). Registration, fields, practice servers, leaderboards, weekly and special events, championships, co-op events and hosted servers are not on it: see them in the game.
- **RaceOS** (the online service of the game, read with the game's Steam ticket) is never asked: a developer of Le Mans Ultimate said third-party apps must not call it, only shared memory and the game's files are fine.
- The option `enable_public_race_schedule` (Settings > Application > Online, on by default) turns this reading on or off. When it is off, the page tells so with a button to the option.
- Tracks are named from the track list of the running game (local Rest API), which also tells the tracks you don't own.

## Races

The daily races of each tier and how often a race of the tier starts, as cards, a compact list or a **timeline** of the next 3, 6 or 12 hours (one line per race, a line at the time now).

Each race card tells the next start (`Tomorrow` for the next day) and the time to it (accent within 15 minutes, pulsing in the last 2 minutes), the track (with its logo), **your personal best and community level of each class you drove there** (from Driver Stats, `Never driven here` else), the race length, a track you don't own, the following starts (`+n more` shows them all) and the reminder you set.

## Menu of a race

Click a race (card, line or timeline block) for its menu, in three groups: the race, planning, then your own data on the track:

- **Register in the Game**: brings Le Mans Ultimate to the front (or starts it), where you register in its Online menu.
- **Remind Me Before** (start time): 5, 10 or 30 min, and the time of `number_of_minutes_before_race_reminder` (`Settings` > `Notification`, 10 by default), the one set shown on the entry; a notification of the app and a message of the tray icon (shown over the game) before the start, whichever page is open, kept after a restart (`race_reminders.json`). A reminder follows its start when the race moves it, and is removed (and told) when its start is gone.
- **Export to Calendar…**: an `.ics` file of the start.
- **Driver Stats**, **Recorded Laps** (Telemetry viewer) and **Prepare Race** (Race Calculator) for the class you drove on the track, or one submenu each listing your classes when you drove several; `Track Stats` and `Prepare Race in Calculator` when you never drove there.

The menu of a timeline block acts on that start (reminder, calendar).

## Filters

- **Search** by race, track or tier.
- **Owned Cars & Tracks**: hides the races on a track you don't own (DLC), from the track list of the running game.

## Requests

`Requests` lists the requests the app sent since it started to GitHub (updates), the community lap times sheet and the public RaceControl site: route and answer only (never a name or an address), how many in the last hour. Kept in memory, nothing saved.

## Your online races

The online races you drove are on the [Results & Replays](Race-Results.md) page, `Online` list, read from the results files of the game.

## Home page

The `Next Races` card of the Home page shows the three next daily races, each with its start and the time to it, track and logo, tier and length, the reminder you set and when the races were read; click it to open the page.
