def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_percent(value, default=0.0):
    try:
        return float(str(value).replace("%", "").strip()) / 100
    except (TypeError, ValueError):
        return default


def parse_usdt(value, default=0.0):
    try:
        return float(str(value).replace("USDT", "").strip())
    except (TypeError, ValueError):
        return default


def ema(values, period):
    if not values:
        return 0.0

    multiplier = 2 / (period + 1)
    result = values[0]

    for value in values[1:]:
        result = (value - result) * multiplier + result

    return result


def ema_series(values, period):
    if not values:
        return []

    multiplier = 2 / (period + 1)
    result = [float(values[0])]
    for value in values[1:]:
        result.append((float(value) - result[-1]) * multiplier + result[-1])
    return result


def macd(values, fast_period=12, slow_period=26, signal_period=9):
    if len(values) < slow_period + signal_period:
        return None

    fast = ema_series(values, fast_period)
    slow = ema_series(values, slow_period)
    macd_line = [fast[index] - slow[index] for index in range(len(values))]
    signal_line = ema_series(macd_line, signal_period)
    value = macd_line[-1]
    signal = signal_line[-1]
    return {
        "value": value,
        "signal": signal,
        "histogram": value - signal,
    }


def rsi(values, period=14):
    if len(values) <= period:
        return 50.0

    gains = []
    losses = []

    for index in range(1, len(values)):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def percent_change(current, previous):
    current = to_float(current)
    previous = to_float(previous)

    if previous == 0:
        return 0.0

    return ((current - previous) / previous) * 100


def safe_round(value, digits=4):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0
