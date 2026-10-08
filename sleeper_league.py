#!/usr/bin/env python3
"""Pull every team's roster from a Sleeper fantasy football league.

Usage:
    python3 sleeper_league.py <league_id> [--me <sleeper_username>] [--json out.json]

Uses the public Sleeper API (no auth). Player metadata (~5MB) is cached
to .sleeper_players.json for a day, per Sleeper's request to not hit
/players/nfl more than once daily.
"""
import argparse
import json
import os
import time
import urllib.request

API = "https://api.sleeper.app/v1"
PLAYER_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sleeper_players.json")


def get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as resp:
        return json.load(resp)


def load_players():
    if os.path.exists(PLAYER_CACHE) and time.time() - os.path.getmtime(PLAYER_CACHE) < 86400:
        with open(PLAYER_CACHE) as f:
            return json.load(f)
    players = get("/players/nfl")
    with open(PLAYER_CACHE, "w") as f:
        json.dump(players, f)
    return players


def player_label(pid, players):
    p = players.get(pid)
    if not p:
        return f"{pid} (DEF)" if not pid.isdigit() else pid
    name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    pos = p.get("position") or "?"
    team = p.get("team") or "FA"
    injury = f" [{p['injury_status']}]" if p.get("injury_status") else ""
    return f"{name} ({pos}, {team}){injury}"


def build_league(league_id):
    league = get(f"/league/{league_id}")
    users = {u["user_id"]: u for u in get(f"/league/{league_id}/users")}
    rosters = get(f"/league/{league_id}/rosters")
    players = load_players()

    teams = []
    for r in rosters:
        owner = users.get(r.get("owner_id"), {})
        s = r.get("settings", {})
        starters = [pid for pid in (r.get("starters") or []) if pid and pid != "0"]
        all_players = r.get("players") or []
        reserve = set(r.get("reserve") or [])
        taxi = set(r.get("taxi") or [])
        bench = [pid for pid in all_players if pid not in starters and pid not in reserve and pid not in taxi]
        teams.append({
            "roster_id": r["roster_id"],
            "username": owner.get("display_name") or owner.get("username") or "(no owner)",
            "team_name": (owner.get("metadata") or {}).get("team_name") or owner.get("display_name") or f"Team {r['roster_id']}",
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "ties": s.get("ties", 0),
            "points_for": s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100,
            "points_against": s.get("fpts_against", 0) + s.get("fpts_against_decimal", 0) / 100,
            "starters": [player_label(p, players) for p in starters],
            "bench": [player_label(p, players) for p in bench],
            "ir": [player_label(p, players) for p in reserve],
            "taxi": [player_label(p, players) for p in taxi],
        })
    teams.sort(key=lambda t: (-t["wins"], -t["points_for"]))
    return league, teams


def print_league(league, teams, me=None):
    print(f"{league['name']} — {league['season']} season ({league.get('total_rosters')} teams)\n")
    print(f"{'#':>2}  {'Team':28} {'Owner':18} {'W-L-T':8} {'PF':>8} {'PA':>8}")
    for i, t in enumerate(teams, 1):
        rec = f"{t['wins']}-{t['losses']}-{t['ties']}"
        mark = " <- you" if me and t["username"].lower() == me.lower() else ""
        print(f"{i:>2}  {t['team_name'][:28]:28} {t['username'][:18]:18} {rec:8} {t['points_for']:8.2f} {t['points_against']:8.2f}{mark}")

    # Show your team first, then everyone else.
    ordered = sorted(teams, key=lambda t: not (me and t["username"].lower() == me.lower()))
    for t in ordered:
        tag = "  (YOUR TEAM)" if me and t["username"].lower() == me.lower() else ""
        print(f"\n=== {t['team_name']} — {t['username']}{tag} ===")
        for label, group in (("Starters", "starters"), ("Bench", "bench"), ("IR", "ir"), ("Taxi", "taxi")):
            if t[group]:
                print(f"  {label}:")
                for p in t[group]:
                    print(f"    - {p}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("league_id")
    ap.add_argument("--me", help="your Sleeper username/display name, to highlight your team")
    ap.add_argument("--json", help="also write the full data to this JSON file")
    args = ap.parse_args()

    league, teams = build_league(args.league_id)
    print_league(league, teams, args.me)
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"league": league, "teams": teams}, f, indent=2)


if __name__ == "__main__":
    main()
