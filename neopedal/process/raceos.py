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
Player Driver Rank & Safety Rank of RaceControl (Le Mans Ultimate online service), without Qt

The game menu stopped keeping ranks in its storage file (2026-10): it reads them online. Same requests
as the game menu (web UI of the game, "RaceOS" client):
    1. GET <game Rest API>/rest/profile/getAuthSessionTicket -> {"authSessionTicket": "<Steam ticket>"}
    2. POST https://raceos.gg/authenticate {"token": ticket, "game": "lmu", "platform": "steam"}
       -> {"accessToken", "expiresAt", "player": {name, driverRank, safetyRank, profile, platforms...}, "banned"}
       (404: no RaceControl account)
Ranks of that sign in answer are current (checked live 2026-10-17: DR progress 36.96, elo 2060), while
GET //api/v1/player with the token gives an old copy (progress 40 of 5 days before, elo 0): signed in again
to read them, at most once every SIGN_IN_SECONDS (the game menu asks a new ticket every 25 minutes too).
Few requests (2026-11-02: RaceControl refused this connection for hours, the game's too, after many reads of the
Upcoming Races page): paced, counted per minute & per hour, nothing asked for an hour or more after a 403.
Other drivers (token of a sign in, header "Game-Authorization: Bearer <accessToken>"):
    POST api/v1/players {"usernames": [...]} -> [player] (same values as race entry lists; daily race lists give
    only races to come, not the one being run: never used)
No websocket. Reads only, but registering to an online event (or leaving it) when the player asks it (Upcoming
Races page, same requests as the game menu). Ticket & token never logged nor saved (memory only).
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import IO, TYPE_CHECKING, Any, NamedTuple

from ..validator import json_loads_checked
from .driver_ranks import DriverRanks, parse_rank, ranks_data, ranks_from_data

if TYPE_CHECKING:
    import http.client
    import urllib.request

RACEOS_HOST = "raceos.gg"
RACEOS_URL = f"https://{RACEOS_HOST}"
AUTH_URL = f"{RACEOS_URL}/authenticate"
TICKET_ROUTE = "/rest/profile/getAuthSessionTicket"
TIMEOUT = 8.0  # seconds per connection step & read
REQUEST_SECONDS = 20.0  # answer (status, headers, body) read in this time at most once request sent
MAX_BODY = 4 * 1024 * 1024
RETRY_SECONDS = 300.0  # first wait after a failed sign in, doubled each failure
RETRY_MAX_SECONDS = 3600.0
NO_ACCOUNT_SECONDS = 3600.0  # no RaceControl account: tried again this late
TOKEN_MARGIN = 120.0  # token of a sign in used for other reads until this many seconds before it expires
TOKEN_SECONDS = 1500.0  # token lifetime if expiry not given or unreadable (game menu: new ticket every 25 min)
FLIGHT_WAIT = 30.0  # caller waits this long at most for the answer of a sign in running (its requests time out sooner)
REQUEST_GAP = 1.0  # seconds between two requests at least, whichever thread asks (RaceControl refused a burst: 403)
MAX_PER_MINUTE = 12  # requests sent at most in any 60 s (RaceControl blocked this connection after bursts)
MAX_PER_HOUR = 120  # requests sent at most in any hour (2026-11-02: connection blocked for hours, the game's too)
SIGN_IN_SECONDS = 600.0  # answer of a sign in (player ranks included) reused this long: no new sign in before
BLOCK_SECONDS = 3600.0  # 403 (connection refused by RaceControl): nothing asked this long, doubled each time
BLOCK_MAX_SECONDS = 6 * 3600.0  # longest wait after a 403 (kept on disk: app restarts never ask sooner)
HOUR_WARNING = 60  # requests in the last hour told in the error log (half of MAX_PER_HOUR: something asks too much)
FORBIDDEN_PATHS = ("api/v1/event/entries/",)  # 403 there: that list only (some events), not the connection
BUSY_SECONDS = 300.0  # no request after a 429 (too many requests) without Retry-After, doubled each 429 until a read
NOT_SENT = -1  # status of send: request not sent (MAX_PER_MINUTE / MAX_PER_HOUR reached, RaceControl asks to wait)
NOT_SIGNED = -2  # status of send: request not sent, not signed in (game not running, sign in failed)

logger = logging.getLogger(__name__)

