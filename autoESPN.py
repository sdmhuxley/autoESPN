from espn_api.football import League
import requests

LEAGUE_ID = 1011302477
SEASON_ID = 2026
TEAM_ID = 3  

league = League(league_id=LEAGUE_ID, year=SEASON_ID, espn_s2=ESPN_S2, swid=SWID)
team=league.teams[TEAM_ID-1]
players=team.roster

ESPN_S2 = "YOUR ESPN_S2 HERE"
SWID = "YOU ESPN SWID HERE"

COOKIES = {"espn_s2": ESPN_S2, "SWID": SWID}
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


READ_HOST = "https://lm-api-reads.fantasy.espn.com"
WRITE_HOST = "https://lm-api-writes.fantasy.espn.com"


SLOT_MAP = {
    "QB": 0, "RB": 2, "WR": 4, "TE": 6, 
    "FLEX": 23, "RB/WR/TE": 23, "RB/WR": 23, "WR/TE": 23,
    "D/ST": 16, "K": 17, 
    "Bench": 20, "BE": 20, 
    "IR": 21
}
    
UNHEALTHY_STATUSES = {"OUT", "QUESTIONABLE", "DOUBTFUL", "IR","BYE","DAY_TO_DAY"}

def get_league_context_and_roster():
    url = ( 
        f"{READ_HOST}/apis/v3/games/ffl/seasons/{SEASON_ID}/"
        f"segments/0/leagues/{LEAGUE_ID}?rosterForTeamId={TEAM_ID}&view=mRoster&view=mSettings"
    )
    res = requests.get(url, headers=HEADERS, cookies=COOKIES)
    res.raise_for_status()
    data = res.json()

    scoring_period_id = data.get("scoringPeriodId")
    
    my_team = next(team for team in data["teams"] if team["id"] == TEAM_ID)
    
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
                    f"No healthy, eligible bench replacement found for Slot {starter.lineupSlot}."
                )

    if not swap_items:
        print("No replacements needed.")
        return

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
        print("Lineup swap successful")
    else:
        print(f"Transaction failed [{resp.status_code}]: {resp.text}")


if __name__ == "__main__":
    auto_swap_injured_starters()

    