#import numpy as np
#import pandas as pd
import time
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from constants import ACCEPTED_GOALS, DB_PATH
from utils.bookie_header_titles import *
from .odds_provider import OddsProvider

class CoralOddsProvider(OddsProvider):
    """ Gathers coefficients data from coral.co.uk
    """

    _HOME_URL = 'https://sports.coral.co.uk/'
    
    def __init__(self, football_database, logger=None):
        super().__init__(football_database, logger)

        self.__valid_groups = [self._bookie_headers[HALF_TIME], self._bookie_headers[DOUBLE_CHANCE], self._bookie_headers[HT_FT], self._bookie_headers[BTTS],
                               self._bookie_headers[GOALS_OU], self._bookie_headers[RESULT_BTTS], self._bookie_headers[FIRST_HALF_BTTS], self._bookie_headers[SECOND_HALF_BTTS]] +\
                              [self._bookie_headers[TG_BTTS].format(ag) for ag in ACCEPTED_GOALS]

        self.__valid_groups += [self.__result_tg_format(ag) for ag in ACCEPTED_GOALS]
        self.__groups_list_xpath = ' or '.join([f'contains(., \'{grp}\')' for grp in self.__valid_groups])
        self.__valid_groups.append(self._bookie_headers[FULL_TIME])
        
        self.__find_odds = lambda x: x.find('span', {'data-crlat': 'oddsPrice'}).text
        self.__find_odds_all = lambda x: x.findAll('span', {'data-crlat': 'oddsPrice'})
        self.__find_subgroups = lambda x: x.findAll('div', {'data-crlat': 'oddsCard'})
        self.__find_outcomes = lambda x: x.findAll('div', {'data-crlat': 'market.outcomes'})
        self.__find_name = lambda x: x.find('span', {'data-crlat': 'outcomeEntity.name'}).text

    def _get_odds_link_items(self):
        time.sleep(5)

        bs = BeautifulSoup(self._driver.page_source, 'html.parser')
        odds_links = [self._HOME_URL + link.attrs['href'] + '/all-markets' for link in bs.findAll('a', {'class': 'odds-more-link'})]

        return odds_links

    def extract_match_odds(self, odds_item, close_driver = False):
        self._driver.get(odds_item)

        self._driver.wait_until_visibility(By.XPATH, './/span[contains(@data-crlat, \'eventEntity.filteredTime\')]')

        time.sleep(2)
        for idx in range(3):
            try:
                date_str = BeautifulSoup(self._driver.page_source, 'html.parser').find('span', {'data-crlat': 'eventEntity.filteredTime'}).text.split()[1].replace('.', '')
                break
            except:
                time.sleep(6)

        date = datetime.strptime(date_str, '%d-%b-%y')

        if (date - datetime.now()).days >= self._max_game_days_ahead:
            return None

        time.sleep(1)

        self._driver.wait_until_visibility(By.XPATH, f'//accordion[contains(., \'{self._bookie_headers[FULL_TIME]}\')]')

        groups_xpath = f'//section[(contains(@class, \'accordion\') and not(contains(@class, \'is-expanded\'))) and ({self.__groups_list_xpath})]'
        list_openers = self._driver.find_elements_by_xpath(groups_xpath)
        for opener in list_openers:
            opener.find_element_by_xpath('.//header').click()
            time.sleep(2)

        match_html = self._driver.page_source
        group_wrappers = self.__get_html_market_groups(match_html)

        # main odds
        game_dict = {}

        odds_1X2_all = self.__find_outcomes(group_wrappers[self._bookie_headers[FULL_TIME]])
        game_dict['home_team'] = self.__find_name(odds_1X2_all[0])
        game_dict['away_team'] = self.__find_name(odds_1X2_all[2])
        game_dict['date'] = date
        game_dict['1'] = self.__frac_to_decimal(self.__find_odds(odds_1X2_all[0]))
        game_dict['X'] = self.__frac_to_decimal(self.__find_odds(odds_1X2_all[1]))
        game_dict['2'] = self.__frac_to_decimal(self.__find_odds(odds_1X2_all[2]))

        if self._bookie_headers[DOUBLE_CHANCE] in group_wrappers:
            odds_dc_all = self.__find_subgroups(group_wrappers[self._bookie_headers[DOUBLE_CHANCE]])
            game_dict['1/X'] = self.__frac_to_decimal(self.__find_odds(odds_dc_all[0]))
            game_dict['X/2'] = self.__frac_to_decimal(self.__find_odds(odds_dc_all[1]))
            game_dict['1/2'] = self.__frac_to_decimal(self.__find_odds(odds_dc_all[2]))
        
        if self._bookie_headers[HT_FT] in group_wrappers:
            odds_htft_all = self.__find_subgroups(group_wrappers[self._bookie_headers[HT_FT]])
            game_dict['1-1'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[0]))
            game_dict['1-X'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[1]))
            game_dict['1-2'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[2]))
            game_dict['X-1'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[3]))
            game_dict['X-X'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[4]))
            game_dict['X-2'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[5]))
            game_dict['2-1'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[6]))
            game_dict['2-X'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[7]))
            game_dict['2-2'] = self.__frac_to_decimal(self.__find_odds(odds_htft_all[8]))

        if self._bookie_headers[BTTS] in group_wrappers:
            odds_btts_all = self.__find_outcomes(group_wrappers[self._bookie_headers[BTTS]])
            game_dict['btts_yes'] = self.__frac_to_decimal(self.__find_odds(odds_btts_all[0]))
            game_dict['btts_no'] = self.__frac_to_decimal(self.__find_odds(odds_btts_all[1]))

        # goals odds
        if self._bookie_headers[GOALS_OU] in group_wrappers:
            for row in self.__find_subgroups(group_wrappers[self._bookie_headers[GOALS_OU]]):
                ng = float(row.find('strong', {'class': 'odds-name'}).text)
                if ng not in ACCEPTED_GOALS:
                    continue

                over, under = [self.__frac_to_decimal(frac.text) for frac in self.__find_odds_all(row)]
                game_dict[f'over_{ng}'] = over
                game_dict[f'under_{ng}'] = under

        def get_team(team):
            if team == game_dict['home_team']:
                return 'home';
            elif team == game_dict['away_team']:
                return 'away';
            else:
                return None;

        for ng in ACCEPTED_GOALS:
            header = self.__result_tg_format(ng)
            if header in group_wrappers:
                ng_odds = self.__find_subgroups(group_wrappers[header])
                for odds in ng_odds:
                    odds_name = odds.find('span', {'data-crlat': 'outcomeEntity.name'})
                    if odds_name is None:
                        team_name = odds.find('strong', {'class': 'odds-name'})
                        if team_name is None:
                            team_name = odds.find('div', {'data-crlat': 'oddsNames'})
                        team = get_team(team_name.text)
                        if team == None:
                            continue

                        over, under = [self.__frac_to_decimal(ou.text) for ou in self.__find_odds_all(odds)]
                        game_dict[f'{team}_&over_{ng}'] = over
                        game_dict[f'{team}_&under_{ng}'] = under
                    else:
                        team, rest = odds_name.text.split(' and ')
                        ou = rest.split()[0].lower()

                        team = get_team(team)
                        if team == None:
                            continue

                        game_dict[f'{team}_&{ou}_{ng}'] = self.__frac_to_decimal(self.__find_odds(odds))

            header = self._bookie_headers[TG_BTTS].format(ng)
            if header in group_wrappers:
                for ng_odds in self.__find_subgroups(group_wrappers[header]):
                    yn, _, ou, _, _ = map(str.lower, ng_odds.find('span', {'data-crlat': 'outcomeEntity.name'}).text.split())
                    game_dict[f'{ou}_{ng}_btts_{yn}'] = self.__frac_to_decimal(self.__find_odds(ng_odds))

        # half odds
        if self._bookie_headers[HALF_TIME] in group_wrappers:
            odds_ht = self.__find_subgroups(group_wrappers[self._bookie_headers[HALF_TIME]])
            game_dict['ht_1'] = self.__frac_to_decimal(self.__find_odds(odds_ht[0]))
            game_dict['ht_X'] = self.__frac_to_decimal(self.__find_odds(odds_ht[1]))
            game_dict['ht_2'] = self.__frac_to_decimal(self.__find_odds(odds_ht[2]))

        if self._bookie_headers[HT_DOUBLE_CHANCE] in group_wrappers:
            ht_dc_all = self.__find_subgroups(group_wrappers[self._bookie_headers[HT_DOUBLE_CHANCE]])
            game_dict['ht_1/X'] = self.__frac_to_decimal(self.__find_odds(ht_dc_all[0]))
            game_dict['ht_X/2'] = self.__frac_to_decimal(self.__find_odds(ht_dc_all[1]))
            game_dict['ht_1/2'] = self.__frac_to_decimal(self.__find_odds(ht_dc_all[2]))

        if self._bookie_headers[FIRST_HALF_BTTS] in group_wrappers:
            half_btts_all = self.__find_subgroups(group_wrappers[self._bookie_headers[FIRST_HALF_BTTS]])
            game_dict['first_half_btts_yes'] = self.__frac_to_decimal(self.__find_odds(half_btts_all[0]))
            game_dict['first_half_btts_no'] = self.__frac_to_decimal(self.__find_odds(half_btts_all[1]))

        if self._bookie_headers[SECOND_HALF_BTTS] in group_wrappers:
            half_btts_all = self.__find_subgroups(group_wrappers[self._bookie_headers[SECOND_HALF_BTTS]])
            game_dict['second_half_btts_yes'] = self.__frac_to_decimal(self.__find_odds(half_btts_all[0]))
            game_dict['second_half_btts_no'] = self.__frac_to_decimal(self.__find_odds(half_btts_all[1]))
            
        return game_dict

    def _get_league_url(self, league_id):
        return self.LEAGUE_URL.format(self.db.leagues.loc[league_id, 'country'], self._league_codes[league_id])

    def __frac_to_decimal(self, fraction_str):
        numerator, denominator = [int(n) for n in fraction_str.split('/')]
        return 1. + round(numerator/denominator, 2)

    def __result_tg_format(self, ng):
        return self._bookie_headers[RESULT_TG].format('&', ng, ' market') if ng in [2.5, 3.5] else self._bookie_headers[RESULT_TG].format('and', ng, '')
        
    def __get_html_market_groups(self, html):
        bs = BeautifulSoup(html, 'html.parser')
        group_wrappers = {}
        for group in bs.findAll('section', {'class': 'is-expanded'}):
            try:
                header = group.find('h2', {'class': 'accordion-title'}).text
            except:
                header = group.find('span', {'class': 'left-title-text'}).text
            if header in self.__valid_groups:
                if header == self._bookie_headers[DOUBLE_CHANCE]:
                    # save full-time double chance content first, then get data for half-time double chance
                    content = group.find('div', {'class': 'container-inner-content'})
                    group_wrappers[header] = content

                    dc_element = self._driver.find_element_by_xpath(f'//accordion[contains(., \'{self._bookie_headers[DOUBLE_CHANCE]}\')]')
                    dc_element.find_element_by_xpath('.//a[contains(@data-crlat, \'buttonSwitch\') and text()=\'1st Half\']').click() ########################################
                    #[el.click() for el in self._driver.find_elements_by_xpath('//a[contains(@data-crlat, \'buttonSwitch\') and text()=\'1st Half\']')]
                    header = self._bookie_headers[HT_DOUBLE_CHANCE]
                    content = BeautifulSoup(dc_element.get_attribute('outerHTML'), 'html.parser').find('div', {'class': 'container-inner-content'})
                elif header == self._bookie_headers[SECOND_HALF_BTTS]:
                    btts_element = self._driver.find_element_by_xpath(f'//accordion[contains(., \'{self._bookie_headers[SECOND_HALF_BTTS]}\')]')
                    btts_element.find_element_by_xpath('.//a[contains(@data-crlat, \'buttonSwitch\') and text()=\'2nd Half\']').click()
                    content = BeautifulSoup(btts_element.get_attribute('outerHTML'), 'html.parser').find('div', {'class': 'container-inner-content'})
                else:
                    content = group.find('div', {'class': 'container-inner-content'})

                # sometimes an odds group exists but has no odds in it; ignore the group if that is the case
                try:
                    odds = self.__find_odds(content)

                    if odds is None:
                        continue

                except:
                    continue

                group_wrappers[header] = content

        return group_wrappers
