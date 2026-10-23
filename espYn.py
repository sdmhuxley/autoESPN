from espn_api.football import League
import requests

# ---------------- CONFIGURATION ----------------
LEAGUE_ID = 1011302477
SEASON_ID = 2026
TEAM_ID = 3  

ESPN_S2 = "AEBfbqVbP%2FZaDgOdj%2FKv4Xic63GfdK6aoRcND3qFka5dbSaaoiKt1YC5VlNK1xFjWq8tQBarN6Ww6T%2BjQIq3dnlj1UIjnS0qilCQXIpOSMiFKK5K3suDekeuLK0NPMWIRJf0DIVkOwLiC%2FU0mb10yj%2BdyXgYsJuPtabeKcS2nvoZLCUdiW9NkHbLl%2Favm5gJH0TI4l9aglzr4vP%2FpqjRmOETiYQvm%2FPNTr7DYEG6GcM0Nt5%2FFEFDarJU4LeQFf%2FDQl486GVx2RJ4vRkjlnFGDBIUJ7yTyQprw6PIt5odvGk3SQ%3D%3D"
SWID = "{EECF8875-BE5F-4E36-800A-EE0ADDC24691}s"

COOKIES = {"espn_s2": ESPN_S2, "SWID": SWID}
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


league = League(league_id=LEAGUE_ID, year=SEASON_ID, espn_s2=ESPN_S2, swid=SWID)
team=league.teams[TEAM_ID-1]
players=team.roster


# Verified API hosts
READ_HOST = "https://lm-api-reads.fantasy.espn.com"
WRITE_HOST = "https://lm-api-writes.fantasy.espn.com"

#DO NOT CHANGE
SLOT_MAP = {
    "QB": 0, "RB": 2, "WR": 4, "TE": 6, 
    "FLEX": 23, "RB/WR/TE": 23, "RB/WR": 23, "WR/TE": 23,
    #"OP": 7, "SUPERFLEX": 7,
    "D/ST": 16, "K": 17, 
    "Bench": 20, "BE": 20, 
    "IR": 21
}

#   Parses the players and displays name + injury status

#for player in players:
    #print(player.name)
    
    #print(player.injuryStatus)
    
UNHEALTHY_STATUSES = {"OUT", "QUESTIONABLE", "DOUBTFUL", "IR","BYE","DAY_TO_DAY"}

def get_league_context_and_roster():
    """Fetches the active scoring period and team roster from lm-api-reads."""
    url = ( 
        f"{READ_HOST}/apis/v3/games/ffl/seasons/{SEASON_ID}/"
        f"segments/0/leagues/{LEAGUE_ID}?rosterForTeamId={TEAM_ID}&view=mRoster&view=mSettings"
    )
    res = requests.get(url, headers=HEADERS, cookies=COOKIES)
    res.raise_for_status()
    data = res.json()

    scoring_period_id = data.get("scoringPeriodId")
    
    # Search the list of teams for the one that matches TEAM_ID. Will throw error without this b/c unable to access API of othe teams
    my_team = next(team for team in data["teams"] if team["id"] == TEAM_ID)
    
    # Safely grab the roster entries for your team
    entries = my_team["roster"]["entries"]

    roster = []
    for entry in entries:
        player = entry["playerPoolEntry"]["player"]
        roster.append(
            {
                "id": entry["playerId"],
                "name": player["fullName"],
                "slot_id": entry["lineupSlotId"],
                "injury_status": player.get("injuryStatus", "ACTIVE"),
                "eligible_slots": player.get("eligibleSlots", []),
            }
        )

    return scoring_period_id, roster


def auto_swap_injured_starters():
    scoring_period_id, roster = get_league_context_and_roster()
    print(f"Active Scoring Period (Week): {scoring_period_id}")

    starters = [p for p in team.roster if p.lineupSlot not in ("BE", "IR")]
    bench = [p for p in team.roster if p.lineupSlot == "BE"]
    bench.sort(key=lambda p: p.projected_avg_points, reverse=True)

    swap_items = []

    for starter in starters:
        if starter.injuryStatus in UNHEALTHY_STATUSES:
            print(f"[FLAGGED] {starter.name} ({starter.injuryStatus}) in Slot {starter.lineupSlot}")

            # Find first bench player eligible for the starter's specific slot
            replacement = None
            for idx, b_player in enumerate(bench):
                is_healthy = b_player.injuryStatus not in UNHEALTHY_STATUSES
                is_eligible = starter.lineupSlot in b_player.eligibleSlots

                target_slot_id = SLOT_MAP.get(starter.lineupSlot)
                bench_slot_id = SLOT_MAP.get("BE")

                if is_healthy and is_eligible:
                    replacement = bench.pop(idx)
                    break

            if replacement:
                print(f"  -> Replacing with: {replacement.name} from Bench")
                swap_items.extend(
                    [
                        {
                            "playerId": starter.playerId,
                            "type": "LINEUP",
                            "fromLineupSlotId": target_slot_id,
                            "toLineupSlotId": bench_slot_id,
                        },
                        {
                            "playerId": replacement.playerId,
                            "type": "LINEUP",
                            "fromLineupSlotId": bench_slot_id,
                            "toLineupSlotId": target_slot_id,
                        },
                    ]
                )
            else:
                print(
                    f"  [!] No healthy, eligible bench replacement found for Slot {starter.lineupSlot}."
                )

    if not swap_items:
        print("Lineup verified: No replacements needed.")
        return

    # Post atomic lineup update to lm-api-writes
    write_url = (
        f"{WRITE_HOST}/apis/v3/games/ffl/seasons/{SEASON_ID}/"
        f"segments/0/leagues/{LEAGUE_ID}/transactions/"
    )

    payload = {
        "isLeagueManager": False,
        "teamId": TEAM_ID,
        "type": "ROSTER",
        "scoringPeriodId": scoring_period_id,
        "executionType": "EXECUTE",
        "items": swap_items,
    }

    resp = requests.post(
        write_url, headers=HEADERS, cookies=COOKIES, json=payload
    )

    if resp.status_code == 200:
        print("Lineup swap successfully posted to lm-api-writes!")
    else:
        print(f"Transaction failed [{resp.status_code}]: {resp.text}")


if __name__ == "__main__":
    auto_swap_injured_starters()

    