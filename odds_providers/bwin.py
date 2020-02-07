#import numpy as np
#import pandas as pd
import time
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from constants import ACCEPTED_GOALS, DB_PATH
from utils.bookie_header_titles import *
from .odds_provider import OddsProvider

class BwinOddsProvider(OddsProvider):
    """ Gathers coefficients data from bwin.com
    """

    _HOME_URL = 'https://sports.bwin.com'
    
    def __init__(self, football_database, logger=None):
        super().__init__(football_database, logger)

        self.__find_odds = lambda x: x.find('div', {'class': 'mb-option-button__option-odds'}).text
        self.__find_name = lambda x: x.find('div', {'class': 'mb-option-button__option-name'}).text

    def provide_odds(self, league_ids, start_date, end_date):
        games = self.db.games[(self.db.games.date >= start_date)&\
                              (self.db.games.date <= end_date)&\
                              (self.db.games.league_id.isin(league_ids))]

        return self.odds.merge(games[['home_team_id', 'away_team_id', 'season']],
                               on=['home_team_id', 'away_team_id', 'season'],
                               how='inner')

    def extract_match_odds(self, odds_item, close_driver = False):
        self._driver.get(odds_item)

        self._driver.wait_until_visibility(By.XPATH, f'//div[contains(@class, \'nav-link \') and contains(@title, \'All\')]')

        #time.sleep(3)

        all_element = self._driver.find_element_by_xpath('//div[contains(@class, \'nav-link \') and contains(@title, \'All\')]').click()
        self._driver.wait_until_visibility(By.XPATH, f'//div[contains(@class, \'nav-link active\') and contains(@title, \'All\')]')

        match_html = self._driver.page_source
        group_wrappers = self.__get_html_market_groups(match_html)

        # main odds
        game_dict = {}
        date = datetime.strptime(BeautifulSoup(match_html, 'html.parser').find('span', {'class': 'event-block__start-date'}).text.split(',')[0], '%m/%d/%Y')
        if (date - datetime.now()).days >= self._max_game_days_ahead:
            return None

        game_dict['date'] = date
        odds_1X2_all = group_wrappers[self._bookie_headers[FULL_TIME]].findAll('td')   
        
        game_dict['home_team'] = self.__find_name(odds_1X2_all[0])
        game_dict['away_team'] = self.__find_name(odds_1X2_all[2])
        game_dict['1'] = float(self.__find_odds(odds_1X2_all[0]))
        game_dict['X'] = float(self.__find_odds(odds_1X2_all[1]))
        game_dict['2'] = float(self.__find_odds(odds_1X2_all[2]))

        if self._bookie_headers[DOUBLE_CHANCE] in group_wrappers:
            odds_dc_all = group_wrappers[self._bookie_headers[DOUBLE_CHANCE]].findAll('td')
            game_dict['1/X'] = float(self.__find_odds(odds_dc_all[0]))
            game_dict['X/2'] = float(self.__find_odds(odds_dc_all[1]))
            game_dict['1/2'] = float(self.__find_odds(odds_dc_all[2]))

        if self._bookie_headers[HT_FT] in group_wrappers:
            odds_htft_all = group_wrappers[self._bookie_headers[HT_FT]].findAll('td')
            game_dict['1-1'] = float(self.__find_odds(odds_htft_all[0]))
            game_dict['X-1'] = float(self.__find_odds(odds_htft_all[1]))
            game_dict['2-1'] = float(self.__find_odds(odds_htft_all[2]))
            game_dict['1-X'] = float(self.__find_odds(odds_htft_all[3]))
            game_dict['X-X'] = float(self.__find_odds(odds_htft_all[4]))
            game_dict['2-X'] = float(self.__find_odds(odds_htft_all[5]))
            game_dict['1-2'] = float(self.__find_odds(odds_htft_all[6]))
            game_dict['X-2'] = float(self.__find_odds(odds_htft_all[7]))
            game_dict['2-2'] = float(self.__find_odds(odds_htft_all[8]))

        if self._bookie_headers[BTTS] in group_wrappers:
            odds_btts_all = group_wrappers[self._bookie_headers[BTTS]].findAll('td')
            game_dict['btts_yes'] = float(self.__find_odds(odds_btts_all[0]))
            game_dict['btts_no'] = float(self.__find_odds(odds_btts_all[1]))

        # goals odds
        for row in group_wrappers[self._bookie_headers[GOALS_OU]].findAll('tr'):
            ngoals = float(self.__find_name(row.find('td')).split()[1].replace(',', '.'))
            if ngoals not in ACCEPTED_GOALS: continue;
            options = row.findAll('td')
            game_dict[f'over_{ngoals}'] = float(self.__find_odds(options[0]))
            game_dict[f'under_{ngoals}'] = float(self.__find_odds(options[1]))

        for ng in ACCEPTED_GOALS:
            header = self._bookie_headers[RESULT_TG].format(ng) 
            if header in group_wrappers:
                for bet in group_wrappers[header].findAll('td'):
                    bet_text = self.__find_name(bet)
                    if bet_text == 'Draw': continue;

                    team, ou = bet_text.split(' and ')
                    team = ' '.join(team.split()[:2])
                    if team == 'Team 1':
                        team = 'home'
                    elif team == 'Team 2':
                        team = 'away'
                    else: 
                        continue
                    ou = ou.split()[0]

                    odds = float(self.__find_odds(bet))
                    game_dict[f'{team}_&{ou}_{ng}'] = odds

        # half odds
        if self._bookie_headers[HALF_TIME] in group_wrappers:
            ht_bets = group_wrappers[self._bookie_headers[HALF_TIME]].findAll('td')
            game_dict['ht_1'] = float(self.__find_odds(ht_bets[0]))
            game_dict['ht_X'] = float(self.__find_odds(ht_bets[1]))
            game_dict['ht_2'] = float(self.__find_odds(ht_bets[2]))

        if self._bookie_headers[HT_DOUBLE_CHANCE] in group_wrappers:
            ht_bets = group_wrappers[self._bookie_headers[HT_DOUBLE_CHANCE]].findAll('td')
            game_dict['ht_1/X'] = float(self.__find_odds(ht_bets[0]))
            game_dict['ht_X/2'] = float(self.__find_odds(ht_bets[1]))
            game_dict['ht_1/2'] = float(self.__find_odds(ht_bets[2]))

        if self._bookie_headers[FIRST_HALF_BTTS] in group_wrappers:
            bets = group_wrappers[self._bookie_headers[FIRST_HALF_BTTS]].findAll('td')
            game_dict['first_half_btts_yes'] = float(self.__find_odds(bets[0]))
            game_dict['first_half_btts_no'] = float(self.__find_odds(bets[1]))

        if close_driver:
            self._close_driver()
            
        return game_dict

    def _get_odds_link_items(self):
        bs = BeautifulSoup(self._driver.page_source, 'html.parser')
        odds_links = [self._HOME_URL + link.attrs['href'] for link in bs.findAll('a', {'class': 'mb-event-details-buttons__button-link'})\
                                                                if link.attrs['title'] != 'Statistics']
        return odds_links

    def _extract_odds_from_item(self, odds_item):
        self._driver.get(odds_item)

        game_dict = self.extract_match_odds(close_driver=False)
        if game_dict is None:
            return None

        game_dict['league_id'] = league_id
        game_dict['home_team_id'] = self._get_team_id(game_dict['home_team'], league_id)
        game_dict['away_team_id'] = self._get_team_id(game_dict['away_team'], league_id)
        game_dict.pop('home_team', None); game_dict.pop('away_team', None)
            
        time.sleep(2)
        return game_dict

        
    def _extract_bookie_league_odds(self, league_id):
        stat_class_name = 'mb-event-details-buttons__button-link'

        bs = BeautifulSoup(self._driver.page_source, 'html.parser')
        odds_links = [self._HOME_URL + link.attrs['href'] for link in bs.findAll('a', {'class': stat_class_name}) if link.attrs['title'] != 'Statistics']

        games_odds = []
        for odds_link in odds_links:
            self._driver.get(odds_link)

            game_dict = self.extract_match_odds(close_driver=False)
            if game_dict is None:
                break

            game_dict['league_id'] = league_id
            game_dict['home_team_id'] = self._get_team_id(game_dict['home_team'], league_id)
            game_dict['away_team_id'] = self._get_team_id(game_dict['away_team'], league_id)
            game_dict.pop('home_team', None); game_dict.pop('away_team', None)
            
            games_odds.append(game_dict)
            time.sleep(2)

        return games_odds

    def __get_html_market_groups(self, html):
        bs = BeautifulSoup(html, 'html.parser')
        group_wrappers = {}
        for group in bs.findAll('div', {'class': 'marketboard-event-with-header'}):
            title = group.find('span', {'class': 'marketboard-event-with-header__market-name'})
            if title is None:
                continue
            title = title.text

            group_wrappers[title] = group.find('div', {'class': 'marketboard-event-with-header__markets-container'})

        return group_wrappers

