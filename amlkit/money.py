"""Google Money value type: ISO 4217 currency, integer units, integer nanos.

Non-negative only. Nanos range: 0..999,999,999 (9 decimal digits).
Uses Decimal internally — never float — to avoid rounding drift.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_NANOS_PER_UNIT = 1_000_000_000


class Money:
    __slots__ = ("currency_code", "units", "nanos")

    def __init__(self, currency_code: str, units: int, nanos: int) -> None:
        if units < 0:
            raise ValueError("Money must be non-negative (units < 0)")
        if not (0 <= nanos < _NANOS_PER_UNIT):
            raise ValueError(
                f"nanos must be in 0..999,999,999, got {nanos}"
            )
        self.currency_code = currency_code
        self.units = units
        self.nanos = nanos

    @classmethod
    def from_decimal(cls, amount: Decimal, currency_code: str) -> Money:
        if amount < 0:
            raise ValueError("Money must be non-negative")
        units = int(amount)
        nanos = int((amount - units) * _NANOS_PER_UNIT)
        return cls(currency_code, units, nanos)

    @classmethod
    def from_float(cls, amount: float, currency_code: str) -> Money:
        return cls.from_decimal(Decimal(str(amount)), currency_code)

    def to_decimal(self) -> Decimal:
        return Decimal(self.units) + Decimal(self.nanos) / Decimal(_NANOS_PER_UNIT)

    def to_aed_str(self) -> str:
        d = self.to_decimal()
        return f"{d:,.2f}"

    def _total_nanos(self) -> int:
        return self.units * _NANOS_PER_UNIT + self.nanos

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return (
            self.currency_code == other.currency_code
            and self.units == other.units
            and self.nanos == other.nanos
        )

    def __lt__(self, other: Money) -> bool:
        return self._total_nanos() < other._total_nanos()

    def __le__(self, other: Money) -> bool:
        return self._total_nanos() <= other._total_nanos()

    def __gt__(self, other: Money) -> bool:
        return self._total_nanos() > other._total_nanos()

    def __ge__(self, other: Money) -> bool:
        return self._total_nanos() >= other._total_nanos()

    def __add__(self, other: Money) -> Money:
        if self.currency_code != other.currency_code:
            raise ValueError(
                f"Cannot add {self.currency_code} and {other.currency_code}: currency mismatch"
            )
        total_nanos = self.nanos + other.nanos
        carry = total_nanos // _NANOS_PER_UNIT
        return Money(
            self.currency_code,
            self.units + other.units + carry,
            total_nanos % _NANOS_PER_UNIT,
        )

    def __repr__(self) -> str:
        return f"Money({self.currency_code!r}, {self.units}, {self.nanos})"
