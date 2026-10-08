"""Two slide tables as images: the five rule rows positive in both periods, and ten strategies that failed.

The tables are mutually exclusive: no rule variant in the first table appears in the second.
Numbers come from tables/fomc_strategy_results.csv and the other strategy tests summarized in
reports/trading_strategies.md (mean executable bp per trade, number of trades in brackets;
2015-2022 = development, 2023-2026 = holdout).

Run: python -m scripts.make_trading_tables
Writes figures/trading_tables/table_five_positive.png and table_ten_failed.png
"""

from __future__ import annotations

import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils.config import PROJECT_ROOT

FIG = PROJECT_ROOT / "figures" / "trading_tables"
HEADER, HEADER_TEXT, BORDER, STRIPE = "#dce8f5", "#1b2a41", "#b8c4d2", "#f6f8fb"

FIVE = {
    "title": "Five FOMC rules made money in both periods, but none is robust",
    "columns": ["#", "Rule", "Market", "What it does", "2015-2022", "2023-2026", "Why it is not robust"],
    "widths": [0.03, 0.20, 0.08, 0.22, 0.09, 0.09, 0.29],
    "rows": [
        ["1", "Price momentum, held to +30 min", "ES", "Follow a large first-5-minute move; exit 2:30 p.m.",
         "+1.7 bp (16)", "+1.5 bp (5)", "Tiny profit; 95% range -10 to +14 bp includes zero"],
        ["2", "Large move + thin book -> follow, held to +10 min", "ZN",
         "Follow a large move while the book is still thin; exit 2:10 p.m.", "+1.8 bp (4)", "+5.6 bp (1)",
         "One recent trade; the same rule loses -32 bp per trade in NQ"],
        ["3", "Large move + refilled book -> fade", "ES", "Bet a large move reverses once liquidity is back; exit 2:20 p.m.",
         "+6.7 bp (2)", "+20.5 bp (1)", "Three trades in eleven years"],
        ["4", "Same as #3, held to +10 min", "ES", "As #3; exit 2:10 p.m.", "+5.3 bp (2)", "+15.2 bp (1)",
         "Same three meetings as #3; fails the 3-trade minimum"],
        ["5", "Same as #3, held to +10 min", "ES+NQ+ZN", "As #4, across all three markets", "+3.0 bp (11)",
         "+18.5 bp (2)", "Two recent trades; 95% range -1 to +11 bp includes zero"],
    ],
    "footer": "Mean profit per trade after bid/ask costs (number of trades). Three of the five are the same "
              "'fade after the book refills' idea. Across 68 rule results, about this many come out positive in both "
              "periods by chance.",
}

TEN = {
    "title": "Ten strategies that did not work",
    "columns": ["#", "Strategy", "Hypothesis", "Result (2015-2022 -> 2023-2026)", "Why it failed"],
    "widths": [0.03, 0.21, 0.24, 0.27, 0.25],
    "rows": [
        ["1", "Late momentum (+5 to +20 min)", "News is still being absorbed, so large moves continue",
         "ES -9 -> -6 bp, NQ -12 -> -15 bp per trade", "Large moves slightly reverse instead"],
        ["2", "Large move + thin book -> follow (NQ)", "Missing liquidity means the move isn't finished",
         "-31 -> -37 bp per trade (95% CI -53 to -10)", "Opposite: stressed NQ moves reverse"],
        ["3", "NQ: thin depth only / wide spread only", "One side of NQ's book carries the signal",
         "-41 bp (no recent trades) / -30 -> -37 bp", "Both lose; same reversal as #2"],
        ["4", "ES + NQ agree on a large move -> follow", "Two markets confirming each other",
         "ES -9 -> -10 bp, NQ -11 -> -15 bp", "Confirmation does not stop the reversal"],
        ["5", "ES + NQ + ZN all agree -> follow", "A coherent three-market reaction continues",
         "About 0 -> -10 to -49 bp (1 recent trade)", "Rare and loses"],
        ["6", "ES/NQ relative value", "A large NQ-vs-ES gap closes by +20 min",
         "-4 to +3 -> -3 to +4 bp", "About zero"],
        ["7", "Statement vs press conference", "The press conference reverses or extends the statement move",
         "Reversed before 2023, not after", "Relationship flipped; no edge"],
        ["8", "ES-NQ pairs trading (one-second)", "Temporary divergences converge",
         "Spread reverts ~0.05 bp; costs ~0.6 bp per trade", "Loses after costs, also on normal days"],
        ["9", "ES-NQ lead-lag (one-second)", "One index predicts the other's next move",
         "Both move within the same second", "No exploitable lead"],
        ["10", "Thin book -> fade on macro releases (432)", "Same pattern on a much larger sample",
         "Worked in 2015-2022, gone from 2023", "Did not survive the later period"],
    ],
    "footer": "Mean profit per trade after bid/ask costs unless stated. FOMC rules decide at 2:05 p.m. and exit "
              "at 2:20 p.m. No rule in this table appears in the five-rule table.",
}


