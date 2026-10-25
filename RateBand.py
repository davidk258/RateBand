# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""RateBand: store an FX rate only if validators agree within a fixed band."""

from dataclasses import dataclass
from genlayer import *
import json

SCALE = 100000000
BAND_BPS = 100
CURRENCIES = ("USD", "EUR", "GBP", "CHF", "JPY")
SOURCE = "https://api.frankfurter.dev/v1/latest?from="


@allow_storage
@dataclass
class Observation:
    obs_id: str
    caller: Address
    pair: str
    scaled_rate: str
    rate_date: str


class RateBand(gl.Contract):
    next_id: u256
    observations: TreeMap[str, Observation]
    latest: TreeMap[str, str]

    def __init__(self):
        self.next_id = u256(0)

    def _view(self, item: Observation):
        return {
            "obs_id": item.obs_id,
            "caller": str(item.caller),
            "pair": item.pair,
            "scaled_rate": item.scaled_rate,
            "rate_date": item.rate_date,
            "scale": str(SCALE),
            "band_bps": str(BAND_BPS),
        }

    @gl.public.view
    def get_observation(self, obs_id: str):
        obs_id = "" if obs_id is None else str(obs_id).strip()
        if obs_id not in self.observations:
            raise gl.vm.UserError("unknown observation")
        return self._view(self.observations[obs_id])

    @gl.public.view
    def get_latest(self, base: str, quote: str):
        pair = self._pair(base, quote)
        if pair not in self.latest:
            raise gl.vm.UserError("no observation for this pair")
        return self._view(self.observations[self.latest[pair]])

    def _pair(self, base: str, quote: str):
        base = "" if base is None else str(base).strip().upper()
        quote = "" if quote is None else str(quote).strip().upper()
        if base not in CURRENCIES or quote not in CURRENCIES:
            raise gl.vm.UserError("currency must be USD, EUR, GBP, CHF, or JPY")
        if base == quote:
            raise gl.vm.UserError("base and quote must differ")
        return base + "/" + quote

    @gl.public.write
    def record(self, base: str, quote: str):
        pair = self._pair(base, quote)
        base, quote = pair.split("/", 1)
        url = SOURCE + base + "&to=" + quote

        def leader_fn():
            response = gl.nondet.web.get(url)
            code = getattr(response, "status_code", 200)
            if code != 200:
                raise gl.vm.UserError("rate source unavailable")
            body = response.body
            text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
            data = json.loads(text)
            rate = float(data["rates"][quote])
            scaled = int(round(rate * SCALE))
            day = str(data["date"])
            if scaled <= 0 or len(day) != 10:
                raise gl.vm.UserError("rate source returned an unusable value")
            return str(scaled) + "|" + day

        def _text(value):
            if isinstance(value, str):
                return value
            if isinstance(value, bytes):
                return value.decode("utf-8", "replace")
            data = getattr(value, "calldata", None)
            if isinstance(data, bytes):
                return data.decode("utf-8", "replace")
            if data is not None:
                return str(data)
            return str(value)

        def _scaled(value):
            text = _text(value)
            number = text.split("|", 1)[0]
            digits = ""
            for ch in number:
                if ch.isdigit():
                    digits += ch
                elif digits:
                    break
            if digits == "":
                return 0
            return int(digits)

        def validator_fn(leader_result):
            leader_scaled = _scaled(leader_result)
            if leader_scaled <= 0:
                return False
            try:
                own_scaled = _scaled(leader_fn())
            except Exception:
                return False
            if own_scaled <= 0:
                return False
            diff = abs(leader_scaled - own_scaled)
            return diff * 10000 <= leader_scaled * BAND_BPS

        agreed = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        scaled_rate, rate_date = str(agreed).split("|", 1)

        caller = gl.message.sender_address
        obs_id = str(self.next_id + u256(1))
        self.next_id = self.next_id + u256(1)
        self.observations[obs_id] = Observation(
            obs_id=obs_id,
            caller=caller,
            pair=pair,
            scaled_rate=scaled_rate,
            rate_date=rate_date,
        )
        self.latest[pair] = obs_id
