HOME_TEAM_ID = 'home_team_id'
AWAY_TEAM_ID = 'away_team_id'
DATE = 'date'
LEAGUE_ID = 'league_id'

def get_all_match_columns():
    return [v for k, v in globals().items() if not k.startswith('__') and k != 'get_all_match_columns']