# Upcoming Races

The **Upcoming Races** page lists the online races of Le Mans Ultimate to come, as the game menu shows them: daily races, weekly and special events, championships, co-op events and the servers hosted by players.

Open it with the `Races` entry of the navigation bar, the `Tools` menu, the command palette (`Ctrl+K`, type "races"), or the `Next Races` card of the Home page.

## Where the races come from

The races are read from **RaceControl**, the online service of Le Mans Ultimate, signed in with the game exactly as the game menu does (the same sign in as the online Driver Rank & Safety Rank). So:

- **Le Mans Ultimate must be running** (in the menus is enough) for a new read. The page reads again every 10 minutes while it is shown (every 30 minutes for the Home card; championships, weekly & special events and co-op every hour, hosted servers only while their tab shows), and `Read Again` (`F5`) reads everything at once, at most once a minute. Starting the app again asks nothing at once while the last read is recent. RaceControl refuses a connection that asks too much (the game's too, so you could no longer race online): after a refusal the app asks nothing for an hour or more, even after a restart.
- The last races read are kept on disk (`.race_schedule.json` in the global config folder) and shown while the game is closed; the header tells when they were read.
- The option `enable_online_driver_ranks` (Settings > Application, on by default) turns online reading on or off for both the ranks and the races. When it is off, the page tells so with a button to the option.

What is kept on disk is trimmed: no names of other players, no server addresses or passwords. Details read on demand (field of a race, championship sessions, co-op leaderboard) are never kept.

## Tabs

| Tab | What it shows |
|---|---|
| **Daily Races** | Every daily race of each tier (Beginner, Intermediate, Advanced) and how often it starts, as cards, a compact list or a **timeline** of the next 6 hours (one line per race) |
| **Weekly & Special** | Weekly races and special events with their starts, registrations and whether you are registered |
| **Championships** | Championships running or to come: Safety Rank needed, drivers registered, current round and its track, attempts per round, dropped rounds, points multiplier, next sessions, all rounds by number (current one highlighted, hover one for its track and dates). `Sessions & Practice` reads the sessions of the round with the drivers registered to each, your attempts used and the practice servers (players) |
| **Co-op** | Endurance events to drive with friends and until when they are open. `Leaderboard` reads the best teams and your team (position, drivers, class, fastest and average lap) |
| **Hosted Servers** | Public servers hosted by players: name, track and its logo, session, players (with how full the server is), region, classes, a lock when it needs a password, cars or track you don't own; sorted by players, region or name |

Each race card tells the next start (`Tomorrow` for the next day) and the time to it (accent within 15 minutes, pulsing in the last 2 minutes), the track (with its logo), the classes, **your personal best and community level of each class you drove there** (from Driver Stats, `Never driven here` else), the sessions and their length, the **time on track** at the race start, the **weather** from start to end (temperature, rain changes), fixed or open setup, tyre warmers, drivers registered, grid size, when registrations open, and every following start (`+n more` shows them all).

## Menu of a race

Click a race, a championship, a co-op event or a hosted server (card or line) for its menu, in three groups: the race (register, field, leaderboard), planning (reminder, calendar), then your own data on the track:

- **Driver Stats**, **Recorded Laps** (Telemetry viewer) and **Prepare Race** (Race Calculator) for the class you drove on the track, or one submenu each listing your classes when you drove several; `Track Stats` and `Prepare Race in Calculator` when you never drove there. Hosted servers have these entries only.
- **Remind Me Before** (start time): 5, 10 or 30 min, and the time of `number_of_minutes_before_race_reminder` (`Settings` > `Notification`, 10 by default, also the reminder set when you register), the one set shown on the entry; a notification of the app and a message of the tray icon (shown over the game) before the start, whichever page is open, kept after a restart (`race_reminders.json`). `number_of_minutes_before_last_race_reminder` adds a last reminder (for example 30 then 2 minutes before; `0`, the default, for none). A reminder offers `Remind Me in 2 Min`, flashes the app button in the taskbar, shows in the `Race Notifications` overlay and on the Web Dashboard, and plays a sound (`race_reminder_sound`: by default only while Windows hides its notifications, over a full screen game for example; `race_reminder_sound_file_name` for a sound file of your own). A bell shows on the race. `Cancel Reminder` removes it.
- **Show Field**: drivers registered to the next start, by class, Driver Rank and Safety Rank (counts only).
- **Practice Servers** (daily, weekly and special races): the practice servers open for the race, as the game lists them: players and until when, with the time they were read. Read only when asked (click again to read them again); join them from the game. Practice+ servers (RaceControl Pro) are not listed.
- **Export to Calendar…**: an `.ics` file of the next start, or of every round to come of a championship.
- **Weekly Leaderboard** (championships: **Round Leaderboard**): the fastest laps of the week of this race, as in the game menu, **every page** (100 drivers a page, first / previous / next / last, or `Page Up` / `Page Down` / `Home` / `End`), all classes or one, opened at the page of your place, `Show My Place` to go back to it, where you stand ("Top 7% · 2.104 s to the first"). `Friends` shows you and your RaceControl friends ranked this week; `Find a driver…` (type a name, `Enter`) jumps to the page of a driver; click a line for the driver's profile (nationality, Driver & Safety Rank, badge); export the page to CSV. Each line: rank, driver, car, team, tyres, class, Driver & Safety Rank, sectors, lap time and gap. Pages read a moment ago are shown again without asking RaceControl. RaceControl publishes no leaderboard for some championships (team endurance): the window tells so.

Championship cards also have `Your Progress`: the rounds you drove in this championship and your best place in each.

Hosted servers tell their sessions (length, time on track) and weather. The daily races timeline shows 3, 6 or 12 hours, with a line at the time now. Races and championships your Safety Rank does not open yet are dimmed when `Open to Me` is off.

## Your place

Each race and championship round you drove this week shows **your place in its weekly leaderboard** ("#1,204 of 17,836"); click it to open the leaderboard at your page. Places are read again every 30 minutes while the page is shown.

## Filters

- **Search** by race, track, tier or class.
- **Class** chips: races and servers with one of the classes chosen.
- **Owned Cars & Tracks**: hides what needs a car or a track you don't own (DLC), from the car and track lists of the running game.
- **Open to Me** (on by default): hides the races your Safety Rank does not open, and the servers that are full or need a password.

## Safety Rank

As in the game menu, a race opens to you when your **Safety Rank** is at least the one its tier needs (daily races: Bronze for Beginner, Silver for Intermediate, Gold for Advanced; weekly, special events and championships give their own). Your Safety Rank shows in the header (`SR unknown` until it was read once: start Le Mans Ultimate with online ranks on); a race it does not open has a **lock** next to the rank needed.

## Your online races

The online races you drove are on the [Results & Replays](Race-Results.md) page, `Online` list.

## Home page

The `Next Races` card of the Home page shows the three next races your Safety Rank opens, each with its start and the time to it, track and logo, classes, tier and length, your place in its weekly leaderboard, the reminder you set and your registration; click it to open the page.
