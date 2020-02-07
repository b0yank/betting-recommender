#import numpy as np
import pandas as pd
from datetime import datetime
import time
import sys
import inspect

from textdistance import hamming, jaro_winkler, cosine


from driver import Driver
from constants import ACCEPTED_GOALS, DB_PATH, BOOKIE_HEADERS_CSV_PATH
from utils import OddsExtractionFailedError, Logging
from utils.odds_columns import get_all_odds_columns
from utils.match_columns import get_all_match_columns

_BOOKIE_LEAGUE_URLS = {
    'bet365': 'https://www.bet365.com/#/AC/B1/C1/D13/{}/F2/',
    'bwin': 'https://sports.bwin.com/en/sports#leagueIds={}&sportId=4',
    'coral': 'https://sports.coral.co.uk/competitions/football/football-{}/{}',
    'efbet': 'https://www.efbet.com/UK/sports#bo-navigation=282241.1,{},{}&action=market-group-list'
}

def get_all_providers():
    module = sys.modules[globals()['__name__'].split('.')[0]]
    odds_provider_names = [n[0] for n in inspect.getmembers(module, inspect.isclass)]
    return [p for p in [getattr(module, pn) for pn in odds_provider_names if pn != 'FootballDataOddsProvider'] if issubclass(p, OddsProvider)]