def wrap(text: str, width_frac: float, bold: bool = False, total_chars: int = 172) -> str:
    chars = int(width_frac * total_chars * (0.86 if bold else 1.0))
    return "\n".join(textwrap.wrap(text, max(4, chars)))


def draw(spec: dict, path) -> None:
    cols, widths = spec["columns"], spec["widths"]
    rows = [[wrap(c.replace("->", "\u2192"), w, bold=i == 1) for i, (c, w) in enumerate(zip(r, widths))]
            for r in spec["rows"]]
    heights = [max(c.count("\n") + 1 for c in r) for r in rows]
    unit = 0.30
    header_h = 0.55
    body_h = sum(h * unit + 0.22 for h in heights)
    fig_h = header_h + body_h + 1.6
    fig = plt.figure(figsize=(18, fig_h))
    ax = fig.add_axes([0.02, 0.0, 0.96, 1.0])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    ax.text(0.5, fig_h - 0.35, spec["title"], ha="center", va="top", fontsize=22, fontweight="bold", color=HEADER_TEXT)
    top = fig_h - 1.0
    x = [0.0]
    for w in widths:
        x.append(x[-1] + w)
    ax.add_patch(plt.Rectangle((0, top - header_h), 1, header_h, facecolor=HEADER, edgecolor=BORDER))
    for i, c in enumerate(cols):
        ax.text((x[i] + x[i + 1]) / 2, top - header_h / 2, c.replace("->", "\u2192"), ha="center", va="center", fontsize=13,
                fontweight="bold", color=HEADER_TEXT)
    y = top - header_h
    for k, (r, h) in enumerate(zip(rows, heights)):
        rh = h * unit + 0.22
        ax.add_patch(plt.Rectangle((0, y - rh), 1, rh, facecolor=STRIPE if k % 2 else "white", edgecolor=BORDER))
        for i, c in enumerate(r):
            bold = i == 1
            ax.text(x[i] + 0.006, y - rh / 2, c, ha="left", va="center", fontsize=12,
                    fontweight="bold" if bold else "normal", color="#1f2933", linespacing=1.25)
        y -= rh
    for xi in x[1:-1]:
        ax.plot([xi, xi], [y, top], color=BORDER, lw=0.8)
    ax.text(0.0, y - 0.25, "\n".join(textwrap.wrap(spec["footer"], 190)), ha="left", va="top", fontsize=11,
            color="#52606d")
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170, facecolor="white")
    plt.close(fig)


def main() -> None:
    draw(FIVE, FIG / "table_five_positive.png")
    draw(TEN, FIG / "table_ten_failed.png")
    print(f"Wrote {FIG.relative_to(PROJECT_ROOT)}/table_five_positive.png and table_ten_failed.png")


if __name__ == "__main__":
    main()
