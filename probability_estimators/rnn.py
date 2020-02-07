import numpy as np
import pandas as pd
from scipy.stats import poisson, skellam
import warnings
from datetime import datetime

from keras import backend as K
import tensorflow.keras.activations as activations
from tensorflow.keras.callbacks import EarlyStopping, TerminateOnNaN
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense, InputLayer, LSTM, Activation, BatchNormalization, GRU
from tensorflow.keras.optimizers import SGD, Adam

from constants import ACCEPTED_GOALS, DB_PATH

class RnnProbabilityEstimator:
    """ Uses a recurrent neural network, pretrained to use up to 'n_timestep_games' of a team's previous games
        as input, to provide probabilities for certain events in future games. Models poisson distributions for
        the number of goals scored by each team, both before half-time and before full-time, and uses those
        distributions to estimate probabilities for various match outcomes.

        Parameters:
           'football_database' - Database of past football games on which the estimations are based.
           'n_timestep_games'  - Maximum number of games in the past to be used for estimations.

    """
    _MIN_GAMES_WARNING = 5

    _USED_COLS = ['is_home',
                  'possession_team',
                  'shots_off_opponent',
                  'shots_off_team',
                  'shots_on_opponent',
                  'shots_on_team']

    __model_structure_htft = Sequential([
            InputLayer(input_shape = (None, 6)),
            GRU(64, return_sequences = True),
            Activation('relu'),
            Dense(32),
            BatchNormalization(),
            Activation('relu'),
            Dense(4),
            Activation(K.exp)
        ])

    __model_structure_second_half = Sequential([
            InputLayer(input_shape = (None, 8)),
            GRU(64, return_sequences = True),
            Activation('relu'),
            Dense(32),
            BatchNormalization(),
            Activation('relu'),
            Dense(2),
            Activation(K.exp)
        ])
    
    def __init__(self, football_database, n_timestep_games=20):
        self.db = football_database
        self.n_timestep_games = n_timestep_games
        
        self.goals_htft_model = self.__model_structure_htft
        self.goals_htft_model.load_weights(DB_PATH + 'goals_htft.keras')

        self.goals_second_half_model = self.__model_structure_second_half
        self.goals_second_half_model.load_weights(DB_PATH + 'goals_second_half.keras')
        
    def estimate_odds(self, league_ids, start_date, end_date, max_goals=8):
        games = self.db.provide_games(league_ids, start_date, end_date)

        # fetch relevant data from previous games of both home and away team to propagate through network
        (home_array, home_ht), (away_array, away_ht) = self.__prepare_arrays(games, self.n_timestep_games)

        home_preds = self.goals_htft_model.predict(home_array)
        away_preds = self.goals_htft_model.predict(away_array)
        
        home_predictions = [preds[self.__n_home_games[idx] - 1] for idx, preds in enumerate(home_preds)]
        away_predictions = [preds[self.__n_away_games[idx] - 1] for idx, preds in enumerate(away_preds)]
        
        columns = [f'{hg}:{ag}' for hg in range(max_goals) for ag in range(max_goals)]

        # get predictions for home team's second half performance
        home_second_half_predictions = np.array([self.goals_second_half_model.predict(np.dstack([home_array, np.ones(home_array.shape[:2] + (2,))*np.array([hg, ag])]))\
                                                        for hg in range(max_goals) for ag in range(max_goals)]).swapaxes(0, 1).swapaxes(-2, 1)
        # since the number of games a team has played during the season varies and could be less than self.n_timestep_games, cut junk predictions and
        # use ones made after the timestep with the last game played
        home_second_half_predictions = home_second_half_predictions[range(len(home_second_half_predictions)), np.array(self.__n_home_games)-1, :, :]
        arr_list = [home_second_half_predictions[:, i, ...] for i in range(home_second_half_predictions.shape[1])]
        home_second_half_predictions = pd.DataFrame(list(zip(*arr_list)), columns = columns).to_dict(orient='records')

        # get predictiosn for away team's second half performance
        away_second_half_predictions = np.array([self.goals_second_half_model.predict(np.dstack([away_array, np.ones(away_array.shape[:2] + (2,))*np.array([hg, ag])]))\
                                                        for hg in range(max_goals) for ag in range(max_goals)]).swapaxes(0, 1).swapaxes(-2, 1)
        # since the number of games a team has played during the season varies and could be less than self.n_timestep_games, cut junk predictions and
        # use ones made after the timestep with the last game played
        away_second_half_predictions = away_second_half_predictions[range(len(away_second_half_predictions)), np.array(self.__n_away_games)-1, :, :]
        arr_list = [away_second_half_predictions[:, i, ...] for i in range(away_second_half_predictions.shape[1])]
        away_second_half_predictions = pd.DataFrame(list(zip(*arr_list)), columns = columns).to_dict(orient='records')

        odds = [self.__estimate_game_odds(home_preds, away_preds, home_ht_preds, away_ht_preds, game_info, max_goals=max_goals)\
                    for home_preds, away_preds, home_ht_preds, away_ht_preds, game_info in\
                    zip(home_predictions, away_predictions, home_second_half_predictions, away_second_half_predictions,
                        games[['league_id', 'home_team_id', 'away_team_id', 'date']].to_dict(orient='records'))]

        return pd.DataFrame.from_dict(odds)
    
    def __estimate_game_odds(self, home_predictions, away_predictions, home_second_half_predictions, away_second_half_predictions, game_info, max_goals=8):
        home_ht_goals, home_ft_goals, home_ht_conc, home_ft_conc = home_predictions
        away_ht_goals, away_ft_goals, away_ht_conc, away_ft_conc = away_predictions

        # Rnn models make predictions both for the number of goals each team will score and for the number of goals it will concede.
        # This prediction is the mean of a poisson distribution. For each team, use the expected number of goals it will score averaged
        # with the expected number of goals the other team will concede as the mean of the poisson distribution representing how many goals
        # the first team will score. Do this for full-time and half-time predictions
        home_ft_mean = (home_ft_goals + away_ft_conc)/2
        home_ht_mean = (home_ht_goals + away_ht_conc)/2
        away_ft_mean = (away_ft_goals + home_ft_conc)/2
        away_ht_mean = (away_ht_goals + home_ht_conc)/2

        # same as above, but for second-half predictions
        home_sh_mean = {k: (home_second_half_predictions[k][0] + away_second_half_predictions[k][1])/2 for k in home_second_half_predictions.keys()}
        away_sh_mean = {k: (away_second_half_predictions[k][0] + home_second_half_predictions[k][1])/2 for k in away_second_half_predictions.keys()}

        btts = (1-poisson.cdf(0, home_ft_mean))*(1-poisson.cdf(0, away_ft_mean))
        btts_ht = (1-poisson.cdf(0, home_ht_mean))*(1-poisson.cdf(0, away_ht_mean)) 
        second_half_btts = sum([(1-poisson.cdf(0, sh_h[1]))*\
                                (1-poisson.cdf(0, sh_a[1]))*\
                                (poisson.pmf(int(sh_h[0].split(':')[0]), home_ht_mean))*\
                                (poisson.pmf(int(sh_a[0].split(':')[1]), away_ht_mean))\
                                    for sh_h, sh_a in zip(home_sh_mean.items(), away_sh_mean.items())])
                           
        prob_1_ft = sum([poisson.pmf(ngoals, away_ft_mean)*(1-poisson.cdf(ngoals, home_ft_mean)) for ngoals in range(max_goals)])
        prob_X_ft = sum([poisson.pmf(ngoals, home_ft_mean)*(poisson.pmf(ngoals, away_ft_mean)) for ngoals in range(max_goals)])
        prob_2_ft = sum([poisson.pmf(ngoals, home_ft_mean)*(1-poisson.cdf(ngoals, away_ft_mean)) for ngoals in range(max_goals)])
        prob_1_ht = sum([poisson.pmf(ngoals, away_ht_mean)*(1-poisson.cdf(ngoals, home_ht_mean)) for ngoals in range(max_goals)])
        prob_X_ht = sum([poisson.pmf(ngoals, home_ht_mean)*(poisson.pmf(ngoals, away_ht_mean)) for ngoals in range(max_goals)])
        prob_2_ht = sum([poisson.pmf(ngoals, home_ht_mean)*(1-poisson.cdf(ngoals, away_ht_mean)) for ngoals in range(max_goals)])

        game_odds = {
            # game info
            'league_id': game_info['league_id'],
            'home_team_id': game_info['home_team_id'],
            'away_team_id': game_info['away_team_id'],
            'date': game_info['date'],
            # main
            '1': prob_1_ft,
            'X': prob_X_ft,
            '2': prob_2_ft,
            'btts_yes': btts,
            'btts_no': 1-btts,
            # half
            'ht_1': prob_1_ht,
            'ht_X': prob_X_ht,
            'ht_2': prob_2_ht,
            'first_half_btts_yes': btts_ht,
            'first_half_btts_no': 1-btts_ht,
            'second_half_btts_yes': second_half_btts,
            'second_half_btts_no': 1-second_half_btts,
            # double chance
            '1/X': prob_1_ft + prob_X_ft,
            'X/2': prob_X_ft + prob_2_ft,
            '1/2': prob_1_ft + prob_2_ft,
            # ht double chance
            'ht_1/X': prob_1_ht + prob_X_ht,
            'ht_X/2': prob_X_ht + prob_2_ht,
            'ht_1/2': prob_1_ht + prob_2_ht,
            # ht-ft
            '1-1': sum([(poisson.pmf(g, home_ht_mean))*(poisson.pmf(g-ngoals, away_ht_mean))*\
                        (1-skellam.cdf(-ngoals, home_sh_mean[f'{g}:{g-ngoals}'], away_sh_mean[f'{g-ngoals}:{g}']))\
                            for ngoals in range(1, max_goals) for g in range(ngoals, max_goals)]),
            '1-X':  sum([(poisson.pmf(g, home_ht_mean))*(poisson.pmf(g-ngoals, away_ht_mean))*\
                        (skellam.pmf(-ngoals, home_sh_mean[f'{g}:{g-ngoals}'], away_sh_mean[f'{g-ngoals}:{g}']))\
                            for ngoals in range(1, max_goals) for g in range(ngoals, max_goals)]),
            '1-2': sum([(poisson.pmf(g, home_ht_mean))*(poisson.pmf(g-ngoals, away_ht_mean))*\
                        (1-skellam.cdf(ngoals, away_sh_mean[f'{g-ngoals}:{g}'], home_sh_mean[f'{g}:{g-ngoals}']))\
                            for ngoals in range(1, max_goals) for g in range(ngoals, max_goals)]),
            'X-1': sum([(poisson.pmf(g, home_ht_mean))*(poisson.pmf(g, away_ht_mean))*\
                        (1-skellam.cdf(0, home_sh_mean[f'{g}:{g}'], away_sh_mean[f'{g}:{g}'])) for g in range(max_goals)]),
            'X-X':  sum([(poisson.pmf(g, home_ht_mean))*(poisson.pmf(g, away_ht_mean))*\
                         (skellam.pmf(0, home_sh_mean[f'{g}:{g}'], away_sh_mean[f'{g}:{g}'])) for g in range(max_goals)]),
            'X-2': sum([(poisson.pmf(g, home_ht_mean))*(poisson.pmf(g, away_ht_mean))*\
                        (1-skellam.cdf(0, away_sh_mean[f'{g}:{g}'], home_sh_mean[f'{g}:{g}'])) for g in range(max_goals)]),
            '2-2': sum([(poisson.pmf(g, away_ht_mean))*(poisson.pmf(g-ngoals, home_ht_mean))*\
                        (1-skellam.cdf(-ngoals, away_sh_mean[f'{g}:{g-ngoals}'], home_sh_mean[f'{g-ngoals}:{g}']))\
                            for ngoals in range(1, max_goals) for g in range(ngoals, max_goals)]),
            '2-X':  sum([(poisson.pmf(g, away_ht_mean))*(poisson.pmf(g-ngoals, home_ht_mean))*\
                        (skellam.pmf(-ngoals, away_sh_mean[f'{g}:{g-ngoals}'], home_sh_mean[f'{g-ngoals}:{g}']))\
                            for ngoals in range(1, max_goals) for g in range(ngoals, max_goals)]),
            '2-1': sum([(poisson.pmf(g, away_ht_mean))*(poisson.pmf(g-ngoals, home_ht_mean))*\
                        (1-skellam.cdf(ngoals, home_sh_mean[f'{g-ngoals}:{g}'], away_sh_mean[f'{g}:{g-ngoals}']))\
                            for ngoals in range(1, max_goals) for g in range(ngoals, max_goals)])
        }

        ft_over = {f'over_{ng}': 1-poisson.cdf(ng, home_ft_mean+away_ft_mean) for ng in ACCEPTED_GOALS}
        ft_under = {f'under_{k[-3:]}': 1-v for k,v in ft_over.items()}

        result_tg = {f'home_&over_{ng}': sum([poisson.pmf(g, away_ft_mean)*(1-poisson.cdf(max(ng-g, g), home_ft_mean)) for g in range(max_goals)])\
                                                    for ng in ACCEPTED_GOALS if ng > 1}
        result_tg.update({f'home_&under_{ng}': sum([poisson.pmf(g, home_ft_mean)*(poisson.cdf(min(ng-g, g), away_ft_mean)-poisson.pmf(min(ng-g, g), away_ft_mean))\
                                                    for g in range(1, int(np.ceil(ng)))]) for ng in ACCEPTED_GOALS if ng > 1})
        result_tg.update({f'away_&over_{ng}': sum([poisson.pmf(g, home_ft_mean)*(1-poisson.cdf(max(ng-g, g), away_ft_mean)) for g in range(max_goals)])\
                                                    for ng in ACCEPTED_GOALS if ng > 1})
        result_tg.update({f'away_&under_{ng}': sum([poisson.pmf(g, away_ft_mean)*(poisson.cdf(min(ng-g, g), home_ft_mean)-poisson.pmf(min(ng-g, g), home_ft_mean))\
                                                    for g in range(1, int(np.ceil(ng)))]) for ng in ACCEPTED_GOALS if ng > 1})
        tg_btts = {f'over_{ng}_btts_yes': sum([poisson.pmf(gh, home_ft_mean)*poisson.pmf(ga, away_ft_mean) for gh in range(1, max_goals)\
                                                    for ga in range(max(1, int(np.ceil(ng)-gh)), max_goals)]) for ng in ACCEPTED_GOALS if ng > 1.5}
        tg_btts.update({f'over_{ng}_btts_no': (1-poisson.cdf(ng, home_ft_mean))*poisson.pmf(0, away_ft_mean) +\
                                              (1-poisson.cdf(ng, away_ft_mean))*poisson.pmf(0, home_ft_mean) for ng in ACCEPTED_GOALS if ng > 1.5})
        tg_btts.update({f'under_{ng}_btts_yes': sum([poisson.pmf(gh, home_ft_mean)*poisson.pmf(ga, away_ft_mean) for gh in range(1, int(ng))\
                                                    for ga in range(1, 1+int(ng)-gh)]) for ng in ACCEPTED_GOALS if ng > 1.5})
        tg_btts.update({f'under_{ng}_btts_no': poisson.cdf(ng, home_ft_mean)*poisson.pmf(0, away_ft_mean) +\
                                               poisson.cdf(ng, away_ft_mean)*poisson.pmf(0, home_ft_mean) -\
                                               poisson.pmf(0, home_ft_mean)*poisson.pmf(0, away_ft_mean) for ng in ACCEPTED_GOALS if ng > 1.5})
        game_odds.update(ft_over)
        game_odds.update(ft_under)
        game_odds.update(result_tg)
        game_odds.update(tg_btts)
        
        return game_odds
    
    def __prepare_arrays(self, games, n_prev_games = 20):
        """Prepares arrays of past games data for propagation through the neural networks.
        """
        self.__home_team_games, self.__away_team_games, self.__home_next_game_ht, self.__away_next_game_ht, self.__n_home_games, self.__n_away_games = [], [], [], [], [], []
        self.__games_by_team_sorted = self.db.games_by_team.sort_values('date', axis = 0, ascending = True)
        games.apply(self.__get_previous_games, axis = 1)
        
        return (np.array(self.__home_team_games), np.array(self.__home_next_game_ht)), (np.array(self.__away_team_games), np.array(self.__away_next_game_ht))

    def __get_previous_games(self, game):
        """ Returns up to self.n_timestep_games most recent games played played by both teams playing in parameter 'game'
            during the game's season
        """
        season = int(self.db.date_to_season(game.date))

        games_home_team = self.__games_by_team_sorted[(self.__games_by_team_sorted.team_id == game.home_team_id)&\
                                                      (self.__games_by_team_sorted.date < game.date)&\
                                                      (self.__games_by_team_sorted.season == season)]\
                                                            .tail(self.n_timestep_games)
                                                                   
        games_away_team = self.__games_by_team_sorted[(self.__games_by_team_sorted.team_id == game.away_team_id)&\
                                                      (self.__games_by_team_sorted.date < game.date)&\
                                                      (self.__games_by_team_sorted.season == season)]\
                                                            .tail(self.n_timestep_games)
                                                                  
                
        if len(games_home_team) == 0 or len(games_away_team) == 0:
            raise ValueError(f'No previous games found for game between teams with ids {game.home_team_id}' +\
                             f' and {game.away_team_id}')
        if len(games_home_team) < self._MIN_GAMES_WARNING + 1 or len(games_away_team) < self._MIN_GAMES_WARNING + 1:
            warnings.warn(f'Fewer than {self._MIN_GAMES_WARNING} previous games found for ' +\
                          f'game between teams with ids {game.home_team_id} and {game.away_team_id}')

        games_home_ht_goals = games_home_team[['ht_goals_team', 'ht_goals_opponent']].values[1:]
        games_away_ht_goals = games_away_team[['ht_goals_team', 'ht_goals_opponent']].values[1:]

        games_home_team = games_home_team[self._USED_COLS].values[:-1]
        games_away_team = games_away_team[self._USED_COLS].values[:-1]
        
        self.__n_home_games.append(games_home_team.shape[0])
        self.__n_away_games.append(games_away_team.shape[0])
        timesteps_left_home = self.n_timestep_games - games_home_team.shape[0]
        timesteps_left_away = self.n_timestep_games - games_away_team.shape[0]

        games_home_team = np.vstack([games_home_team, np.zeros((timesteps_left_home, games_home_team.shape[1]))])
        games_away_team = np.vstack([games_away_team, np.zeros((timesteps_left_away, games_away_team.shape[1]))])
        games_home_ht_goals = np.vstack([games_home_ht_goals, np.zeros((timesteps_left_home, games_home_ht_goals.shape[1]))])
        games_away_ht_goals = np.vstack([games_away_ht_goals, np.zeros((timesteps_left_away, games_away_ht_goals.shape[1]))])
 
        self.__home_team_games.append(games_home_team)
        self.__away_team_games.append(games_away_team)
        self.__home_next_game_ht.append(games_home_ht_goals)
        self.__away_next_game_ht.append(games_away_ht_goals)
