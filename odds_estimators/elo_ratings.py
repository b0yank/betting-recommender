import numpy as np
import pandas as pd
from datetime import datetime
import warnings

from data_services import SoccerwayFootballDataService
from constants import ACCEPTED_GOALS, DB_PATH

class EloRatingsOddsEstimator:
    """Elo ratings-based model for estimating odds in games. Uses a standard elo ratings system adapted
       for football, with a couple of additions:
           - form:                     Estimates a team's home and away 'form', which acts as a correction
                                       on the team's current strength estimation (points). The idea is that
                                       points would change slower over time, while form will adjust for
                                       short-term fluctuations. Uses an exponentially weighted average on the
                                       team's past games.
           - margin expectation:       Adjusts the points corrections for both teams based on the difference
                                       between the margin in the game and the expected margin given the points
                                       difference (estimated on games in the database from the current league).
           - expected advantage:       Adds a pre-calculated expected home/away advantage, which was calculated
                                       as the points difference required for the model to expect an equal game
                                       (spoiler alert - it's a home advantage in every league). Differs from most
                                       elo ratings models which use a fixed home advantage for all leagues.

       Parameters:
           'football_database' - Database of past football games on which the ratings will are built
           'form_lr'           - Coefficient to use in the exponentially weighted average calculation for the form of
                                 each team. The higher form_lr is, the more importance that is placed on more recent games,
                                 with the edge case form_lr = 1 meaning the model only looks at the previous game.
           'delta_points_diff' - The model uses the points difference between the teams to find similar past games and use the
                                 frequency of events in that collection of games as probabilities. However, since the points
                                 difference is too specific and would often lead to either very little or no games that fit the
                                 criterion, the model uses games that had points_difference +/- delta_points_diff as their points
                                 difference
    """
    _LEAGUE_INIT_POINTS_CSV_PATH = DB_PATH + 'leagues_init_points.csv' 
    _LEAGUE_MARGINS_CSV_PATH = DB_PATH + 'league_margins.csv' 
    _ELO_RATINGS_CSV_PATH = DB_PATH + 'teams_elo.csv' 
    _GOALS_GIVEN_POINTS_CSV_PATH = DB_PATH + 'goals_given_points.csv'
    _MARGIN_GIVEN_POINTS_CSV_PATH = DB_PATH + 'margin_given_points.csv'
    _MARGINS_EXP_GIVEN_SIGN_PATH = DB_PATH + 'league_exp_margin_given_sign.csv' 
    _TEAMS_FORM_CSV_PATH = DB_PATH + 'teams_form.csv'

    _INIT_CALIBRATION_ROUNDS = 20
    
    def __init__(self,
                 football_database,
                 form_lr = 0.2,
                 delta_points_diff = 30):
        self.db = football_database

        if form_lr < 0. or form_lr > 1.:
            raise ValueError('Form learning rate must be a number in the range [0, 1]')
        self.form_lr = form_lr
        
        if delta_points_diff <= 0:
            raise ValueError('Parameter delta_points_diff must be a positive number.')
        self.delta_points_diff = delta_points_diff

        self.__teams_elo_score = None
        self.__goals_given_points = None
        self.__margin_given_points = None
        self.__leagues_init_points = None
        self.__leagues_margins = None
        self.__teams_form = None
        self.__mevgs = None


        self.__update_list = []
        self.__margin_given_points_new = []
        self.__goals_given_points_new = []

    @property
    def teams_elo_score(self):
        if self.__teams_elo_score is None:
            self.__teams_elo_score = pd.read_csv(self._ELO_RATINGS_CSV_PATH)\
                                            .astype(dtype={'team_id': 'int32',
                                                           'league_id': 'int8',
                                                           'elo_rating': 'float16',
                                                           'date': 'datetime64[ns]',
                                                           'home_delta': 'float16',
                                                           'away_delta': 'float16',
                                                           'home_t': 'int8',
                                                           'away_t': 'int8',
                                                           'calibrating_game': 'bool'})
        return self.__teams_elo_score

    @teams_elo_score.setter
    def teams_elo_score(self, value): self.__teams_elo_score = value

    @property
    def margin_exp_value_given_sign(self):
        if self.__mevgs is None:
            self.__mevgs = pd.read_csv(self._MARGINS_EXP_GIVEN_SIGN_PATH)
        return self.__mevgs

    @property
    def leagues_margins(self):
        if self.__leagues_margins is None:
            self.__leagues_margins = pd.read_csv(self._LEAGUE_MARGINS_CSV_PATH)
        return self.__leagues_margins

    @property
    def teams_form(self):
        if self.__teams_form is None:
            self.__teams_form = pd.read_csv(self._TEAMS_FORM_CSV_PATH)
        return self.__teams_form

    @teams_form.setter
    def teams_form(self, value): self.__teams_form = value;

    @property
    def leagues_init_points(self):
        if self.__leagues_init_points is None:
            self.__leagues_init_points = pd.read_csv(self._LEAGUE_INIT_POINTS_CSV_PATH)
        return self.__leagues_init_points

    @property
    def goals_given_points(self):
        if self.__goals_given_points is None:
            self.__goals_given_points = pd.read_csv(self._GOALS_GIVEN_POINTS_CSV_PATH)\
                                            .astype(dtype={'date': 'datetime64[ns]',
                                                           'season': 'object',
                                                           'league_id': 'int8',
                                                           'ft_home': 'int8',
                                                           'ft_away': 'int8',
                                                           'ht_home': 'int8',
                                                           'ht_away': 'int8',
                                                           'points_diff': 'float16'})
        return self.__goals_given_points

    @goals_given_points.setter
    def goals_given_points(self, value): self.__goals_given_points = value

    @property
    def margin_given_points(self):
        if self.__margin_given_points is None:
            self.__margin_given_points = pd.read_csv(self._MARGIN_GIVEN_POINTS_CSV_PATH)\
                                            .astype(dtype={'ft_home': 'int8',
                                                           'ft_away': 'int8',
                                                           'ht_home': 'int8',
                                                           'ht_away': 'int8',
                                                           'points_diff': 'float16',
                                                           'league_id': 'int8',
                                                           'season': 'object',
                                                           'date': 'datetime64[ns]'})
        return self.__margin_given_points

    @margin_given_points.setter
    def margin_given_points(self, value): self.__margin_given_points = value

    def get_rating_at_date(self, team_id, date):
        return self.teams_elo_score[(self.teams_elo_score.team_id == team_id)&(self.teams_elo_score.date <= date)]\
                        .sort_values('date', ascending = False)['elo_rating'].values[0]
        
    def estimate_odds(self, league_ids, start_date, end_date, use_form=True):
        self.update_data(calibration_rounds=8)

        games = self.db.provide_games(league_ids, start_date, end_date)

        odds = [self.__estimate_game_odds(games.loc[idx], use_form) for idx in games.index]
        return pd.DataFrame.from_dict(odds)

    def update_data(self, calibration_rounds=8):
        current_season = int(self.db.date_to_season(datetime.now()))

        if len(self.teams_elo_score) == 0:
            last_update_season = None
            update_seasons = sorted(list(self.db.games.season.unique()))
        else:
            last_update_season = int(self.db.date_to_season(self.teams_elo_score.date.max()))
            update_seasons = sorted([s for s in self.db.games.season.unique() if s > last_update_season]) if current_season != last_update_season\
                                                                                                          else [current_season]

        # prepare margin_exp_value_given_sign for easy lookup depending on league
        league_ids = self.margin_exp_value_given_sign['league_id'].values
        league_mevgs = {lid: mevgs for lid, mevgs in zip(league_ids, self.margin_exp_value_given_sign.drop('league_id', axis=1).to_dict(orient='records'))}

        league_start_season = {lid: self.db.games[self.db.games.league_id == lid].season.min() for lid in league_ids}
        
        for update_season in update_seasons:
            team_ids_this_season = np.unique(self.db.games[self.db.games.season == update_season][['home_team_id', 'away_team_id']].values)

            if last_update_season is None or last_update_season < current_season:
                self.__initialize_elo_ratings(team_ids_this_season, update_season)
                #self.__update_margin_exp_value_given_sign()

                # start team form afresh in new season
                self.teams_form = pd.DataFrame.from_dict([{'team_id': tid,
                                                           'home_delta': 0.,
                                                           'away_delta': 0.,
                                                           'home_t': 0,
                                                           'away_t': 0}\
                                                             for tid in team_ids_this_season])
                self.teams_form.to_csv(self._TEAMS_FORM_CSV_PATH, index_label=False)

                games_to_update = self.db.games[self.db.games.season == update_season].sort_values('date', ascending=True)
            else:
                games_to_update = self.db.games[(self.db.games.season == update_season)&\
                                                (self.db.games.date > self.teams_elo_score.date.max())]\
                                                .sort_values('date', ascending=True)
            if len(games_to_update) > 0:
                games_to_update = games_to_update[['ft_home', 'ft_away', 'date', 'league_id', 'ht_home', 'ht_away', 'season', 'home_team_id', 'away_team_id']].copy()
                games_to_update['margin'] = (games_to_update.ft_home - games_to_update.ft_away)
                games_to_update['sign'] = games_to_update.apply(lambda x: 'X' if x.ft_home == x.ft_away else str(int(x.ft_home < x.ft_away) + 1),
                                                                  axis = 1)

                # get last team ratings in a quick table
                self.__teams_ratings = {team_id: self.teams_elo_score[(self.teams_elo_score.team_id == team_id)]\
                                                    .sort_values('date', ascending = False)\
                                                        ['elo_rating'].values[0]\
                                                            for team_id in team_ids_this_season}

                for league_id in games_to_update['league_id'].unique():
                    rounds_to_calibrate = calibration_rounds if update_season > league_start_season[league_id] else self._INIT_CALIBRATION_ROUNDS

                    games_to_update_league = games_to_update[games_to_update.league_id == league_id]
                    games_to_update_league.apply(lambda game: self.__update_elo(game, league_mevgs[game.league_id], rounds_to_calibrate), axis = 1)

                self.__update_stats()
                self.__save_stats()

                last_update_season  = update_season
    
    def __estimate_game_odds(self, game, use_form=True):
        home_team_stats = self.teams_elo_score[(self.teams_elo_score.team_id == game.home_team_id)&\
                                             (self.teams_elo_score.date < game.date)]\
                                    .sort_values('date', ascending=False)
        away_team_stats = self.teams_elo_score[(self.teams_elo_score.team_id == game.away_team_id)&\
                                             (self.teams_elo_score.date < game.date)]\
                                    .sort_values('date', ascending=False)

        home_team_rating = home_team_stats['elo_rating'].values[0]
        away_team_rating = away_team_stats['elo_rating'].values[0]
        if use_form:
            home_team_rating += home_team_stats['home_delta'].values[0]
            away_team_rating += away_team_stats['away_delta'].values[0]

        points_diff = home_team_rating - away_team_rating
            
        delta = self.delta_points_diff
        # reduce delta if teams are too closely matched
        #if 2*delta >= abs(points_diff):
        #    delta = delta/2
        #    #delta = points_diff/2
        sim_games = self.goals_given_points[(self.goals_given_points.points_diff >= (points_diff - delta))&\
                                            (self.goals_given_points.points_diff <= (points_diff + delta))]
        ngames = len(sim_games)
        if ngames < 20:
            if points_diff - delta > self.goals_given_points.points_diff.max():
                sim_games = self.goals_given_points.nlargest(20, 'points_diff')
                ngames = len(sim_games)
            elif ngames > 0:
                warnings.warn(f'Less than twenty games with points difference between {points_diff - delta} and ' +\
                                 f'{points_diff + delta} recorded. Perhaps you should increase delta_points_diff?')
            else:
                raise ValueError(f'No games with points difference between {points_diff - delta} and ' +\
                                 f'{points_diff + delta} recorded. Perhaps you should increase delta_points_diff?')
        
        btts = (sim_games.ft_home > 0)&(sim_games.ft_away > 0)
        ft_home = sim_games.ft_home > sim_games.ft_away
        ft_draw = sim_games.ft_home == sim_games.ft_away
        ft_away = sim_games.ft_home < sim_games.ft_away
        ht_home = sim_games.ht_home > sim_games.ht_away
        ht_draw = sim_games.ht_home == sim_games.ht_away
        ht_away = sim_games.ht_home < sim_games.ht_away
        first_half_btts = (sim_games.ht_home > 0)&(sim_games.ht_away > 0)
        second_half_btts = ((sim_games.ft_home-sim_games.ht_home) > 0)&((sim_games.ft_away-sim_games.ht_away) > 0)
        game_odds = {
            # game info
            'date': game.date,
            'home_team_id': game.home_team_id,
            'away_team_id': game.away_team_id,
            'league_id': game.league_id,
            # main
            '1': len(sim_games[ft_home])/ngames,
            'X': len(sim_games[ft_draw])/ngames,
            '2': len(sim_games[ft_away])/ngames,
            'btts_yes': len(sim_games[btts])/ngames,
            'btts_no': len(sim_games[~btts])/ngames,
            # half
            'ht_1': len(sim_games[ht_home])/ngames,
            'ht_X': len(sim_games[ht_draw])/ngames,
            'ht_2': len(sim_games[ht_away])/ngames,
            'first_half_btts_yes': len(sim_games[first_half_btts])/ngames,
            'first_half_btts_no': len(sim_games[~first_half_btts])/ngames,
            'second_half_btts_yes': len(sim_games[second_half_btts])/ngames,
            'second_half_btts_no': len(sim_games[~second_half_btts])/ngames,
            # double chance
            '1/X': len(sim_games[ft_home|ft_draw])/ngames,
            'X/2': len(sim_games[ft_draw|ft_away])/ngames,
            '1/2': len(sim_games[ft_home|ft_away])/ngames,
            # ht double chance
            'ht_1/X': len(sim_games[ht_home|ht_draw])/ngames,
            'ht_X/2': len(sim_games[ht_draw|ht_away])/ngames,
            'ht_1/2': len(sim_games[ht_home|ht_away])/ngames,
            # ht-ft
            '1-1': len(sim_games[ht_home&ft_home])/ngames,
            '1-X': len(sim_games[ht_home&ft_draw])/ngames,
            '1-2': len(sim_games[ht_home&ft_away])/ngames,
            'X-1': len(sim_games[ht_draw&ft_home])/ngames,
            'X-X': len(sim_games[ht_draw&ft_draw])/ngames,
            'X-2': len(sim_games[ht_draw&ft_away])/ngames,
            '2-1': len(sim_games[ht_away&ft_home])/ngames,
            '2-X': len(sim_games[ht_away&ft_draw])/ngames,
            '2-2': len(sim_games[ht_away&ft_away])/ngames
        }
        
        tot_goals = sim_games.ft_home + sim_games.ft_away
        ft_over = {f'over_{ng}': len(tot_goals[tot_goals > ng])/ngames for ng in ACCEPTED_GOALS}
        ft_under = {f'under_{k[-3:]}': 1-v for k,v in ft_over.items()}
        result_tg = {f'home_&over_{ng}': len(sim_games[ft_home&(tot_goals > ng)])/ngames for ng in ACCEPTED_GOALS}
        result_tg.update({f'home_&under_{ng}': len(sim_games[ft_home&(tot_goals < ng)])/ngames for ng in ACCEPTED_GOALS})
        result_tg.update({f'away_&over_{ng}': len(sim_games[ft_away&(tot_goals > ng)])/ngames for ng in ACCEPTED_GOALS})
        result_tg.update({f'away_&under_{ng}': len(sim_games[ft_away&(tot_goals < ng)])/ngames for ng in ACCEPTED_GOALS})

        tg_btts = {f'over_{ng}_btts_yes': len(sim_games[(tot_goals > ng)&(btts)])/ngames for ng in ACCEPTED_GOALS if ng > 1.5}
        tg_btts.update({f'over_{ng}_btts_no': len(sim_games[(tot_goals > ng)&(~btts)])/ngames for ng in ACCEPTED_GOALS if ng > 1.5})
        tg_btts.update({f'under_{ng}_btts_yes': len(sim_games[(tot_goals < ng)&(btts)])/ngames for ng in ACCEPTED_GOALS if ng > 1.5})
        tg_btts.update({f'under_{ng}_btts_no': len(sim_games[(tot_goals < ng)&(~btts)])/ngames for ng in ACCEPTED_GOALS if ng > 1.5})
        game_odds.update(ft_over)
        game_odds.update(ft_under)
        game_odds.update(result_tg)
        game_odds.update(tg_btts)
        
        return game_odds

    def __update_elo(self,
                   game,
                   margin_exp_value_given_sign,
                   rounds_to_calibrate,
                   k = 20,
                   update_list = []):

        home_team_elo = self.__teams_ratings[game.home_team_id]
        away_team_elo = self.__teams_ratings[game.away_team_id]

