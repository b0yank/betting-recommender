import numpy as np
import pandas as pd
from datetime import datetime
import warnings

from constants import DB_PATH
from data_services import SoccerwayFootballDataService
from odds_providers import get_all_providers
from utils import odds_to_probabilities
from utils.match_columns import get_all_match_columns
from utils.odds_columns import get_all_odds_columns

class BookieAverageOddsEstimator:
    """Simple odds estimator. Uses coefficients from several bookmakers, converts them to probabilities and averages them to use as
       probabilities in games. Since bookie coefficients cannot be directly converted to probabilities (bookies lower coefficents on
       purpose, so using the reciprocal of coefficients gives more than 100% probability), the estimator assumes an equal lowering of
       the coefficients of all related events

       Example:
           Athletic Bilbao - Barcelona
           1(home win): 4.20    X(draw): 3.40   2(away win): 1.85
           
           The three events cover all possible outcomes, therefore their probabilities should add up to 1
           If the take the reciprocal of each coefficient:
           1/4.20 + 1/3.40 + 1/1.85 = 1.073
           There is an extra 7.3% that is there on purpose. It gives the bookmakers an even greater winnings margin.
           TheBookieAverageOddsEstimator assumes an equal split of this margin between the outcomes
           Therefore, the actual calculation would be:
               probability of home win = 1/(4.20*1.073)
               probability of draw     = 1/(3.40*1.073)
               probability of home win = 1/(1.85*1.073), which now sum to 1.
    """
    _BOOKIE_CSV_NAME_FORMAT = DB_PATH + 'odds_{}.csv'
    
    def __init__(self, football_database):
        self.db = football_database

        self.__bookie_odds_loaded = False
    
    def estimate_odds(self, league_ids, start_date, end_date):
        games = self.db.provide_games(league_ids, start_date, end_date)
        if not self.__bookie_odds_loaded:
            self.__load_bookie_odds()

        probs_all = []
        match_cols = get_all_match_columns()
        for bookie in self.bookies.values():
            # filter only games from current bookie for which we want to make estimations
            bookie_games = bookie.merge(games[match_cols], how='inner', on=match_cols)
            if len(bookie_games) == 0:
                continue

            probs_all.append(odds_to_probabilities(bookie_games))
            
        # calculate mean probabilites from all bookies
        probabilities = pd.concat(probs_all).groupby(match_cols).mean().reset_index()
        odds_cols = get_all_odds_columns()
        for c in [c for c in odds_cols if c not in probabilities.columns]:
            probabilities[c] = None
        return probabilities.astype({c: 'float64' for c in odds_cols})

    def __load_bookie_odds(self):
        self.bookies = {}
        for bookie in get_all_providers():
            bookie_name = bookie(self.db).name

            self.bookies[bookie_name] = pd.read_csv(self._BOOKIE_CSV_NAME_FORMAT.format(bookie_name))
            self.bookies[bookie_name]['date'] = pd.to_datetime(self.bookies[bookie_name]['date'])

        self.__bookie_odds_loaded = True