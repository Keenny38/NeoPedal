#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Durations, counts and limits of the requests the app sends to online services (RaceControl, ranks), in one place

Every value says why it is what it is: the rhythm at which the data changes, or a limit of the service (RaceControl
refused this connection for hours on 2026-11-02 after bursts of requests, the game's too: few requests, paced).
The modules keep their own names for these values (`READ_SECONDS` of race_schedule_info...), set from here.
Plain numbers only, no import at load: safe to import from anywhere. Economy mode (option
enable_online_requests_economy) stretches the intervals and halves the hourly cap, see `stretch` & `hour_cap`.
"""

ECONOMY_FACTOR = 2.0  # economy mode: every interval of a read of RaceControl lasts twice as long
ECONOMY_HOUR_CAP = 60  # economy mode: requests to RaceControl in any hour, at most (half of RACEOS_MAX_PER_HOUR)


def economy() -> bool:
    """Economy mode of the requests to online services (option enable_online_requests_economy)"""
    try:
        from .setting import cfg

        return bool(cfg.application.get("enable_online_requests_economy", False))
    except Exception:  # config not loaded yet (import time, tools): normal
        return False


def stretch(seconds: float) -> float:
    """Interval of a read of RaceControl: seconds, twice as long in economy mode (fewer requests, older data)"""
    return seconds * ECONOMY_FACTOR if economy() else seconds


def hour_cap(cap: int) -> int:
    """Requests to RaceControl allowed in any hour: cap, at most ECONOMY_HOUR_CAP in economy mode"""
    return min(cap, ECONOMY_HOUR_CAP) if economy() else cap


# RaceControl client (process/raceos.py): sign in, pace and waits
RACEOS_RETRY_SECONDS = 300.0  # first wait after a failed sign in, doubled each failure
RACEOS_RETRY_MAX_SECONDS = 3600.0  # longest wait after failed sign ins (the wait doubles from RETRY_SECONDS)
RACEOS_NO_ACCOUNT_SECONDS = 3600.0  # no RaceControl account: tried again this late
RACEOS_TOKEN_MARGIN = 120.0  # token of a sign in used for other reads until this many seconds before it expires
RACEOS_TOKEN_SECONDS = 1500.0  # token lifetime if expiry not given or unreadable (game menu: new ticket every 25 min)
RACEOS_FLIGHT_WAIT = 30.0  # caller waits this long at most for the answer of a sign in running (its requests time out sooner)
RACEOS_REQUEST_GAP = 1.0  # seconds between two requests at least, whichever thread asks (RaceControl refused a burst: 403)
RACEOS_MAX_PER_MINUTE = 12  # requests sent at most in any 60 s (RaceControl blocked this connection after bursts)
RACEOS_MAX_PER_HOUR = 120  # requests sent at most in any hour (2026-11-02: connection blocked for hours, the game's too)
RACEOS_SIGN_IN_SECONDS = 600.0  # answer of a sign in (player ranks included) reused this long: no new sign in before
RACEOS_BLOCK_SECONDS = 3600.0  # 403 (connection refused by RaceControl): nothing asked this long, doubled each time
RACEOS_BLOCK_MAX_SECONDS = 6 * 3600.0  # longest wait after a 403 (kept on disk: app restarts never ask sooner)
RACEOS_HOUR_WARNING = 60  # requests in the last hour told in the error log (half of MAX_PER_HOUR: something asks too much)
RACEOS_BUSY_SECONDS = 300.0  # no request after a 429 (too many requests) without Retry-After, doubled each 429 until a read
RACEOS_ETAG_ENTRIES = 12  # answers kept with their ETag at most (the routes of the schedule), oldest read dropped first
RACEOS_ETAG_MAX_BYTES = 512 * 1024  # an answer larger than this is not kept with its ETag

# Online races to come & online results (race_schedule_info.py)
SCHEDULE_READ_SECONDS = 1800.0  # read again this often (Home card, race watch: no page needed)
SCHEDULE_LIVE_READ_SECONDS = 600.0  # this often while the Upcoming Races page shows (live; reads every 2 min got this connection refused by RaceControl for hours, the game's too, 2026-11-02)
SCHEDULE_RETRY_SECONDS = 300.0  # read failed (game closed, no answer): tried again this late
SCHEDULE_FAILED_MAX_SECONDS = 3600.0  # signed in but nothing answered (RaceControl down): the wait doubles each time up to this
SCHEDULE_FAIL_STREAK = 3  # routes in a row not answered after which the rest of a read is not asked (RaceControl down: 5xx or no answer on every route; a single route may answer 500, special events when there are none)
SCHEDULE_GAME_LISTS_AGE = 3600.0  # cars & tracks of the game asked again this late (owned DLC)
SCHEDULE_KEEP_ANSWER_SECONDS = 7200.0  # route not answered (500, no answer, read cut by a 429): its last answer kept this long
SCHEDULE_SLOW_ROUTE_SECONDS = 3600.0  # routes that rarely change (weekly series last days, co-op events months, championship rounds a week): read again this late; a refresh asked on the page reads them all
SCHEDULE_FRESH_MARGIN = 30.0  # answer younger than its read interval minus this not asked again (tab switch, refresh)
SCHEDULE_MAX_SECONDS = 6 * 3600.0  # daily schedule: start times of one UTC day, read again after midnight UTC (or this late)
SCHEDULE_ROUND_MAX_SECONDS = 6 * 3600.0  # active championships: rounds change when the current one ends (Tuesday 05:00 UTC, seen 2026-11-03); registrations & attempts move slowly: read again at that moment, or this late
SCHEDULE_ROUND_MARGIN = 60.0  # read again this long after a round ended (RaceControl moves to the next one)
SCHEDULE_FORCE_SECONDS = 60.0  # refresh asked on the page: read again at once at most this often
SCHEDULE_FRIENDS_SECONDS = 600.0  # friends list asked again this late
SCHEDULE_RESULTS_SETTLED_SECONDS = 86400.0  # an online race over for a day no longer changes (rank changes & penalties settled): kept in memory, never on disk (names of drivers)
SCHEDULE_RESULTS_KEEP = 40  # races kept at most in pages (oldest read dropped first)
SCHEDULE_RACES_KEEP = 12  # races with their laps kept at most
SCHEDULE_REGISTERED_SECONDS = 600.0  # registration (or leave) from the page told on its start this long at most

# Upcoming Races page (ui/quick/schedule_backend.py)
PAGE_PERSONAL_SECONDS = 300.0  # driver stats files read again this often while the page shows
PAGE_MANUAL_SECONDS = 300.0  # Read Again asks RaceControl for the tab shown at most this often (like the ranks Refresh):
PAGE_BOARD_CACHE_SECONDS = 600.0  # leaderboard pages read again this late (going back & forth: no new ask)
PAGE_UNRANKED_SECONDS = 10800.0  # your place in leaderboards where you are not ranked read again this late
PAGE_PLACES_SECONDS = 7200.0  # your places in the weekly leaderboards read again this often while shown (a place moves when you or others drive it: 2 requests a leaderboard, the biggest part of the page's requests at 30 minutes)
PAGE_PLACES_DRIVEN_SECONDS = 8 * 86400.0  # leaderboards asked only for tracks you drove this long ago at most (a week of the leaderboard, one day more): you cannot be ranked on a track you did not drive
PAGE_LIVE_FIELD_SECONDS = 600.0  # starts this close: their field (drivers, ranks) read while the page shows (once at LIVE_FIELD_EVERY, 18 requests an hour at 15 minutes for 3 tiers)
PAGE_LIVE_FIELD_MISSES = 2  # live reads in a row not answered: that race's field no longer asked
PAGE_LIVE_FIELD_EVERY = 598.0  # seconds between two reads of a field (checked every tick: TICK_MS); count of the

# Driver & Safety Rank of the player (process/driver_ranks.py)
RANKS_CHECK_SECONDS = 5.0  # storage file modification time checked this often
RANKS_LOCATE_SECONDS = 60.0  # game folder & player looked for again this often while not found (game installed)
RANKS_LOCATE_FOUND_SECONDS = 600.0  # looked for again this often once found (game moved, other Steam user)
RANKS_ONLINE_RESULTS_DELAYS = (180.0, 900.0)  # the last one signs in again (sign in answer reused 10 min, see raceos)
RANKS_ONLINE_SECONDS = 1800.0  # few sign ins: RaceControl refused this connection for hours after many (2026-11-02)
RANKS_ONLINE_GAME_SECONDS = 60.0  # game looked for this often while not running
RANKS_ONLINE_RETRY_SECONDS = 600.0  # read again this late once a read failed (offline)
RANKS_ONLINE_MANUAL_SECONDS = 300.0  # read asked by the player (Refresh) at most this often: few sign ins

# Ranks of the other drivers of an online session (process/field_ranks.py)
FIELD_BATCH = 50  # names per request
FIELD_CHECK_SECONDS = 30.0  # server joined & ranks due checked this often
FIELD_JOIN_SECONDS = 15.0  # driver joining the session asked at once, at most one request this often (arrivals grouped)
FIELD_KEEP_DRIVERS = 500  # ranks kept of drivers no longer in session (shown at once if they come back), at most
FIELD_KEEP_SECONDS = 3600.0  # ranks of a driver read again this late (few requests: RaceControl refuses many)
FIELD_RESULTS_DELAYS = (300.0,)  # every driver read again this long after a session ended
FIELD_MISSING_SECONDS = 3600.0  # driver without RaceControl profile asked again this late
FIELD_RETRY_SECONDS = 300.0  # drivers of a read not sent (RaceControl limits, waiting) or not answered asked again this late

# Community lap times sheet (ui/quick/stats_common.py)
SHEET_REFERENCE_MAX_AGE = 24 * 3600  # seconds before cached lap time reference is downloaded again
SHEET_REFERENCE_RETRY_SECONDS = 3600  # seconds after a failed download before the next page opening asks again (3 attempts each: a page opened often while the service is down or rate limiting sent 3 requests every time)