# (method, url, body, headers, timeout) -> status (0: no answer), body (a Reply gives the Retry-After header too)
Http = Callable[[str, str, bytes | None, dict[str, str], float], tuple[int, bytes]]


class Reply(tuple[int, bytes]):
    """Status & body of an answer (equal to the (status, body) tuple) with its Retry-After header ("" if none)"""

    retry_after: str

    def __new__(cls, status: int, body: bytes, retry_after: str = "") -> Reply:
        reply = super().__new__(cls, (status, body))
        reply.retry_after = retry_after
        return reply


def retry_after(value: str, now: float) -> float | None:
    """Seconds to wait of a Retry-After header (seconds, or HTTP date: now in seconds since epoch), at most
    RETRY_MAX_SECONDS, None if not given or unreadable"""
    from email.utils import parsedate_to_datetime

    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text) if text.isdigit() else parsedate_to_datetime(text).timestamp() - now
    except (TypeError, ValueError, OverflowError):
        return None
    return min(max(seconds, 0.0), RETRY_MAX_SECONDS)


def is_raceos_url(url: str) -> bool:
    """Address of RaceControl over HTTPS (redirect allowed to it only: requests carry the sign in token)"""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        return parts.scheme == "https" and parts.hostname == RACEOS_HOST and parts.port in (None, 443)
    except ValueError:  # invalid port
        return False


def _opener(seconds: float) -> urllib.request.OpenerDirector:
    """urllib opener: answers read within seconds of each connection, redirects followed only to https://raceos.gg
    (urllib keeps the Game-Authorization header on a redirect to another host, and allows http)"""
    import http.client
    import urllib.request

    from ..http_limits import deadline_response_class

    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str,
                             headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
            if not is_raceos_url(newurl):
                logger.info("RACEOS: redirect to another address refused")
                return None  # redirect answer handed to caller (HTTPError), never followed
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    class Connection(http.client.HTTPSConnection):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.response_class = deadline_response_class(seconds)  # type: ignore[assignment]

    class Handler(urllib.request.HTTPSHandler):
        def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
            return self.do_open(Connection, req, context=self._context)  # type: ignore[attr-defined]

    return urllib.request.build_opener(Redirect, Handler)


def http_request(method: str, url: str, body: bytes | None, headers: dict[str, str],
                 timeout: float) -> tuple[int, bytes]:
    """Status & body of request (error statuses too), (0, b"") if no answer, or not read in REQUEST_SECONDS, or body
    above MAX_BODY; https://raceos.gg only (redirects too)"""
    import http.client
    import urllib.error
    import urllib.request

    from ..http_limits import read_body

    if not is_raceos_url(url):
        return 0, b""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _opener(max(REQUEST_SECONDS, timeout)).open(request, timeout=timeout) as response:
            return response.status, read_body(response.read, MAX_BODY, response.length)
    except urllib.error.HTTPError as error:
        retry = str(error.headers.get("Retry-After") or "") if error.headers is not None else ""
        try:
            return Reply(error.code, read_body(error.read, MAX_BODY, getattr(error.fp, "length", None)), retry)
        except (OSError, ValueError, http.client.HTTPException):
            return Reply(error.code, b"", retry)
        finally:
            error.close()
    except (OSError, ValueError, http.client.HTTPException):  # offline, refused, cut off, too large (ValueError)
        return 0, b""


def _json(body: bytes) -> Any:
    try:
        return json_loads_checked(body)
    except (ValueError, RecursionError):  # UnicodeDecodeError too, RecursionError: nested too deeply
        return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse_time(value: Any) -> float:
    """Seconds since epoch of ISO 8601 text (UTC if no zone), NaN if unreadable"""
    if not isinstance(value, str) or not value:
        return math.nan
    text = value.strip().replace("Z", "+00:00")
    head, dot, rest = text.partition(".")  # nanoseconds given (Go service): microseconds kept
    if dot:
        digits = len(rest) - len(rest.lstrip("0123456789"))
        text = f"{head}.{rest[:min(digits, 6)]}{rest[digits:]}"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return math.nan
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.timestamp()


class SignIn(NamedTuple):
    """Answer of a sign in: token for other reads, its expiry (seconds since epoch), ranks of player, RaceControl id
    & name of player ("" if not given: leaderboard place around the player), time answered (seconds since epoch)"""

    token: str
    expiry: float
    player: DriverRanks | None
    player_id: str = ""
    player_name: str = ""
    time: float = 0.0