#        # filling margin_given_points for future use in model
#        # for predicting expected value of goals margin given points difference
#        if not calibrating_game:
##             is_home_better = home_team_elo > away_team_elo
##             points_diff = abs(away_team_elo - home_team_elo)
##             margin = game.ft_home - game.ft_away if is_home_better else game.ft_away - game.ft_home
#            points_diff = home_team_elo - away_team_elo
#            self.__margin_given_points_new.append({'ft_home': game.ft_home,
#                                                   'ft_away': game.ft_away,
#                                                   'ht_home': game.ht_home,
#                                                   'ht_away': game.ht_away,
#                                                   'points_diff': points_diff,
#                                                   'league_id': game.league_id,
#                                                   'season': game.season,
#                                                   'date': game.date})

        league_margins = self.leagues_margins[self.leagues_margins.league_id == game.league_id]
        expected_advantage, intercept, coef = league_margins[['expected_advantage',
                                                              'intercept',
                                                              'coef']].values[0]        
        
        points_diff = home_team_elo - away_team_elo + expected_advantage        

        R_h = int(game.ft_home > game.ft_away) if game.ft_home != game.ft_away else 0.5
        R_a = 1 - R_h

        E_h = self.__W_e(points_diff)
        E_a = self.__W_e(-points_diff)

        elo_delta_h = (R_h - E_h) * k
        elo_delta_a = (R_a - E_a) * k

        sign_func = lambda a: 1 if a>0 else -1 if a<0 else 0
        margin = game.margin if abs(game.margin) < 5 else 5*sign_func(game.margin)
        if abs(margin) > 0:
            exp_margin = margin_exp_value_given_sign[game.sign]
            margin_given_exp = np.sqrt(abs(margin) / exp_margin)
        else:
            margin_given_exp = 1.

        elo_margin_h = elo_delta_h * margin_given_exp
        elo_margin_a = elo_delta_a * margin_given_exp

        self.__teams_ratings[game.home_team_id] = home_team_elo + elo_margin_h
        self.__teams_ratings[game.away_team_id] = away_team_elo + elo_margin_a

        # update home/away form
        expected_points_diff = (margin - intercept) / coef
        true_points_diff = home_team_elo - away_team_elo + expected_advantage
        # difference between true and expected points is halved
        # the assumption is that both teams share the 'fault' for the difference equally
        delta_points_diff = (true_points_diff - expected_points_diff) / 2

        home_home_form = self.teams_form[self.teams_form.team_id == game.home_team_id]\
                                ['home_delta'].values[0]
        away_away_form = self.teams_form[self.teams_form.team_id == game.away_team_id]\
                                ['away_delta'].values[0]
        home_away_form = self.teams_form[self.teams_form.team_id == game.home_team_id]\
                                ['away_delta'].values[0]
        away_home_form = self.teams_form[self.teams_form.team_id == game.away_team_id]\
                                ['home_delta'].values[0]

        home_home_new = (1 - self.form_lr)*home_home_form - self.form_lr*delta_points_diff
        away_away_new = (1 - self.form_lr)*away_away_form + self.form_lr*delta_points_diff

        home_home_t = self.teams_form[self.teams_form.team_id == game.home_team_id]\
                                ['home_t'].values[0] + 1
        home_away_t = self.teams_form[self.teams_form.team_id == game.home_team_id]\
                                ['away_t'].values[0]
        away_away_t = self.teams_form[self.teams_form.team_id == game.away_team_id]\
                                ['away_t'].values[0] + 1
        away_home_t = self.teams_form[self.teams_form.team_id == game.away_team_id]\
                                ['home_t'].values[0]
        
        self.teams_form.loc[self.teams_form.team_id == game.home_team_id,
                            ['home_delta', 'home_t']] = [home_home_new, home_home_t]
        self.teams_form.loc[self.teams_form.team_id == game.away_team_id,
                            ['away_delta', 'away_t']] = [away_away_new, away_away_t]

        calibrating_game = (home_home_t + home_away_t <= rounds_to_calibrate)|(away_home_t + away_away_t <= rounds_to_calibrate)

        if not calibrating_game:
            # update goals_given_points for future use
            points_diff = (home_team_elo + home_home_new) - (away_team_elo + away_away_new)
            self.__goals_given_points_new.append({'ft_home': game.ft_home,
                                                  'ft_away': game.ft_away,
                                                  'ht_home': game.ht_home,
                                                  'ht_away': game.ht_away,
                                                  'points_diff': points_diff,
                                                  'league_id': game.league_id,
                                                  'season': game.season,
                                                  'date': game.date})

        self.__update_list.append({'team_id': game.home_team_id,
                                   'league_id': game.league_id,
                                   'elo_rating': self.__teams_ratings[game.home_team_id],
                                   'home_delta': home_home_new,
                                   'away_delta': home_away_form,
                                   'home_t': home_home_t,
                                   'away_t': home_away_t,
                                   'calibrating_game': calibrating_game,
                                   'date': game.date})
        self.__update_list.append({'team_id': game.away_team_id,
                                   'league_id': game.league_id,
                                   'elo_rating': self.__teams_ratings[game.away_team_id],
                                   'home_delta': away_home_form,
                                   'away_delta': away_away_new,
                                   'home_t': away_home_t,
                                   'away_t': away_away_t,
                                   'calibrating_game': calibrating_game,
                                   'date': game.date})
        
    def __W_e(self, dr, q=400):
        return 1 / (10**(-dr/q) + 1)
    
    def __update_stats(self):
        self.teams_elo_score = self.teams_elo_score.append(pd.DataFrame.from_dict(self.__update_list), ignore_index=True)   
        self.__update_list = []

        self.goals_given_points = self.goals_given_points.append(pd.DataFrame.from_dict(self.__goals_given_points_new), ignore_index=True)
        self.__goals_given_points_new = []

        self.margin_given_points = self.margin_given_points.append(pd.DataFrame.from_dict(self.__margin_given_points_new), ignore_index=True)
        self.__margin_given_points_new = []

    def __save_stats(self):
        self.teams_elo_score.to_csv(self._ELO_RATINGS_CSV_PATH, index_label=False)
        self.teams_form.to_csv(self._TEAMS_FORM_CSV_PATH, index_label=False)
        self.goals_given_points.to_csv(self._GOALS_GIVEN_POINTS_CSV_PATH, index_label=False)
        self.margin_given_points.to_csv(self._MARGIN_GIVEN_POINTS_CSV_PATH, index_label=False)

    def __initialize_elo_ratings(self, team_ids_this_season, current_season):
        season_start_date = datetime(int(current_season / 1e4), 7, 1)

        def get_team_starting_entry(team_id):
            last_season = current_season - 10001
            league_id_last_season = self.db.games[(self.db.games.season == last_season)&\
                                                  (self.db.games.home_team_id == team_id)]['league_id']
            league_id_this_season = self.db.games[(self.db.games.season == current_season)&\
                                                  (self.db.games.home_team_id == team_id)]['league_id'].values[0]

            # use last elo rating team got in the previous season if they stayed in the same league
            # initialize with league default otherwise
            if len(league_id_last_season) == 0 or league_id_last_season.values[0] != league_id_this_season:
                team_starting_rating = self.leagues_init_points[self.leagues_init_points.league_id == league_id_this_season]['starting_points'].values[0]
            else:
                team_starting_rating = self.teams_elo_score[self.teams_elo_score.team_id == team_id].sort_values('date', ascending=False)['elo_rating'].values[0]

            return {'team_id': team_id,
                    'league_id': league_id_this_season,
                    'elo_rating': team_starting_rating,
                    'home_delta': 0.,
                    'away_delta': 0.,
                    'home_t': 0,
                    'away_t': 0,
                    'calibrating_game': True,
                    'date': season_start_date}

        teams_ratings_new_entries = [get_team_starting_entry(tid) for tid in team_ids_this_season]
        self.teams_elo_score = self.teams_elo_score.append(pd.DataFrame.from_dict(teams_ratings_new_entries), ignore_index=True)
        self.__save_stats()

    def __update_margin_exp_value_given_sign(self):
        leagues_mevgs = []
        for league_id in range(len(self.db.leagues)):
            all_league_games = self.db.games[(self.db.games.league_id == league_id)][['ft_home', 'ft_away', 'date', 'league_id',
                                                                                      'ht_home', 'ht_away', 'season',
                                                                                      'home_team_id', 'away_team_id',
                                                                                      ]].copy()
        
            all_league_games['margin'] = (all_league_games.ft_home - all_league_games.ft_away).apply('abs')
            all_league_games['sign'] = all_league_games.apply(lambda x: 'X' if x.ft_home == x.ft_away\
                                                                else str(int(x.ft_home < x.ft_away) + 1),
                                                            axis = 1)

            probs_margins = {}
            margin_exp_value_given_sign = {}
            for sign in ['1', '2']:
                counts = all_league_games[all_league_games.sign == sign]['margin'].value_counts().sort_index() 
                margins = np.hstack([counts.index.values[:6], np.array(['>5'])])
                percents = np.hstack([counts.values[:6], np.sum(counts.values[6:])]) /\
                                    len(all_league_games[all_league_games.sign == sign])

                probs_margins[sign] = {k: v for k, v in zip(margins, percents)}

                margin_exp_value_given_sign[sign] = np.sum(np.array([int(m.replace('>5', '6'))\
                                                         for m in probs_margins[sign].keys()])*\
                                                                   np.array(list(probs_margins[sign].values())))

                margin_exp_value_given_sign['league_id'] = league_id

            leagues_mevgs.append(margin_exp_value_given_sign)

        pd.DataFrame.from_dict(leagues_mevgs).to_csv(self._MARGINS_EXP_GIVEN_SIGN_PATH, index_label=False)

    #def construct_ratings(self,
    #                      league_id,
    #                      start_date = None,
    #                      calibration_rounds_first_season = 20,
    #                      calibration_rounds_following_seasons = 8):
    #    LEAGUE_INIT_RATING = self.leagues_init_points[self.leagues_init_points.league_id == league_id]\
    #                                        ['starting_points'].values[0]
            
    #    if start_date is None:
    #        start_date = datetime(1900, 1, 1)

    #    all_league_games = self.db.games[(self.db.games.league_id == league_id)&\
    #                                     (self.db.games.date >= start_date)][['ft_home', 'ft_away', 'date',
    #                                                                          'ht_home', 'ht_away', 'country',
    #                                                                          'home_team', 'season', 'away_team',
    #                                                                          'league_id']].copy()
        
    #    all_league_games['margin'] = (all_league_games.ft_home - all_league_games.ft_away).apply('abs')
    #    all_league_games['sign'] = all_league_games.apply(lambda x: 'X' if x.ft_home == x.ft_away\
    #                                                        else str(int(x.ft_home < x.ft_away) + 1),
    #                                                    axis = 1)


    #    probs_margins = {}
    #    margin_exp_value_given_sign = {}
    #    for sign in ['1', '2']:
    #        counts = all_league_games[all_league_games.sign == sign]['margin'].value_counts().sort_index() 
    #        margins = np.hstack([counts.index.values[:6], np.array(['>5'])])
    #        percents = np.hstack([counts.values[:6], np.sum(counts.values[6:])]) /\
    #                            len(all_league_games[all_league_games.sign == sign])

    #        probs_margins[sign] = {k: v for k, v in zip(margins, percents)}

    #        margin_exp_value_given_sign[sign] = np.sum(np.array([int(m.replace('>5', '6'))\
    #                                                 for m in probs_margins[sign].keys()])*\
    #                                                           np.array(list(probs_margins[sign].values())))

    #    first_season = all_league_games['season'].unique().min()
    #    for season in sorted(all_league_games.season.unique()):
    #        season_games = all_league_games[all_league_games.season == season].sort_values('date')
    #        season_teams = np.unique(season_games[['home_team', 'away_team']].values.reshape(-1, 1))\
    #                            .tolist()
    #        teams_ids = self.db.teams[(self.db.teams.team.isin(season_teams))&\
    #                                  (self.db.teams.country == country)].index.values
    #        season_start_date = datetime(int(season / 1e4), 7, 1)
            
    #        # start team form afresh
    #        self.teams_form = self.teams_form[~self.teams_form.team_id.isin(teams_ids)]
    #        self.teams_form = self.teams_form.append(pd.DataFrame\
    #                                                       .from_dict([{'team_id': tid,
    #                                                                    'home_delta': 0.,
    #                                                                    'away_delta': 0.,
    #                                                                    'home_t': 0,
    #                                                                    'away_t': 0}\
    #                                                                   for tid in teams_ids]))
            
    #        new_teams_entries = []
    #        if season != first_season:
    #            prev_season = season - 10001
                
    #            # initialize newly relegated teams with league average rating
    #            if not self.db.leagues.loc[league_id]['top_league']:
    #                upper_league = self.db.leagues.loc[self.db.leagues.loc[league_id]['upper_league_id']]\
    #                                                    ['league']
                    
    #                upper_league_teams = np.unique(self.db.games[(self.db.games.league_id == upper_league_id)&\
    #                                                             (self.db.games.season == prev_season)][['home_team',
    #                                                                                                    'away_team']]\
    #                                                    .values.reshape(-1, 1)).tolist()
    #                upper_prev_season_team_ids = self.db.teams[self.db.teams.team.isin(upper_league_teams)].index.values
                   
    #                relegated_teams_ids = np.intersect1d(teams_ids, upper_prev_season_team_ids)
    #                new_teams_entries += [{'team_id': tid,
    #                                       'league_id': league_id,
    #                                       'elo_rating': LEAGUE_INIT_RATING,
    #                                       'home_delta': 0.,
    #                                       'away_delta': 0.,
    #                                       'home_t': 0,
    #                                       'away_t': 0,
    #                                       'calibrating_game': True,
    #                                       'date': season_start_date} for tid in relegated_teams_ids]
                
    #            prev_season_teams = np.unique(self.db.games[(self.db.games.league_id == league_id)&\
    #                                                        (self.db.games.season == prev_season)][['home_team',
    #                                                                                                'away_team']]
    #                                                    .values.reshape(-1, 1)).tolist()
    #            prev_season_teams_ids = self.db.teams[self.db.teams.team.isin(prev_season_teams)].index.values
                
    #            promoted_teams_ids = [tid for tid in teams_ids if tid not in prev_season_teams_ids]
    #            new_teams_entries += [{'team_id': tid,
    #                                   'league_id': league_id,
    #                                   'elo_rating': LEAGUE_INIT_RATING,
    #                                   'home_delta': 0.,
    #                                   'away_delta': 0.,
    #                                   'home_t': 0,
    #                                   'away_t': 0,
    #                                   'calibrating_game': True,
    #                                   'date': season_start_date} for tid in promoted_teams_ids]
    #        else:
    #            new_teams_entries = [{'team_id': tid,
    #                                  'league_id': league_id,
    #                                  'elo_rating': LEAGUE_INIT_RATING,
    #                                  'home_delta': 0.,
    #                                  'away_delta': 0.,
    #                                  'home_t': 0,
    #                                  'away_t': 0,
    #                                  'calibrating_game': True,
    #                                  'date': season_start_date} for tid in teams_ids]
                
    #        self.teams_elo_score = self.teams_elo_score.append(pd.DataFrame.from_dict(new_teams_entries))
    #        self.__teams_ratings = {team_id: self.teams_elo_score[(self.teams_elo_score.team_id == team_id)]\
    #                                    .sort_values('date', ascending = False)['elo_rating'].values[0]\
    #                                         for team_id in teams_ids}

    #        n_calibration = calibration_rounds_first_season if season == first_season\
    #                                                        else calibration_rounds_following_seasons

    #        calibration_games = pd.DataFrame([])
    #        for team in season_teams:
    #            team_games = season_games[(season_games.home_team == team)|\
    #                                      (season_games.away_team == team)].head(n_calibration)

    #            calibration_games = pd.concat([calibration_games, team_games]).drop_duplicates()

    #        calibration_games.apply(lambda game: self.__update_elo(game, margin_exp_value_given_sign,
    #                                                             calibrating_game = True),
    #                                axis = 1)
            
    #        rest_of_games = pd.concat([season_games, calibration_games]).drop_duplicates(keep=False)            
    #        rest_of_games.apply(lambda game: self.__update_elo(game,
    #                                                         margin_exp_value_given_sign),
    #                            axis = 1) 

    #        self.__update_stats()
    #    self.__save_stats()