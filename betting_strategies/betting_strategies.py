import numpy as np
import pandas as pd
from enum import Enum

from utils import odds_to_probabilities
from utils.match_columns import get_all_match_columns
from utils.odds_columns import get_all_odds_columns

class BetPickCriterion(Enum):
    PROBABILITY = 0
    COEFFICIENT = 1
    DELTA = 2
    KELLY = 3

class BetPicker:
    """ Picks bets according to certain criteria. Specifically, for each game it maximizes the 'maximizing_criterion' conditioned
        on the 'threshold_criterion' being met. Criteria are given in he BetPickCriterion enumeration.
        
        Example:
            (maximizing_criterion = BetPickCriterion.PROBABILITY, threshold_criterion = BetPickCriterion.COEFFICIENT,
             min_maximizing = 0.8, min_threshold = 1.3): Picks the bet type with the maximum probability if the coefficient for that
             bet type is at least 1.30 and the model's estimated probability of that event is at least 80%. Otherwise ignores this match
    """
    @staticmethod
    def find_potential_bets(model_proba, bookie_odds, maximizing_criterion, threshold_criterion, min_maximizing, min_threshold):
        match_cols = get_all_match_columns()
        odds_cols = get_all_odds_columns()

        # we really only need odds for games which we are trying to predict currently
        bookie_odds = bookie_odds.merge(model_proba[match_cols],
                                        on=match_cols, how='inner')

        # and only really need probabilities for games for which we also have odds
        model_proba = model_proba.merge(bookie_odds[match_cols],
                                        on=match_cols, how='inner')

        # get the correct maximizing and threshold tables given the criterion types
        max_table = BetPicker.__get_table(model_proba, bookie_odds, maximizing_criterion)
        thresh_table = BetPicker.__get_table(model_proba, bookie_odds, threshold_criterion)
        
        max_suffix = '_max'; max_cols = [f'{c}_max' for c in odds_cols];
        thresh_suffix = '_thresh'; thresh_cols = [f'{c}_thresh' for c in odds_cols]

        # use maximum value of maximizing_criterion for prediction_type provided that min_threshold is fulfilled
        merged = max_table.merge(thresh_table, on=match_cols, suffixes=(max_suffix, thresh_suffix))
        merged['prediction_type'] = merged[(merged[thresh_cols] >= min_threshold)\
                                        .rename(columns={c: c.replace(thresh_suffix, max_suffix) for c in thresh_cols})][max_cols]\
                                        .idxmax(axis=1).str.replace(max_suffix, '')
        merged = merged[~merged.prediction_type.isna()]
        merged = merged.rename(columns={f'{c}_max': c for c in odds_cols})
        merged = merged[merged.apply(lambda x: x[x.prediction_type] > min_maximizing, axis=1)]
        if len(merged) == 0:
            return pd.DataFrame([])

        bets = model_proba
        bets = bets.merge(merged[['prediction_type'] + match_cols], on=match_cols)

        bets['estimated_probability'] = bets.apply(lambda x: x[x.prediction_type], axis=1)
        bets = bets.drop(odds_cols, axis=1)
        
        bets = bets.merge(bookie_odds, left_on=match_cols, right_on=match_cols)
        bets['bookie_coefficient'] = bets.apply(lambda x: x[x.prediction_type], axis=1)
        bets = bets.drop(odds_cols, axis=1)
        return bets

    @staticmethod
    def __get_table(model_proba, bookie_odds, criterion):
        if criterion == BetPickCriterion.PROBABILITY:
            return model_proba
        elif criterion == BetPickCriterion.COEFFICIENT:
            return bookie_odds
        elif criterion == BetPickCriterion.DELTA:
            bookie_proba = odds_to_probabilities(bookie_odds)
            match_cols = get_all_match_columns()

            return model_proba.set_index(match_cols).subtract(bookie_proba.set_index(match_cols)).reset_index()
        elif criterion == BetPickCriterion.KELLY:
            match_cols = get_all_match_columns()
            odds_cols = get_all_odds_columns()

            # probability of losing the bet divided by the probability of winnning
            q_over_p = (1 - model_proba[odds_cols]) / model_proba[odds_cols]
            q_over_p[match_cols] = model_proba[match_cols]

            # pure profit in bookmaker's coefficient
            bookie_profit = bookie_odds[odds_cols] - 1
            bookie_profit[match_cols] = bookie_odds[match_cols]

            combined_table = q_over_p.merge(bookie_profit, on=match_cols, suffixes=('_prob', '_coef'), how='inner')
            for col in odds_cols:
                combined_table[col] = combined_table.apply(lambda x: x[f'{col}_coef'] - x[f'{col}_prob'], axis=1)
    
            return combined_table.drop([f'{c}_prob' for c in odds_cols] +\
                                       [f'{c}_coef' for c in odds_cols], axis=1)
        else:
            raise ValueError('Invalid maximizing criterion.')

class RandomBetPicker:
    """ Picks a bet for each game on random. Useful in baseline tests or in combination with the Kelly criterion for comparing
        probability distributions:
            Run RandomBetPicker on a set of games N times with each probability distribution. Given that
            the Kelly criterion decides which bets to use and what amount to bet on them purely based on the estimated pribabilities
            (and the bookmaker coefficients) - the more accurate the probability distribution is, the higher the percentage of simulations
            that will end up with a profit).
    """
    @staticmethod
    def find_potential_bets(model_proba, bookie_odds):
        match_cols = get_all_match_columns()
        odds_cols = get_all_odds_columns()

        merged = bookie_odds.merge(model_proba, on=match_cols, suffixes=('_bookie', '_estimator'))

        bets = []
        for idx, row in merged.iterrows():
            valid_cols = [c for c in odds_cols if not np.isnan(row[f'{c}_bookie'])]
            if len(valid_cols) == 0:
                continue
            prediction_type = np.random.choice(valid_cols, (1,))[0]
            bookie_coefficient = row[f'{prediction_type}_bookie']
            estimated_probability = row[f'{prediction_type}_estimator']

            new_bet = {'prediction_type': prediction_type,
                       'bookie_coefficient': bookie_coefficient,
                       'estimated_probability': estimated_probability}
            for match_col in match_cols:
                new_bet[match_col] = row[match_col]

            bets.append(new_bet)


        df = pd.DataFrame.from_dict(bets)
        return df.dropna()