def player_ranks(data: Any) -> DriverRanks | None:
    """Ranks of RaceControl player data, None if no rank"""
    if not isinstance(data, dict):
        return None
    driver, safety = parse_rank(data.get("driverRank")), parse_rank(data.get("safetyRank"))
    if driver is None and safety is None:
        return None
    profile = data.get("profile")
    if not isinstance(profile, dict):
        profile = {}
    steam_id = ""
    platforms = data.get("platforms")
    if isinstance(platforms, list):
        for platform in platforms:
            if isinstance(platform, dict) and platform.get("platform") == "steam":
                value = platform.get("id")
                steam_id = str(value) if isinstance(value, int) and not isinstance(value, bool) else _text(value)
                break
    return DriverRanks(
        name=_text(data.get("name")) or _text(data.get("username")),
        steam_id=steam_id,
        driver_id=_text(data.get("id")),
        nationality=_text(profile.get("nationality")),
        driver=driver,
        safety=safety,
        badge=_text(profile.get("badge")),
    )


class _Flight:
    """Sign in running (one at a time): callers asking meanwhile wait for its answer"""

    __slots__ = ("done", "generation", "result")

    def __init__(self, generation: int):
        self.generation = generation  # client generation when started: answer dropped if changed meanwhile
        self.done = threading.Event()
        self.result: SignIn | None = None


