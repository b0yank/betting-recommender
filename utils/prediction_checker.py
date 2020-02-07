import pandas as pd
import re

from constants import ACCEPTED_GOALS

class PredictionChecker:
    """ Class for checking predictions. Uses 'football_database' as data source.
    """
    _GOAL_PREDICTION_TYPES = set([f'{ou}_{ng}' for ou in ['over', 'under'] for ng in ACCEPTED_GOALS] +\
                                 [f'{ou}_{ng}_btts_{yn}' for ou in ['over', 'under'] for yn in ['yes', 'no'] for ng in ACCEPTED_GOALS if ng > 1.5] +\
                                 [f'{team}_&{ou}_{ng}' for team in ['home', 'away'] for ou in ['over', 'under'] for ng in ACCEPTED_GOALS])
    _GOALS_REGEX = regex = re.compile('(\d{1,2}\.\d)')

    def __init__(self, football_database):
        self.__construct_prediction_dict()
        self.db = football_database
    
    def check_predictions(self, predictions):
        return predictions.apply(lambda p: self.__check_prediction(p), axis=0)
        
    def __check_prediction(self, prediction):
        game = self.db.games[(self.db.games.home_team_id == prediction.home_team_id)&\
                             (self.db.games.away_team_id == prediction.away_team_id)&\
                             (self.db.games.date == prediction.date)]
        
        if len(game) == 0:
            raise ValueError('Game between teams {prediction.home_team_id} and {prediction.away_team_id}' +\
                             ' in season {prediction.season} not found.')
            
        elif len(game) > 1:
            raise ValueError('More than one games matched for teams {prediction.home_team_id} and' +\
                             ' {prediction.away_team_id} in season {prediction.season}.')
            
        ht_home, ht_away, ft_home, ft_away = game[['ht_home', 'ht_away', 'ft_home', 'ft_away']].values[0]
        if prediction.prediction_type in self._GOAL_PREDICTION_TYPES:
            ng = float(self._GOALS_REGEX.findall(prediction.prediction_type)[0])
            pred_general_type = prediction.prediction_type.replace(f'{ng}', '').replace('__', '_').strip('_')
            return self._GOALS_PRED_CHECKER[pred_general_type](ft_home, ft_away, ht_home, ht_away, ng)
        else:
            return self._PRED_CHECKER[prediction.prediction_type](ft_home, ft_away, ht_home, ht_away)
                          
    def __construct_prediction_dict(self):
        self._PRED_CHECKER = {
            '1': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 > ft_2),
            'X': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 == ft_2),
            '2': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 < ft_2),
            'btts_yes': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 > 0) and (ft_2 > 0),
            'btts_no': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 == 0) or (ft_2 == 0),
            'ht_1': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 > ht_2),
            'ht_X': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 == ht_2),
            'ht_2': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 < ht_2),
            'first_half_btts_yes': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 > 0) and (ht_2 > 0),
            'first_half_btts_no': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 == 0) or (ht_2 == 0),
            'second_half_btts_yes': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1-ht_1) > 0) and ((ft_2-ht_2) > 0),
            'second_half_btts_no': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1-ht_1) == 0) or ((ft_2-ht_2) == 0),
            '1/X': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 >= ft_2),
            'X/2': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 <= ft_2),
            '1/2': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 != ft_2),
            'ht_1/X': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 >= ht_2),
            'ht_X/2': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 <= ht_2),
            'ht_1/2': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 != ht_2),
            '1-1': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 > ht_2) and (ft_1 > ft_2),
            '1-X': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 > ht_2) and (ft_1 == ft_2),
            '1-2': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 > ht_2) and (ft_1 < ft_2),
            'X-1': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 == ht_2) and (ft_1 > ft_2),
            'X-X': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 == ht_2) and (ft_1 == ft_2),
            'X-2': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 == ht_2) and (ft_1 < ft_2),
            '2-1': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 < ht_2) and (ft_1 > ft_2),
            '2-X': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 < ht_2) and (ft_1 == ft_2),
            '2-2': lambda ft_1, ft_2, ht_1, ht_2: (ht_1 < ht_2) and (ft_1 < ft_2),
        }
                          
        self._PRED_CHECKER.update({f'over_{ng}': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1 + ft_2) > ng)\
                                                                                  for ng in ACCEPTED_GOALS})
        self._PRED_CHECKER.update({f'under_{ng}': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1 + ft_2) < ng)\
                                                                                  for ng in ACCEPTED_GOALS})
        self._PRED_CHECKER.update({f'home_&over_{ng}': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 > ft_2) and\
                                                                                      ((ft_1 + ft_2) > ng)\
                                                                                          for ng in ACCEPTED_GOALS})
        self._PRED_CHECKER.update({f'home_&under_{ng}': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 > ft_2) and\
                                                                                       ((ft_1 + ft_2) < ng)\
                                                                                          for ng in ACCEPTED_GOALS})
        self._PRED_CHECKER.update({f'away_&over_{ng}': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 < ft_2) and\
                                                                                      ((ft_1 + ft_2) > ng)\
                                                                                          for ng in ACCEPTED_GOALS})
        self._PRED_CHECKER.update({f'away_&under_{ng}': lambda ft_1, ft_2, ht_1, ht_2: (ft_1 < ft_2) and\
                                                                                       ((ft_1 + ft_2) < ng)\
                                                                                          for ng in ACCEPTED_GOALS})
        self._PRED_CHECKER.update({f'over_{ng}_btts_yes': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1 + ft_2) > ng) and\
                                                                                         ((ft_1 > 0) and (ft_2 > 0))\
                                                                                          for ng in ACCEPTED_GOALS\
                                                                                                      if ng > 1.5})
        self._PRED_CHECKER.update({f'over_{ng}_btts_no': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1 + ft_2) > ng) and\
                                                                                        ((ft_1 == 0) or (ft_2 == 0))\
                                                                                          for ng in ACCEPTED_GOALS})
        self._PRED_CHECKER.update({f'under_{ng}_btts_yes': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1 + ft_2) < ng) and\
                                                                                          ((ft_1 > 0) and (ft_2 > 0))\
                                                                                          for ng in ACCEPTED_GOALS\
                                                                                                      if ng > 1.5})
        self._PRED_CHECKER.update({f'under_{ng}_btts_no': lambda ft_1, ft_2, ht_1, ht_2: ((ft_1 + ft_2) < ng) and\
                                                                                         ((ft_1 == 0) or (ft_2 == 0))
                                                                                          for ng in ACCEPTED_GOALS})

        self._GOALS_PRED_CHECKER = {
            'over':             lambda ft_1, ft_2, ht_1, ht_2, ng: (ft_1 + ft_2) > ng,
            'under':            lambda ft_1, ft_2, ht_1, ht_2, ng: (ft_1 + ft_2) < ng,
            'home_&over':       lambda ft_1, ft_2, ht_1, ht_2, ng: (ft_1 > ft_2) and ((ft_1 + ft_2) > ng),
            'home_&under':      lambda ft_1, ft_2, ht_1, ht_2, ng: (ft_1 > ft_2) and ((ft_1 + ft_2) < ng),
            'away_&over':       lambda ft_1, ft_2, ht_1, ht_2, ng: (ft_1 < ft_2) and ((ft_1 + ft_2) > ng),
            'away_&under':      lambda ft_1, ft_2, ht_1, ht_2, ng: (ft_1 < ft_2) and ((ft_1 + ft_2) < ng),
            'over_btts_yes':    lambda ft_1, ft_2, ht_1, ht_2, ng: ((ft_1 + ft_2) > ng) and ((ft_1 > 0) and (ft_2 > 0)),
            'under_btts_yes':   lambda ft_1, ft_2, ht_1, ht_2, ng: ((ft_1 + ft_2) < ng) and ((ft_1 > 0) and (ft_2 > 0)),
            'over_btts_no':     lambda ft_1, ft_2, ht_1, ht_2, ng: ((ft_1 + ft_2) > ng) and ((ft_1 == 0) or (ft_2 == 0)),
            'under_btts_no':    lambda ft_1, ft_2, ht_1, ht_2, ng: ((ft_1 + ft_2) < ng) and ((ft_1 == 0) or (ft_2 == 0)),
        }