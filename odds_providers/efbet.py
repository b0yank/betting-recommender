#import numpy as np
#import pandas as pd
import time
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from constants import ACCEPTED_GOALS, DB_PATH
from utils.bookie_header_titles import *
from .odds_provider import OddsProvider

class EfbetOddsProvider(OddsProvider):
    """ Gathers coefficients data from efbet.com
    """

    _HOME_URL = 'https://www.efbet.com/'
    
    def __init__(self, football_database, logger=None):
        super().__init__(football_database, logger)

        self.__country_codes = {
            'england': '282247.1',
            'italy': '282250.1',
            'spain': '282249.1',
            'germany': '282248.1',
            'france': '282251.1',
            'netherlands': '282254.1',
            'portugal': '282255.1',
            'turkey': '282253.1',
            'russia': '282252.1',
            'greece': '394741.1',
            'scotland': '283681.1'
        }

        valid_groups = [self._bookie_headers[FULL_TIME], self._bookie_headers[HALF_TIME], self._bookie_headers[DOUBLE_CHANCE], self._bookie_headers[HT_DOUBLE_CHANCE],
                        self._bookie_headers[HT_FT], self._bookie_headers[BTTS], self._bookie_headers[RESULT_BTTS], self._bookie_headers[FIRST_HALF_BTTS],
                        self._bookie_headers[SECOND_HALF_BTTS]] +\
                       [g.format(ag) for g in [self._bookie_headers[GOALS_OU], self._bookie_headers[RESULT_TG], self._bookie_headers[TG_BTTS]] for ag in ACCEPTED_GOALS]
        self.__groups_list_xpath = ' or '.join([f'contains(., \'{grp}\')' for grp in valid_groups])

        self.__find_odds = lambda x: x.find('span', {'class': 'prc'}).text
        self.__find_subgroups = lambda x: x.findAll('div', {'class': 'sel-col'})

    def _get_odds_link_items(self):
        def get_date(date_str):
            now = datetime.now()
            month_now, year_now = now.month, now.year
            day_then, month_then = date_str.split()
            month_then = datetime.strptime(month_then[:3], '%b').month
            year = year_now if month_then >= month_now else year_now + 1
            return datetime(year, month_then, int(day_then))

        #self._driver.wait_until_visibility(By.CLASS_NAME, stats_class_name)
        self._driver.wait_until_visibility(By.XPATH, './/a[contains(@class, \'mb\')]')

        bs = BeautifulSoup(self._driver.page_source, 'html.parser')
        self.__game_dates = []
        for d in  bs.findAll('td', {'class': 'date'}):
            date = get_date(d.text)
            if (date - datetime.now()).days >= self._max_game_days_ahead:
                break

            self.__game_dates.append(date)

        return range(len(self.__game_dates))
        
    def extract_match_odds(self, odds_item, close_driver = True):
        stats_class_name = 'mb'
        self._driver.wait_until_visibility(By.CLASS_NAME, stats_class_name)

        stats_list = self._driver.find_elements_by_xpath(f'.//a[contains(@class, \'{stats_class_name}\')]')
        stats_list[odds_item].click()

        self._driver.wait_until_visibility(By.XPATH, './/a[text()=\'All\']')
        time.sleep(3)
        self._driver.refresh()
        time.sleep(3)

        self._driver.find_element_by_xpath('.//a[text()=\'All\']').click()

        groups_string = f'//h2[contains(@behavior.id, \'ToggleContainer\') and ({self.__groups_list_xpath})]'
        list_openers = self._driver.find_elements_by_xpath(groups_string)
        for opener in list_openers:
            opener.click()
            time.sleep(1)
        
        match_html = self._driver.page_source
        group_wrappers = self.__get_html_market_groups(match_html)

        # main odds
        game_dict = {}

        odds_1X2_all = self.__find_subgroups(group_wrappers[self._bookie_headers[FULL_TIME]])
        game_dict['home_team'] = odds_1X2_all[0].find('span').text
        game_dict['away_team'] = odds_1X2_all[2].find('span').text
        game_dict['date'] = self.__game_dates[odds_item]
        game_dict['1'] = float(self.__find_odds(odds_1X2_all[0]))
        game_dict['X'] = float(self.__find_odds(odds_1X2_all[1]))
        game_dict['2'] = float(self.__find_odds(odds_1X2_all[2]))

        if self._bookie_headers[DOUBLE_CHANCE] in group_wrappers:
            odds_dc_all = self.__find_subgroups(group_wrappers[self._bookie_headers[DOUBLE_CHANCE]])
            game_dict['1/X'] = float(self.__find_odds(odds_dc_all[0]))
            game_dict['1/2'] = float(self.__find_odds(odds_dc_all[1]))
            game_dict['X/2'] = float(self.__find_odds(odds_dc_all[2]))
        
        if self._bookie_headers[HT_FT] in group_wrappers:
            odds_htft_all = self.__find_subgroups(group_wrappers[self._bookie_headers[HT_FT]])
            game_dict['1-1'] = float(self.__find_odds(odds_htft_all[0]))
            game_dict['1-X'] = float(self.__find_odds(odds_htft_all[1]))
            game_dict['1-2'] = float(self.__find_odds(odds_htft_all[2]))
            game_dict['X-1'] = float(self.__find_odds(odds_htft_all[3]))
            game_dict['X-X'] = float(self.__find_odds(odds_htft_all[4]))
            game_dict['X-2'] = float(self.__find_odds(odds_htft_all[5]))
            game_dict['2-1'] = float(self.__find_odds(odds_htft_all[6]))
            game_dict['2-X'] = float(self.__find_odds(odds_htft_all[7]))
            game_dict['2-2'] = float(self.__find_odds(odds_htft_all[8]))

        if self._bookie_headers[BTTS] in group_wrappers:
            odds_btts_all = self.__find_subgroups(group_wrappers[self._bookie_headers[BTTS]])
            game_dict['btts_yes'] = float(self.__find_odds(odds_btts_all[0]))
            game_dict['btts_no'] = float(self.__find_odds(odds_btts_all[1]))

        # goals odds
        for ng in ACCEPTED_GOALS:
            header = self._bookie_headers[GOALS_OU].format(ng)
            if header not in group_wrappers:
                header = self._bookie_headers[ALTERNATIVE_TG].format(ng)

            if header in group_wrappers:
                goals_ou = self.__find_subgroups(group_wrappers[header])

                label_one = goals_ou[0].find('label').find('span').text.split()[0].lower()
                game_dict[f'{label_one}_{ng}'] = float(self.__find_odds(goals_ou[0]))
                label_two = goals_ou[1].find('label').find('span').text.split()[0].lower()
                game_dict[f'{label_two}_{ng}'] = float(self.__find_odds(goals_ou[1]))

            header = self._bookie_headers[RESULT_TG].format(ng) 
            if header in group_wrappers:
                for bet in self.__find_subgroups(group_wrappers[header]):
                    team, ou = bet.find('span').text.lower().split(' and ')
                    if team == game_dict['home_team'].lower():
                        team = 'home'
                    elif team == game_dict['away_team'].lower():
                        team = 'away'
                    else: continue;
                    ou = ou.split()[0]

                    game_dict[f'{team}_&{ou}_{ng}'] = float(self.__find_odds(bet))

            header = self._bookie_headers[TG_BTTS].format(ng)
            if header in group_wrappers:
                for bet in self.__find_subgroups(group_wrappers[header]):
                    yn, ou = map(str.lower, bet.find('span').text.split(' / ')[:2])
                    ou = ou.split()[0]

                    game_dict[f'{ou}_{ng}_btts_{yn}'] = float(self.__find_odds(bet))

        # half odds
        if self._bookie_headers[HALF_TIME] in group_wrappers:
            odds_ht = self.__find_subgroups(group_wrappers[self._bookie_headers[HALF_TIME]])
            game_dict['ht_1'] = float(self.__find_odds(odds_ht[0]))
            game_dict['ht_X'] = float(self.__find_odds(odds_ht[1]))
            game_dict['ht_2'] = float(self.__find_odds(odds_ht[2]))

        if self._bookie_headers[HT_DOUBLE_CHANCE] in group_wrappers:
            ht_dc_all = self.__find_subgroups(group_wrappers[self._bookie_headers[HT_DOUBLE_CHANCE]])
            game_dict['ht_1/X'] = float(self.__find_odds(ht_dc_all[0]))
            game_dict['ht_1/2'] = float(self.__find_odds(ht_dc_all[1]))
            game_dict['ht_X/2'] = float(self.__find_odds(ht_dc_all[2]))

        if self._bookie_headers[FIRST_HALF_BTTS] in group_wrappers:
            sh_btts_all = self.__find_subgroups(group_wrappers[self._bookie_headers[FIRST_HALF_BTTS]])
            game_dict['first_half_btts_yes'] = float(self.__find_odds(sh_btts_all[0]))
            game_dict['first_half_btts_no'] = float(self.__find_odds(sh_btts_all[1]))

        if self._bookie_headers[SECOND_HALF_BTTS] in group_wrappers:
            sh_btts_all = self.__find_subgroups(group_wrappers[self._bookie_headers[SECOND_HALF_BTTS]])
            game_dict['second_half_btts_yes'] = float(self.__find_odds(sh_btts_all[0]))
            game_dict['second_half_btts_no'] = float(self.__find_odds(sh_btts_all[1]))
            
        self._driver.back()

        return game_dict

    def _get_league_url(self, league_id):
        # needs a little timeout, otherwise a nasty bug appears occasionally, mixing up the different leagues
        time.sleep(30)

        if league_id not in self._league_codes or self._league_codes[league_id] is None:
            return None

        league_code = self._league_codes[league_id]
        country_code = self.__country_codes[self.db.leagues.loc[league_id, 'country']]
        league_url = self.LEAGUE_URL.format(country_code, league_code)

        return league_url

    def __get_html_market_groups(self, html):
        mhtml = self._driver.page_source
        bs = BeautifulSoup(mhtml, 'html.parser')
        group_wrappers = {}
        for group in bs.findAll('div', {'class': 'selections-container'}):
            group_wrappers[group.find('a').attrs['behavior.selectionclick.marketname']] = group

        return group_wrappers
