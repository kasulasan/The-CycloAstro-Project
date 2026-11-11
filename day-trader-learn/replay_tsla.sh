#!/usr/bin/env bash
# Replays one real day trade (TSLA, Mon 2026-10-19) through six skills,
# offline, using recorded market data. Nothing is ever sent to a broker.
# Run from anywhere:  bash day-trader-learn/replay_tsla.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SK="$HERE/../.claude/skills"
DATA="$HERE/data"
WORK="$HERE/workspace"          # the skills write their files to ./trader/
rm -rf "$WORK"; mkdir -p "$WORK/trader"; cd "$WORK"
cp "$SK/trader-budget/config.example.json" trader/config.json
NOW="2026-10-19 10:15"          # pretend it is 10:15 AM New York time
pause() { echo; read -r -p "---- press Enter for the next step ----" _ || true; echo; }

echo "STEP 1  /trader-entry: has TSLA broken out of its opening range?"
python3 "$SK/trader-entry/entry.py" check TSLA --now "$NOW" --offline "$DATA/TSLA-2026-10-19-5m.json" --write; pause
echo "STEP 2  /trader-exit: where is the stop and the target?"
python3 "$SK/trader-exit/exit.py" plan --stop or-mid --target 1R --now "$NOW" --write; pause
echo "STEP 3  /trader-timemachine: what are the odds? (10,000 replays)"
python3 "$SK/trader-timemachine/timemachine.py" run --seed 19 --now "$NOW" --offline "$DATA/TSLA-60d5m.json.gz" --write; pause
echo "STEP 4  /trader-budget: how many shares for a \$5,000 account, \$50 max loss?"
python3 "$SK/trader-budget/size.py" --now "$NOW" --write; pause
echo "STEP 5  /trader-risk: does the order break any rule?"
python3 "$SK/trader-risk/check.py" --now "$NOW"; pause
echo "STEP 6  /trader-broker: the ticket you would say yes or no to (nothing is placed)"
python3 "$SK/trader-broker/ticket.py" show --now "$NOW"
echo; echo "Done. The files each step wrote are in: $WORK/trader/"