class RaceOSClient:
    """RaceControl reads: player ranks of a sign in with a new game ticket (current ranks, answer reused for
    SIGN_IN_SECONDS), token of last sign in kept a while for other reads (blocking calls)

    One sign in at a time (single flight): a caller asking while one runs waits for its answer instead of signing in
    again. Lock held only to read & change state, never during requests (forget & token never wait for the network).

    Args:
        ticket: function giving a Steam ticket of the game ("" if game not running or no answer).
        http: request function (tests).
        clock: time function (tests).
        user_agent: User-Agent header.
        wall_clock: time function giving seconds since epoch (tests).
        block_file: file keeping the end of a wait after a 403 across app restarts ("" if none).
        ranks_file: file keeping your ranks of the last sign in & its time: an app restart signs in only once they
            are old ("" if none; never the token).
    """

    def __init__(self, ticket: Callable[[], str], http: Http = http_request,
                 clock: Callable[[], float] = time.monotonic, user_agent: str = "NeoPedal",
                 wall_clock: Callable[[], float] = time.time, pace: bool | None = None,
                 sleep: Callable[[float], None] = time.sleep, block_file: str = "", ranks_file: str = ""):
        self._ticket = ticket
        self._http = http
        self._pace_requests = http is http_request if pace is None else pace  # service itself: requests paced
        self._sleep = sleep
        self._pace_lock = threading.Lock()  # requests counted one after another (never held while waiting)
        self._next_request = -math.inf  # clock time the next request may be sent
        self._sent: deque[float] = deque()  # clock times of requests sent in the last hour (paced only)
        self._refusing = False  # last request not sent (limits): next refusal not logged again
        self._block_wait = BLOCK_SECONDS
        self._blocked = False  # busy because RaceControl refused this connection (403), not asked to wait (429)
        self._block_file = block_file
        self._clock = clock
        self._wall_clock = wall_clock
        self._user_agent = user_agent
        self._lock = threading.Lock()
        self._account = ""  # game account (SteamID64) of last sign in
        self._retry_time = -1.0  # no sign in before this time (failed before), -1 if none
        self._retry_wait = RETRY_SECONDS
        self._refused_wait = RETRY_SECONDS  # wait after a refused new token, doubled each refusal until a read
        self._sign_ins = 0  # sign ins done: token of a request new (signed in for it) or kept
        self._signed: SignIn | None = None  # last sign in (token kept in memory only)
        self._signed_time = -math.inf  # clock time of last sign in
        self._generation = 0  # incremented when state forgotten (option off, account switched): running sign in dropped
        self._flight: _Flight | None = None  # sign in running, None if none
        self._busy_time = -1.0  # no request before this time (429: too many requests), -1 if none
        self._busy_wait = BUSY_SECONDS
        self.no_account = False  # service answered: no RaceControl account for this player
        self._load_block()
        self._ranks_file = ranks_file
        self._saved_ranks = self._load_ranks()  # (game account, seconds since epoch, ranks) of last sign in, or None

    def _load_ranks(self) -> tuple[str, float, DriverRanks] | None:
        if not self._ranks_file:
            return None
        from ..userfile import read_json

        data = read_json(self._ranks_file, default=None, dict_only=True)
        if not isinstance(data, dict):
            return None
        account, stamp, ranks = data.get("account"), data.get("time"), ranks_from_data(data.get("ranks"))
        if (not isinstance(account, str) or not isinstance(stamp, (int, float)) or isinstance(stamp, bool)
                or not math.isfinite(stamp) or ranks is None):
            return None
        return account, float(stamp), ranks

    def _save_ranks(self, account: str, ranks: DriverRanks) -> None:
        """Ranks of a sign in kept on disk with its time (never the token or ticket)"""
        stamp = self._wall_clock()
        self._saved_ranks = (account, stamp, ranks)
        if not self._ranks_file:
            return
        from ..userfile import write_json

        try:
            write_json(self._ranks_file, {"account": account, "time": stamp, "ranks": ranks_data(ranks)},
                       fsync=False, raise_error=True)
        except (OSError, TypeError, ValueError) as error:
            logger.info("RACEOS: ranks of the sign in not saved: %s", error)

    def _load_block(self) -> None:
        """Wait after a 403 of an earlier run still running: nothing asked until its end"""
        if not self._block_file:
            return
        from ..userfile import read_json

        data = read_json(self._block_file, default=None, dict_only=True)
        if not isinstance(data, dict):
            return
        until, wait = data.get("until"), data.get("wait")
        if not isinstance(until, (int, float)) or isinstance(until, bool) or not math.isfinite(until):
            return
        if isinstance(wait, (int, float)) and not isinstance(wait, bool) and math.isfinite(wait):
            self._block_wait = min(max(float(wait), BLOCK_SECONDS), BLOCK_MAX_SECONDS)  # refused again: longer
        left = until - self._wall_clock()
        if left <= 0:  # wait over (file removed once answered)
            return
        self._busy_time = self._clock() + min(left, BLOCK_MAX_SECONDS)
        self._blocked = True
        logger.warning("RACEOS: requests refused by RaceControl before (403): none sent for %d min", round(left / 60))

    def _save_block(self, seconds: float, wait: float) -> None:
        """End of a wait after a 403 kept on disk (seconds from now, next wait), file removed once read again"""
        if not self._block_file:
            return
        import os

        from ..userfile import write_json

        try:
            if seconds > 0:
                write_json(self._block_file, {"until": self._wall_clock() + seconds, "wait": wait}, fsync=False,
                           raise_error=True)
            elif os.path.exists(self._block_file):
                os.remove(self._block_file)
        except (OSError, TypeError, ValueError) as error:
            logger.info("RACEOS: wait after a refusal not saved: %s", error)

    def _unblock(self) -> None:
        """Answer read: waits after refusals back to their first length"""
        with self._lock:
            was_blocked = self._blocked or self._block_wait != BLOCK_SECONDS
            self._refused_wait = RETRY_SECONDS
            self._busy_wait = BUSY_SECONDS
            self._block_wait, self._blocked = BLOCK_SECONDS, False
        if was_blocked:
            self._save_block(0.0, BLOCK_SECONDS)

    def forget(self) -> None:
        """Failures, token & saved ranks forgotten (option turned off): signed in at once next time (sign in running
        dropped)"""
        with self._lock:
            self._account, self._retry_time, self._retry_wait = "", -1.0, RETRY_SECONDS
            self._refused_wait = RETRY_SECONDS
            self._signed = None
            self._saved_ranks = None
            self._generation += 1
        if self._ranks_file:
            import os

            try:
                if os.path.exists(self._ranks_file):
                    os.remove(self._ranks_file)
            except OSError as error:
                logger.info("RACEOS: saved ranks not removed: %s", error)

    def fetch(self, account: str = "", max_age: float = SIGN_IN_SECONDS) -> DriverRanks | None:
        """Ranks of player of game account in use ("" if unknown) of a sign in made less than max_age seconds ago
        (this run or an earlier one, 0: new sign in), None if not read (offline, game not running, no account,
        waiting after a failure)"""
        found = self.fetch_timed(account, max_age)
        return found[0] if found is not None else None

    def fetch_timed(self, account: str = "", max_age: float = SIGN_IN_SECONDS) -> tuple[DriverRanks, float] | None:
        """Ranks of fetch & time of the sign in that read them (seconds since epoch: a sign in reused, or saved by an
        earlier run, is older than now), None if not read"""
        with self._lock:
            signed = self._signed
            if (signed is not None and signed.player is not None and self._same_account(account)
                    and self._clock() - self._signed_time < max_age):
                return signed.player, signed.time
        saved = self._saved_ranks
        if saved is not None and saved[0] == account and 0 <= self._wall_clock() - saved[1] < max_age:
            return saved[2], saved[1]
        signed = self.sign_in(account, max_age)
        return (signed.player, signed.time) if signed is not None and signed.player is not None else None

    def room(self) -> int:
        """Requests that could be sent now within MAX_PER_MINUTE & MAX_PER_HOUR (0 while busy): background reads
        stop below a reserve instead of asking requests refused (the player's own asks keep room)"""
        if self.busy_for() > 0:
            return 0
        if not self._pace_requests:
            return MAX_PER_MINUTE
        with self._pace_lock:
            now = self._clock()
            hour = sum(1 for sent in self._sent if now - sent < 3600.0)
            minute = sum(1 for sent in reversed(self._sent) if now - sent < 60.0)
        return max(min(MAX_PER_MINUTE - minute, MAX_PER_HOUR - hour), 0)

    def busy_for(self) -> float:
        """Seconds RaceControl asked to wait (429: too many requests) or refuses this connection (403) still to run,
        0 if none: nothing asked meanwhile, sign ins included"""
        return max(self._busy_time - self._clock(), 0.0) if self._busy_time >= 0 else 0.0

    def blocked_for(self) -> float:
        """Seconds still to run while RaceControl refuses this connection (403 on a sign in or a read), 0 if not"""
        return self.busy_for() if self._blocked else 0.0

    def _block(self) -> None:
        """RaceControl refuses this connection (403): nothing asked for BLOCK_SECONDS, doubled at each new refusal
        (the game is refused too meanwhile: asking again would keep the block going)"""
        with self._lock:
            wait = self._block_wait
            self._busy_time = self._clock() + wait
            logger.warning("RACEOS: requests refused by RaceControl (403): none sent for %d min", round(wait / 60))
            self._block_wait = min(wait * 2, BLOCK_MAX_SECONDS)
            self._blocked = True
            next_wait = self._block_wait
        self._save_block(wait, next_wait)

    @property
    def player(self) -> tuple[str, str]:
        """RaceControl id & name of the player of the last sign in, ("", "") if not signed in"""
        signed = self._signed
        return (signed.player_id, signed.player_name) if signed is not None else ("", "")

    def token(self, account: str = "") -> str:
        """Token of last sign in while valid, else of a new sign in, "" if not signed in"""
        with self._lock:
            signed = self._signed
            if (signed is not None and self._same_account(account)
                    and self._wall_clock() < signed.expiry - TOKEN_MARGIN):
                return signed.token
        signed = self.sign_in(account)
        return signed.token if signed is not None else ""

    def _same_account(self, account: str) -> bool:
        """Account asked for is the one of the last sign in: "" (game account not located yet) stands for the one in
        use, never for another; first account asked for after a sign in made without one taken as its own (ticket of
        the game account in use), so that the next other one is a switch (lock held)"""
        if account and not self._account and self._signed is not None:
            self._account = account
        return not account or not self._account or account == self._account

    def sign_in(self, account: str = "", max_age: float = SIGN_IN_SECONDS) -> SignIn | None:
        """Sign in with a game ticket: last one if made less than max_age (SIGN_IN_SECONDS at most) ago, else a new
        one (answer of the one running if any), None if not signed in"""
        if self.busy_for() > 0:  # asked to wait or connection refused: no sign in either
            return None
        with self._lock:
            if not self._same_account(account):  # Steam account switched: failures & token of other account forgotten
                self._retry_time, self._retry_wait = -1.0, RETRY_SECONDS
                self._refused_wait = RETRY_SECONDS
                self._signed = None
                self.no_account = False
                self._generation += 1
            if account:
                # Account located after a sign in made without it (ticket of the game account in use): sign in kept.
                # Readers asking with "" (Upcoming Races before the game folder was found) and with the account
                # (ranks) used to switch back and forth: a new sign in each time, the answer running dropped
                self._account = account
            now = self._clock()
            signed = self._signed
            if (signed is not None and now - self._signed_time < min(max_age, SIGN_IN_SECONDS)
                    and self._wall_clock() < signed.expiry - TOKEN_MARGIN):  # recent sign in: its answer reused
                return signed
            if self._retry_time >= 0 and now < self._retry_time:
                return None
            flight = self._flight
            joined = flight is not None and flight.generation == self._generation
            if not joined:  # none running (or one of a forgotten state, its answer dropped): this one signs in
                flight = self._flight = _Flight(self._generation)
        assert flight is not None
        if joined:
            flight.done.wait(FLIGHT_WAIT)
            return flight.result
        try:
            flight.result = self._sign_in(now, flight.generation)
        finally:
            with self._lock:
                if self._flight is flight:
                    self._flight = None
            flight.done.set()
        return flight.result

    def _sign_in(self, now: float, generation: int) -> SignIn | None:
        """Requests of a sign in started at clock time now (no lock held), answer applied unless state forgotten
        meanwhile (generation changed)"""
        try:
            ticket = self._ticket()
        except Exception:  # any error of game request: game not running
            ticket = ""
        if not ticket:  # game not running: tried again next time asked (no wait, no request made)
            return None
        body = json.dumps({"token": ticket, "game": "lmu", "platform": "steam"}).encode()
        headers = {"User-Agent": self._user_agent, "Accept": "application/json",
                   "Content-Type": "application/json"}
        if not self._pace("sign in"):
            return None
        status, answer = self._http("POST", AUTH_URL, body, headers, TIMEOUT)
        if status == 403:  # connection refused (live 2026-11-02: 403 on every request, the game's too)
            self._block()
        data = _json(answer) if status == 200 else None
        token = _text(data.get("accessToken")) if isinstance(data, dict) else ""
        signed = None
        if token:
            assert isinstance(data, dict)
            expiry = parse_time(data.get("expiresAt"))
            if math.isnan(expiry):
                expiry = self._wall_clock() + TOKEN_SECONDS
            player = data.get("player")
            player = player if isinstance(player, dict) else {}
            signed = SignIn(token, expiry, player_ranks(player), _text(player.get("id")), _text(player.get("name")),
                            self._wall_clock())
        with self._lock:
            if generation != self._generation:  # option turned off or account switched meanwhile: answer dropped
                return None
            if status == 404:
                logger.info("RACEOS: no RaceControl account for this player")
                self.no_account = True
                self._retry_time = now + NO_ACCOUNT_SECONDS
                return None
            if signed is None:
                logger.info("RACEOS: sign in failed (status %s)", status)
                self._retry_time = now + self._retry_wait
                self._retry_wait = min(self._retry_wait * 2, RETRY_MAX_SECONDS)
                return None
            self._retry_time, self._retry_wait = -1.0, RETRY_SECONDS
            self.no_account = False
            self._signed = signed
            self._signed_time = now
            self._sign_ins += 1
            account = self._account
        self._unblock()
        if signed.player is not None:
            self._save_ranks(account, signed.player)
        return signed

    def _pace(self, what: str) -> bool:
        """Wait until REQUEST_GAP after the last request (blocking: worker threads), whichever thread asks; False
        (not sent) once MAX_PER_MINUTE were sent in the last 60 s or MAX_PER_HOUR in the last hour, or while busy;
        each request logged with the count of the last hour (what: request name)"""
        if not self._pace_requests:
            return True
        waited = math.nan  # next request time slept for: sent once awake unless another thread sent meanwhile
        while True:
            with self._pace_lock:
                wait = self._next_request - self._clock()
                if wait <= 0 or self._next_request == waited:
                    count = self._count_request()
                    break
                waited = self._next_request
            self._sleep(wait)  # lock never held while sleeping: room() (GUI thread) never waits for it
        if not count:
            return False
        if count == HOUR_WARNING:
            logger.warning("RACEOS: %d requests to RaceControl in the last hour", count)
        else:
            logger.info("RACEOS: %s (%d requests in the last hour)", what, count)
        return True

    def _count_request(self) -> int:
        """Request counted as sent now (pace lock held): count of the last hour, 0 if not sent (limits, waiting)"""
        now = self._clock()
        while self._sent and now - self._sent[0] >= 3600.0:
            self._sent.popleft()
        minute = sum(1 for sent in reversed(self._sent) if now - sent < 60.0)
        if minute >= MAX_PER_MINUTE or len(self._sent) >= MAX_PER_HOUR or self.busy_for() > 0:
            if not self._refusing:  # told once until a request is sent again (no line per request refused)
                logger.info("RACEOS: requests not sent (%d sent in the last minute, %d in the last hour, or "
                            "waiting)", minute, len(self._sent))
            self._refusing = True
            return 0
        self._refusing = False
        self._sent.append(now)
        self._next_request = now + REQUEST_GAP
        return len(self._sent)

    def get(self, path: str, account: str = "") -> Any:
        """JSON answer of a RaceControl GET (path without leading slash), None if not read"""
        return self._request("GET", path, None, account)

    def get_status(self, path: str, account: str = "") -> tuple[int, Any]:
        """Status & JSON answer of a RaceControl GET (path without leading slash), (NOT_SENT, None) if not sent
        (limits, asked to wait), (NOT_SIGNED, None) if not signed in, (0, None) if sent without answer"""
        return self._exchange("GET", path, None, account)

    def post(self, path: str, payload: Any, account: str = "") -> Any:
        """JSON answer of a RaceControl POST of JSON payload (path without leading slash), None if not read"""
        return self._request("POST", path, json.dumps(payload).encode(), account)

    def send(self, method: str, path: str, payload: Any, account: str = "") -> tuple[int, Any]:
        """Status & JSON answer (error answers too: RaceControl tells why) of a request the player asked (event
        registration), (NOT_SENT, None) if not sent (limits, RaceControl asks to wait), (NOT_SIGNED, None) if not
        signed in, (0, None) if sent without answer"""
        return self._exchange(method, path, json.dumps(payload).encode(), account)

    def _request(self, method: str, path: str, body: bytes | None, account: str) -> Any:
        status, answer = self._exchange(method, path, body, account)
        return answer if status == 200 else None

    def _exchange(self, method: str, path: str, body: bytes | None, account: str) -> tuple[int, Any]:
        if self.busy_for() > 0:  # RaceControl asked to wait: nothing asked (rest of a read stopped)
            return NOT_SENT, None
        sign_ins = self._sign_ins
        token = self.token(account)
        new_token = self._sign_ins != sign_ins
        if not token:  # sign in refused meanwhile (403, 429): not sent either
            return (NOT_SENT if self.busy_for() > 0 else NOT_SIGNED), None
        headers = {"User-Agent": self._user_agent, "Accept": "application/json",
                   "Game-Authorization": f"Bearer {token}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if not self._pace(f"{method} {path.split('?', 1)[0]}"):
            return NOT_SENT, None
        reply = self._http(method, f"{RACEOS_URL}/{path}", body, headers, TIMEOUT)
        status, answer = reply
        # 403 on the entry list of some events: that list only, also with a token just made (sign in answered)
        forbidden_list = status == 403 and path.startswith(FORBIDDEN_PATHS)
        if status == 429:  # too many requests: Retry-After waited, else BUSY_SECONDS doubled each time
            wait = retry_after(getattr(reply, "retry_after", ""), self._wall_clock())
            with self._lock:
                self._busy_time = self._clock() + (self._busy_wait if wait is None else wait)
                self._busy_wait = min(self._busy_wait * 2, RETRY_MAX_SECONDS)
        elif status == 401 or (status == 403 and new_token and not forbidden_list):  # token refused: sign in again
            with self._lock:
                self._signed = None
                if new_token:  # refused at once (account refused by the service): waited, never every check
                    self._retry_time = self._clock() + self._refused_wait
                    self._refused_wait = min(self._refused_wait * 2, RETRY_MAX_SECONDS)
        # 403 with a token used before: that request forbidden (entry list of some events), token kept (signing in
        # again at once was refused too)
        elif status == 200:
            self._unblock()
        if status == 403 and not forbidden_list:
            self._block()
        if status != 200:
            logger.info("RACEOS: %s not read (status %s)", path.split("?", 1)[0], status)
        return status, _json(answer)


def game_ticket(fetch: Callable[[str], tuple[int, bytes]]) -> str:
    """Steam ticket of game (fetch: GET route of game Rest API -> status & body), "" if none"""
    status, body = fetch(TICKET_ROUTE)
    data = _json(body) if status == 200 else None
    return _text(data.get("authSessionTicket")) if isinstance(data, dict) else ""
