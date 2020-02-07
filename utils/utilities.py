import numpy as np

from constants import ACCEPTED_GOALS
from .match_columns import get_all_match_columns

_BOOKIE_GROUPS_LIST = [
        (['1', 'X', '2'], None),
        (['ht_1', 'ht_X', 'ht_2'], None),
        (['btts_yes', 'btts_no'], None),
        (['1-1', '1-X', '1-2', 'X-1', 'X-X', 'X-2', '2-1', '2-X', '2-2'], None),
        (['1/X'], '2'), (['X/2'], '1'), (['1/2'], 'X'), 
        (['ht_1/X'], 'ht_2'), (['ht_X/2'], 'ht_1'), (['ht_1/2'], 'ht_X'),
        (['first_half_btts_yes', 'first_half_btts_no'], None),
        (['second_half_btts_yes', 'second_half_btts_no'], None)] +\
        [([f'{ou}_{ng}' for ou in ['over', 'under']], None) for ng in ACCEPTED_GOALS] +\
        [([f'{ou}_{ng}_btts_{yn}' for ou in ['over', 'under'] for yn in ['yes', 'no']], None)\
                for ng in ACCEPTED_GOALS if ng > 1.5] +\
        [([f'{team}_&{ou}_{ng}' for team in ['home', 'away'] for ou in ['over', 'under']], 'X')\
                for ng in ACCEPTED_GOALS]

def fix_unicode(team_name):    
    return team_name.replace('\\u00c9', 'E').replace('\\u00e9', 'e').replace('\\u00ee', 'i')\
                    .replace('\\u00e1', 'a').replace('\\u00f1', 'n').replace('\\u00f3', 'o')\
                    .replace('\\u00ed', 'i').replace('\\u00e3', 'a').replace('\\u00fa', 'u')\
                    .replace('\\u00e7', 'c').replace('\\u0131', 'i').replace('\\u011f', 'g')\
                    .replace('\\u015f', 's').replace('\\u0130', 'I')

def odds_to_probabilities(odds):
    probs = odds[get_all_match_columns()].copy()
    for group in _BOOKIE_GROUPS_LIST:
        if any([g not in odds.columns for g in group[0]]):
            continue

        if group[1] is not None:
            probs_active = probs[~probs[group[1]].isna()]
        else:
            probs_active = probs

        probs.loc[probs_active.index.tolist(), 'group_max_coef'] = 1 if group[1] is None else 1 - probs_active[group[1]].values
        group_coef = odds.apply(lambda x: sum([1/v for v in x[group[0]].values]), axis=1)

        # skip group if all rows have NaN in at least one column
        rows_not_na_idxs = ~group_coef.isna()
        if sum(rows_not_na_idxs) == 0: continue;

        for col in group[0]:
            probs[col] = None
            probs.at[rows_not_na_idxs, col] = probs.loc[rows_not_na_idxs, 'group_max_coef'].values/(odds.loc[rows_not_na_idxs, col].values*\
                                                                                                    group_coef.loc[rows_not_na_idxs].values)

            probs[col] = probs[col].astype('float64')

    return probs.drop('group_max_coef', axis=1)

class PageNotLoadingError(Exception):
    def __init__(self, message):
        super().__init__(message)

class OddsExtractionFailedError(Exception):
    def __init__(self, message):
        super().__init__(message)
