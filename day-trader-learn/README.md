# Learn day trading with the Day Trader skills

This folder teaches you how the 11 `trader-*` skills in `.claude/skills/` work,
using **one real trade**: Tesla (TSLA) on Monday, October 19, 2026.

> Education only, not financial advice. Most people who day trade lose money.
> Practice with **paper trading** (fake money) for a long time before you use real money.

---

## 1. Run the lesson (5 minutes, no internet needed)

```bash
bash day-trader-learn/replay_tsla.sh
```

It stops after each step. Press Enter to go on. It uses recorded prices in
`day-trader-learn/data/`, so it works offline. **It never buys anything.**

---

## 2. The words you need

| Word | What it means | In the TSLA trade |
| --- | --- | --- |
| **Day trade** | Buy and sell on the same day. You hold nothing overnight. | Sell by 3:55 PM at the latest |
| **5-minute bar (candle)** | The open, high, low and close price in a 5-minute block | The 10:10 bar closed at $364.18 |
| **Opening range** | The highest and lowest price in the first 15 minutes (9:30 to 9:45 AM New York time) | High $362.18, low $354.47 |
| **Breakout** | Price closes **above** the opening-range high, which may mean buyers are in control | 10:10 bar closed at $364.18, 0.55% above the high |
| **Entry** | The price you buy at | $364.18 |
| **Stop-loss** | The price where you sell to cut a loss. You pick it **before** you buy. | $358.32 (the middle of the range) |
| **Target (take-profit)** | The price where you sell to take a profit | $370.04 |
| **Risk per share (1R)** | Entry minus stop: what you lose on each share if the stop hits | $364.18 − $358.32 = **$5.86** |
| **Reward:risk** | Profit at the target divided by loss at the stop | $5.86 / $5.86 = **1.0** |
| **Position size** | How many shares to buy | 8 shares |
| **Bracket order** | One order that buys and also places your stop and target. When one of them fills, the other is canceled. | Buy 8, stop 358.32, target 370.04 |
| **Paper trading** | Trading with pretend money in a practice account | The default in these skills |

---

## 3. The trade, step by step

The skills form a chain. Each one writes a file in `trader/` and the next skill reads it:

```
scanner → news → entry → exit → timemachine → budget → risk → broker → alerts
```

**Step 1: Entry (`/trader-entry`).** Find the opening range, then wait for a
5-minute bar to *close* above the high. A quick move above the high that
falls back (a "wick") does not count. TSLA triggered at **10:15 AM at $364.18**.

**Step 2: Exit plan (`/trader-exit`).** Choose the stop and the target **before**
you buy. Stop = middle of the range = $358.32. Target = 1R above the entry = $370.04.
Rule: you never move the stop further away.

**Step 3: Time Machine (`/trader-timemachine`).** This is the most useful step for
learning. It builds 10,000 possible versions of the rest of the day from TSLA's
own last 59 days of price moves (a "Monte Carlo" simulation):

- target hit first: **29.4%**
- stop hit first: **25.5%**
- neither by 4 PM: **45.1%**

It also checked the same rule on the last 59 real days: it fired 33 times,
**13 wins, 15 losses, 5 neither**. The average result was slightly negative.
**Verdict: close to a coin flip.** That lesson matters: a setup that looks good
on a chart often has no real edge.

**Step 4: Position size (`/trader-budget`).** Account $5,000. You decide you will
lose at most **$50** on one trade.
`$50 ÷ $5.86 = 8.5`, rounded down to **8 shares** ($2,913.44).
If the stop hits, you lose 8 × $5.86 = **$46.88**.
This is the most important habit in trading: **the stop distance decides how
many shares you buy, not how much money you have.**

**Step 5: Risk check (`/trader-risk`).** Checks the order against your rules:
max loss per trade ($50), daily loss limit ($150), at most 3 trades a day,
minimum reward:risk, trading hours and cash. Result: **PASS**.

**Step 6: Broker ticket (`/trader-broker`).** Shows the exact order in plain
English and waits for you to type "yes". Then Claude asks a second time. Nothing
is placed without both. In this lesson no broker is connected, so nothing can be placed.

Open the files in `day-trader-learn/workspace/trader/` (`entry.json`,
`plan.json`, `timemachine.json`, `orders.json`) to see what each step saved.

---

## 4. Try changing things

Each change teaches one idea. Run these from the `day-trader-learn/workspace` folder
after the lesson. Set `SK=../../.claude/skills`.

```bash
cd day-trader-learn/workspace && SK=../../.claude/skills
```

A 2R target (bigger profit, but hit less often). Compare the odds with the 1R run:

```bash
python3 $SK/trader-exit/exit.py plan --stop or-mid --target 2R --now "2026-10-19 10:15" --write
```

```bash
python3 $SK/trader-timemachine/timemachine.py run --seed 19 --now "2026-10-19 10:15" --offline ../data/TSLA-60d5m.json.gz
```

What you should see: target first drops from 29.4% to **4.0%**, and in the 59 real
days it won only 3 times out of 33. A bigger target is not free: it gets hit much less often.

A wider stop at the range low. Notice that `/trader-budget` now buys **fewer** shares:

```bash
python3 $SK/trader-exit/exit.py plan --stop or-low --target 1R --now "2026-10-19 10:15" --write
```

```bash
python3 $SK/trader-budget/size.py --now "2026-10-19 10:15"
```

What you should see: risk per share goes from $5.86 to $9.71, so the size drops from
8 shares to **5 shares**, and the max loss stays under $50 ($48.55).

Change your limits (budget, max loss, daily limit) by editing `trader/config.json`.

---

## 5. Using it for real (on your own computer)

These skills need live internet data (Yahoo Finance, SEC). The cloud session
that set this up cannot reach them, but your own computer can.

1. Install [Claude Code](https://claude.com/claude-code) and Python 3.8 or newer.
2. Download this repo:

   ```bash
   git clone -b claude/sleepy-ritchie-q394c3 https://github.com/kasulasan/The-CycloAstro-Project.git
   ```

3. Open Claude Code in that folder and type a command, for example
   `/trader-scanner`, `/trader-news TSLA` or `/trader-analyst TSLA`.
   You can also just ask, for example "scan the market for opening range breakouts".
4. For the SEC skills, set your name and email:
   `export SEC_USER_AGENT="Your Name you@example.com"`.
5. To practice placing orders, open a free **paper** account at Alpaca. See
   `.claude/skills/trader-broker/SKILL.md`. Never paste API keys into the chat.

**A good way to learn:** paper trade for at least a month. Run the Time Machine
before every trade and write down the result. Then compare your real win rate with
what the Time Machine said.

---

## 6. The other skills (need live data)

| Skill | What you learn from it |
| --- | --- |
| `/trader-scanner` | How traders find candidates among ~5,900 stocks (breakouts, bull flags, oversold) |
| `/trader-news` | Why stocks move: earnings, analyst calls, deals, SEC 8-K filings |
| `/trader-alerts` | Get notified at your stop, your target and at 3:55 PM to close |
| `/trader-analyst` | How to read earnings: revenue, margins, EPS against a year earlier |
| `/trader-pelosi` | Stock trades that members of Congress must disclose publicly |
