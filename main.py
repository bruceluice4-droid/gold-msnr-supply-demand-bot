import os
import time
import requests
from datetime import datetime, timezone

# ============================================================
# XAUUSD MSnR + SUPPLY & DEMAND TELEGRAM BOT
# ============================================================

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "XAU/USD"
SCAN_INTERVAL = 300  # 5 minutes

TIMEFRAMES = {
    "1D": "1day",
    "4H": "4h",
    "1H": "1h",
    "30M": "30min",
    "15M": "15min",
    "5M": "5min",
}

last_signal = None


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=20
        )

        print("Telegram:", response.status_code)

    except Exception as e:
        print("Telegram error:", e)


# ============================================================
# TWELVE DATA
# ============================================================

def get_candles(interval, outputsize=120):

    if not TWELVE_DATA_API_KEY:
        print("Twelve Data API key missing.")
        return []

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": SYMBOL,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "order": "ASC"
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        data = response.json()

        if "values" not in data:
            print("Twelve Data error:", data)
            return []

        candles = []

        for c in data["values"]:
            try:
                candles.append({
                    "time": c["datetime"],
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                })
            except:
                pass

        return candles

    except Exception as e:
        print("Market data error:", e)
        return []


# ============================================================
# BASIC FUNCTIONS
# ============================================================

def average_range(candles, period=14):

    if len(candles) < period + 1:
        return 0

    ranges = []

    for c in candles[-period:]:
        ranges.append(c["high"] - c["low"])

    return sum(ranges) / len(ranges)


def is_bullish(c):
    return c["close"] > c["open"]


def is_bearish(c):
    return c["close"] < c["open"]


def body(c):
    return abs(c["close"] - c["open"])


def candle_range(c):
    return c["high"] - c["low"]


# ============================================================
# MSnR
# Major Support & Resistance
# ============================================================

def find_support(candles):

    if len(candles) < 20:
        return None

    recent = candles[-60:]

    lows = sorted(
        [c["low"] for c in recent]
    )

    if not lows:
        return None

    return lows[0]


def find_resistance(candles):

    if len(candles) < 20:
        return None

    recent = candles[-60:]

    highs = sorted(
        [c["high"] for c in recent],
        reverse=True
    )

    if not highs:
        return None

    return highs[0]


def nearest_support(candles, price):

    levels = []

    for i in range(2, len(candles) - 2):

        if (
            candles[i]["low"] < candles[i-1]["low"]
            and candles[i]["low"] < candles[i+1]["low"]
            and candles[i]["low"] < candles[i-2]["low"]
            and candles[i]["low"] < candles[i+2]["low"]
        ):
            level = candles[i]["low"]

            if level < price:
                levels.append(level)

    if not levels:
        return None

    return max(levels)


def nearest_resistance(candles, price):

    levels = []

    for i in range(2, len(candles) - 2):

        if (
            candles[i]["high"] > candles[i-1]["high"]
            and candles[i]["high"] > candles[i+1]["high"]
            and candles[i]["high"] > candles[i-2]["high"]
            and candles[i]["high"] > candles[i+2]["high"]
        ):
            level = candles[i]["high"]

            if level > price:
                levels.append(level)

    if not levels:
        return None

    return min(levels)


# ============================================================
# SUPPLY & DEMAND
# ============================================================

def find_demand_zone(candles):

    if len(candles) < 10:
        return None

    for i in range(len(candles) - 4, 2, -1):

        base = candles[i-1]
        move1 = candles[i]
        move2 = candles[i+1]

        avg = average_range(candles[:i], 14)

        if avg == 0:
            continue

        # Base followed by strong bullish departure
        if (
            is_bullish(move1)
            and is_bullish(move2)
            and
            (move2["close"] - base["low"]) > avg * 1.2
        ):
            return {
                "high": base["high"],
                "low": base["low"]
            }

    return None


def find_supply_zone(candles):

    if len(candles) < 10:
        return None

    for i in range(len(candles) - 4, 2, -1):

        base = candles[i-1]
        move1 = candles[i]
        move2 = candles[i+1]

        avg = average_range(candles[:i], 14)

        if avg == 0:
            continue

        # Base followed by strong bearish departure
        if (
            is_bearish(move1)
            and is_bearish(move2)
            and
            (base["high"] - move2["close"]) > avg * 1.2
        ):
            return {
                "high": base["high"],
                "low": base["low"]
            }

    return None


# ============================================================
# LIQUIDITY SWEEP
# ============================================================

def bullish_liquidity_sweep(candles):

    if len(candles) < 10:
        return False

    current = candles[-1]

    previous_lows = [
        c["low"] for c in candles[-8:-1]
    ]

    lowest = min(previous_lows)

    return (
        current["low"] < lowest
        and current["close"] > lowest
    )


def bearish_liquidity_sweep(candles):

    if len(candles) < 10:
        return False

    current = candles[-1]

    previous_highs = [
        c["high"] for c in candles[-8:-1]
    ]

    highest = max(previous_highs)

    return (
        current["high"] > highest
        and current["close"] < highest
    )


# ============================================================
# STRUCTURE SHIFT
# ============================================================

def bullish_structure_shift(candles):

    if len(candles) < 10:
        return False

    recent = candles[-6:]

    previous_high = max(
        c["high"] for c in candles[-10:-3]
    )

    return recent[-1]["close"] > previous_high


def bearish_structure_shift(candles):

    if len(candles) < 10:
        return False

    recent = candles[-6:]

    previous_low = min(
        c["low"] for c in candles[-10:-3]
    )

    return recent[-1]["close"] < previous_low


# ============================================================
# ANALYSIS
# ============================================================

def analyze_market():

    data = {}

    for name, interval in TIMEFRAMES.items():

        candles = get_candles(interval)

        if len(candles) < 30:
            print(f"Not enough {name} data.")
            return None

        data[name] = candles

    current_price = data["5M"][-1]["close"]

    score_buy = 0
    score_sell = 0

    reasons_buy = []
    reasons_sell = []

    # --------------------------------------------------------
    # DAILY + 4H MSnR
    # --------------------------------------------------------

    daily = data["1D"]
    four_h = data["4H"]