class OddsProvider:
    """Abstract odds provider class.
       Odds providers are crawlers extracting bookie coefficients data from specific websites.
    """
    def __init__(self, football_database, logger = None, max_trials = 3, trial_wait_time = 5):
        self.db = football_database
        self.logger = logger
        self.max_trials = max_trials
        self.trial_wait_time = trial_wait_time

        self._bookie_name = type(self).__name__.replace('OddsProvider', '').lower()
        if self._bookie_name not in _BOOKIE_LEAGUE_URLS:
            raise ValueError(f'No league url listed for bookmaker {self._bookie_name}')

        self._league_url = _BOOKIE_LEAGUE_URLS[self._bookie_name]

        self._ODDS_CSV_PATH = DB_PATH + 'odds_{}.csv'.format(self._bookie_name)
        self._odds = None

        self._teams_quick_map = pd.read_csv(DB_PATH + 'teams_quick_map_' + self._bookie_name + '.csv')
        self._teams_quick_map = {k: int(v) for k, v in self._teams_quick_map[['bookie_team_name', 'team_id']].values}

        self._league_codes = pd.read_csv(DB_PATH + 'league_codes_' + self._bookie_name + '.csv')
        self._league_codes = {k: v for k, v in self._league_codes[['league_id', 'league_code']].values}

        self.__load_headers()

        self._driver = None
        self.__driver_started = False

        self._max_game_days_ahead = 7

        self._BOOKIES_COLUMNS = get_all_match_columns() + get_all_odds_columns()

    @property
    def name(self): return self._bookie_name;
        
    @property
    def odds(self):
        if self._odds is None:
            self._odds = pd.read_csv(self._ODDS_CSV_PATH)
            self._odds.date = pd.to_datetime(self._odds.date)
        return self._odds

    @property
    def LEAGUE_URL(self):
        if self._league_url is None: raise NotImplementedError(f'League url for bookie {self._bookie_name} must be set.');
        return self._league_url

    def set_driver(self, driver):
        self._driver = driver
        self.__driver_started = True

    def provide_odds(self, league_ids, start_date, end_date):
        games = self.db.games[(self.db.games.date >= start_date)&\
                              (self.db.games.date <= end_date)&\
                              (self.db.games.league_id.isin(league_ids))]

        return self.odds.merge(games[['home_team_id', 'away_team_id', 'date']],
                               on=['home_team_id', 'away_team_id', 'date'],
                               how='inner')

    def update_odds_db(self, max_game_days_ahead = 7):
        self._max_game_days_ahead = max_game_days_ahead

        new_odds = pd.DataFrame([])
        for idx in range(len(self.db.leagues)):
            try:
                league_odds = self.extract_league_odds(idx, close_driver=False)

                data_columns = [c for c in self._BOOKIES_COLUMNS if c not in league_odds.columns]
                if len(data_columns) > 0 and self.logger is not None:
                    self.logger.log_message(f'Provider {self.name} could not find odds for columns {data_columns}', Logging.WARNING)

                new_odds = new_odds.append(league_odds, ignore_index=True)
            except Exception as exc:
                if self.logger is not None:
                    self.logger.log_message(str(exc), Logging.ERROR)
                    self.logger.log_message(f'Odds for league with id {idx} failed to be updated.', Logging.ERROR)

        self._close_driver()
        if self.logger is not None:
            self.logger.add_newline()

        existing_odds_idxs = self.odds.reset_index()[['home_team_id', 'away_team_id', 'date', 'index']]\
                                      .merge(new_odds[['home_team_id', 'away_team_id', 'date']],
                                             on=['home_team_id', 'away_team_id', 'date'])['index'].tolist()
            
        odds = self.odds.drop(existing_odds_idxs, axis=0).append(new_odds, ignore_index=True)
        odds.to_csv(self._ODDS_CSV_PATH, index_label=False)

    def extract_league_odds(self, league_id, close_driver = True):
        if self._driver is None:
            if self.logger is not None:
                self.logger.log_message('No driver was explicitly set. Reverting to default webdriver', Logging.INFO)
            self.set_driver(Driver(logger=self.logger))

        if not self.__driver_started:
            self._start_driver()

        self._open_league_url(league_id, close_driver)
        games_odds = self.__extract_bookie_league_odds(league_id)

        if close_driver:
            self._close_driver()

        odds = pd.DataFrame([],  columns=self._BOOKIES_COLUMNS)
        return odds.append(pd.DataFrame.from_dict(games_odds))

    def extract_match_odds(self, odds_item, close_driver = False):
        raise NotImplementedError

    def _get_odds_link_items(self):
        raise NotImplementedError

    def _open_league_url(self, league_id, close_driver = True):
        if self._driver is None:
            if self.logger is not None:
                self.logger.log_message('No driver was explicitly set. Reverting to default webdriver', Logging.INFO)
            self.set_driver(Driver(logger=self.logger))

        if not self.__driver_started:
            self._start_driver()

        league_url = self._get_league_url(league_id)
        if league_url is None:
            if self.logger is not None:
                self.logger.log_message(f'League with id {league_id} not supported.', Logging.ERROR)
            return pd.DataFrame([])

        try:
            self._driver.get(league_url)
        except:
            if close_driver:
                self._close_driver()
                
            error_msg = 'Odds for league with id {league_id} unavailable.'
            if self.logger is not None:
                self.logger.log_message(error_msg, Logging.INFO)
            raise ValueError(error_msg)
        
        time.sleep(4)

    def _get_team_id(self, team_name, league_id):
        country = self.db.leagues.loc[league_id, 'country']
        country_teams = self.db.teams[self.db.teams.country == country]
        
        team_lower = team_name.lower()
        if team_lower in self._teams_quick_map:
            return self._teams_quick_map[team_lower]
       
        dists = country_teams.apply(lambda x: jaro_winkler(x.team.lower(), team_lower) +\
                                              3*cosine(x.team.lower(), team_lower) +\
                                              hamming.normalized_similarity(x.team.lower(), team_lower),
                                    axis = 1)
        idxmax = dists.idxmax()
        if dists.loc[idxmax] < 3.5 and self.logger is not None:
            self.logger.log_message(f'Low name similarity - team {team_name} may not exist in teams database', Logging.WARNING)
            
        return idxmax

    def _start_driver(self):
        if self._driver is None:
            raise ValueError('Driver must be set before it is started.')

        self._driver.start()
        self.__driver_started = True
        
    def _close_driver(self):
        self._driver.close()
        self.__driver_started = False

    def _get_league_url(self, league_id):
        if league_id not in self._league_codes or self._league_codes[league_id] is None:
            return None
        
        league_code = self._league_codes[league_id]
        return self.LEAGUE_URL.format(league_code)

    def __extract_bookie_league_odds(self, league_id):
        odds_generator = self._get_odds_link_items()

        games_odds = []
        for odds_item in odds_generator:
            for trial in range(self.max_trials):
                try:
                    game_dict = self.extract_match_odds(odds_item, False)

                    # extract_match_odds would only return None if it's parsed through all the games within the set self._max_game_days_ahead
                    # therefore, we are done with this league
                    if game_dict is None:
                        return games_odds

                    if game_dict == False:
                        continue

                    game_dict['league_id'] = league_id
                    game_dict['home_team_id'] = self._get_team_id(game_dict['home_team'], league_id)
                    game_dict['away_team_id'] = self._get_team_id(game_dict['away_team'], league_id)
                    game_dict.pop('home_team', None); game_dict.pop('away_team', None)

                    games_odds.append(game_dict)
                    break
                except:
                    self._driver.back()
                    time.sleep(self.trial_wait_time)
                    continue
            
                # if league odds were extracted successfully - the loop should break before reaching this exception
                error_msg = f'Odds for league with id {league_id} failed to be extracted.'
                if self.logger is not None:
                    self.logger.log_message(error_msg, Logging.ERROR)
                raise OddsExtractionFailedError

        return games_odds

    def __load_headers(self):
        bookie_headers = pd.read_csv(BOOKIE_HEADERS_CSV_PATH)
        self._bookie_headers = bookie_headers[bookie_headers.BOOKIE_NAME == self._bookie_name]\
                                                        .drop('BOOKIE_NAME', axis=1)\
                                                        .to_dict(orient='records')[0]



