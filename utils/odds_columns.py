HOME = '1'; DRAW = 'X'; AWAY = '2'; HT_HOME = 'ht_1'; HT_DRAW = 'ht_X'; HT_AWAY = 'ht_2'; BTTS_YES = 'btts_yes'; BTTS_NO = 'btts_no'; 
FIRST_HALF_BTTS_YES = 'first_half_btts_yes'; FIRST_HALF_BTTS_NO = 'first_half_btts_no';
SECOND_HALF_BTTS_YES = 'second_half_btts_yes'; SECOND_HALF_BTTS_NO = 'second_half_btts_no';
HOME_AND_HOME = '1-1'; HOME_AND_DRAW = '1-X'; HOME_AND_AWAY = '1-2'; HOME_OR_DRAW = '1/X'; HOME_OR_AWAY = '1/2'; DRAW_OR_AWAY = 'X/2';
AWAY_AND_HOME = '2-1'; AWAY_AND_DRAW = '2-X'; AWAY_AND_AWAY = '2-2'; DRAW_AND_HOME = 'X-1'; DRAW_AND_DRAW = 'X-X'; DRAW_AND_AWAY = 'X-2';
HT_HOME_OR_DRAW = 'ht_1/X'; HT_DRAW_OR_AWAY = 'ht_X/2'; HT_HOME_OR_AWAY = 'ht_1/2';
OVER_1_5 = 'over_1.5'; UNDER_1_5 = 'under_1.5'; HOME_AND_OVER_1_5 = 'home_&over_1.5'; HOME_AND_UNDER_1_5 = 'home_&under_1.5'
OVER_2_5 = 'over_2.5'; UNDER_2_5 = 'under_2.5'; HOME_AND_OVER_2_5 = 'home_&over_2.5'; HOME_AND_UNDER_2_5 = 'home_&under_2.5'
OVER_3_5 = 'over_3.5'; UNDER_3_5 = 'under_3.5'; HOME_AND_OVER_3_5 = 'home_&over_3.5'; HOME_AND_UNDER_3_5 = 'home_&under_3.5'
OVER_4_5 = 'over_4.5'; UNDER_4_5 = 'under_4.5'; HOME_AND_OVER_4_5 = 'home_&over_4.5'; HOME_AND_UNDER_4_5 = 'home_&under_4.5'  
AWAY_AND_OVER_1_5 = 'away_&over_1.5'; AWAY_AND_UNDER_1_5 = 'away_&under_1.5'; AWAY_AND_OVER_2_5 = 'away_&over_2.5'; AWAY_AND_UNDER_2_5 = 'away_&under_2.5'; 
AWAY_AND_OVER_3_5 = 'away_&over_3.5'; AWAY_AND_UNDER_3_5 = 'away_&under_3.5'; AWAY_AND_OVER_4_5 = 'away_&over_4.5'; AWAY_AND_UNDER_4_5 = 'away_&under_4.5'; 
OVER_2_5_BTTS_YES = 'over_2.5_btts_yes'; OVER_2_5_BTTS_NO = 'over_2.5_btts_no'; UNDER_2_5_BTTS_YES = 'under_2.5_btts_yes'; UNDER_2_5_BTTS_NO = 'under_2.5_btts_no';
OVER_3_5_BTTS_YES = 'over_3.5_btts_yes'; OVER_3_5_BTTS_NO = 'over_3.5_btts_no'; UNDER_3_5_BTTS_YES = 'under_3.5_btts_yes'; UNDER_3_5_BTTS_NO = 'under_3.5_btts_no';
OVER_4_5_BTTS_YES = 'over_4.5_btts_yes'; OVER_4_5_BTTS_NO = 'over_4.5_btts_no'; UNDER_4_5_BTTS_YES = 'under_4.5_btts_yes'; UNDER_4_5_BTTS_NO = 'under_4.5_btts_no';

def get_all_odds_columns():
    return [v for k, v in globals().items() if not k.startswith('__') and k != 'get_all_odds_columns']