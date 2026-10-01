from decimal import Decimal

_PER_MILLION = Decimal(1_000_000)
_PRECISION = Decimal("0.00000001")


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price: Decimal,
    output_price: Decimal,
) -> Decimal:
    """Cost in USD given prices per 1M tokens."""
    cost = (input_tokens * input_price + output_tokens * output_price) / _PER_MILLION
    return cost.quantize(_PRECISION)
