import numpy as np
#import pandas as pd
import time
from datetime import datetime
from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

from constants import ACCEPTED_GOALS, DB_PATH
from utils.bookie_header_titles import *
from .odds_provider import OddsProvider

class Bet365OddsProvider(OddsProvider):
    """ Gathers coefficients data from bet365.com
    """
    
    def __init__(self, football_database, logger=None):
        super().__init__(football_database, logger)

        self.__odds_group_class = 'gl-MarketGroupButton_Text'

        self.__find_odds = lambda x: x.find('span', {'class': 'gl-Participant_Odds'}).text
        self.__find_name = lambda x: x.find('span', {'class': 'gl-Participant_Name'}).text
        self.__find_odds_centered = lambda x: x.find('span', {'class': 'gl-ParticipantCentered_Odds'}).text
        self.__find_odds_borderless = lambda x: x.find('span', {'class': 'gl-ParticipantBorderless_Odds'}).text
        self.__find_odds_only = lambda x: x.findAll('span', {'class': 'gl-ParticipantOddsOnly_Odds'})
        self.__find_odds_subgroups = lambda x: x.findAll('div', {'class': 'gl-Participant_General'})

    def _get_odds_link_items(self):
        outer_stats_class_name = 'sl-MarketCouponFixtureLink'
        stats_class_name = 'sl-CouponFixtureLinkParticipant_Name'
        self._driver.wait_until_visibility(By.CLASS_NAME, stats_class_name)

        all_stats = self._driver.find_element_by_class_name(outer_stats_class_name).find_elements_by_class_name(stats_class_name)
        return range(len(all_stats))

    def extract_match_odds(self, odds_item, close_driver = True):
        stats_class_name = 'sl-CouponFixtureLinkParticipant_Name'
        outer_stats_class_name = 'sl-MarketCouponFixtureLink'
        self._driver.wait_until_visibility(By.CLASS_NAME, stats_class_name)
        time.sleep(3)

        stats_list = self._driver.find_element_by_class_name(outer_stats_class_name).find_elements_by_class_name(stats_class_name)
        stats_list[odds_item].click()

        time.sleep(3)

        try:
             self._driver.wait_until_visibility(By.XPATH, f'.//div[contains(@class, \'{self.__odds_group_class}\') and text()=\'{self._bookie_headers[FULL_TIME]}\']')
        except TimeoutException as te:
            if close_driver:
                self._close_driver()
            else:
                self._driver.back();
                
            return False

        # several try-catch blocks are used with a pass in the catch as we want the code to wait for the page to load fully
        # but we still want the rest of the odds for this game to be extracted even if the specific bet type is not available
        try:
            self._driver.wait_until_visibility(By.XPATH, f'.//div[contains(@class, \'{self.__odds_group_class}\') and text()=\'{self._bookie_headers[DOUBLE_CHANCE]}\']')
        except TimeoutException:
            pass
            
        game_dict = {}
        
        game_dict = self.__extract_main_odds(self._driver.page_source, game_dict=game_dict)
        time.sleep(np.random.randint(2, 5, (1,))[0])

        if game_dict is None:
            return game_dict

        self._driver.get(self._driver.current_url.replace('G0/H0/I1', 'H0/I6/R1'))

        try:
            self._driver.wait_until_visibility(By.XPATH, f'.//div[contains(@class, \'gl-MarketGroupButton_Text\') and text()=\'{self._bookie_headers[ALTERNATIVE_TG]}\']')
        except TimeoutException:
            pass

        game_dict = self.__extract_goals_odds(self._driver.page_source, game_dict)
        time.sleep(np.random.randint(2, 5, (1,))[0])

        self._driver.get(self._driver.current_url.replace('I6', 'I7'))

        try:
            self._driver.wait_until_visibility(By.XPATH, f'.//div[contains(@class, \'gl-MarketGroupButton_Text\') and text()=\'{self._bookie_headers[HALF_TIME]}\']')
        except TimeoutException:
            pass
            
        game_dict = self.__extract_half_odds(self._driver.page_source, game_dict)
        
        if close_driver:
            self._close_driver()
        else:
            self._driver.back(); time.sleep(1);
            self._driver.back(); time.sleep(1);
            self._driver.back(); time.sleep(np.random.randint(1, 4, (1,))[0])
            
        return game_dict

    def _open_league_url(self, league_id, close_driver = True):
        super()._open_league_url(league_id, close_driver)

        language_btn = self._driver.find_element_by_xpath('.//div[contains(@class, \'hm-LanguageDropDownSelections\')]')

        current_language = language_btn.find_element_by_xpath('.//span[contains(@class, \'hm-DropDownSelections_Highlight\')]').get_attribute('innerHTML')
        if current_language != 'English':
            language_btn.click()
            language_btn.find_element_by_xpath('.//a[contains(@class, \'hm-DropDownSelections_Item\') and text()=\'English\']').click()

    def _get_league_url(self, league_id):
        time.sleep(10)
        return super()._get_league_url(league_id)
        
    def __extract_main_odds(self, main_match_html, game_dict = {}):
        group_wrappers = self.__get_html_market_groups(main_match_html)
        game_datetime = BeautifulSoup(main_match_html, 'html.parser')\
                            .find('div', {'class': 'cm-MarketGroupExtraData_TimeStamp'})\
                            .text.split()[:-1]
        now = datetime.now()
        month_now, year_now = now.month, now.year
        month_then = datetime.strptime(game_datetime[1], '%b').month
        year = year_now if month_then >= month_now else year_now + 1
        game_dict['date'] = datetime.strptime(' '.join(game_datetime + [str(year)]), '%d %b %Y')
        if (game_dict['date'] - datetime.now()).days >= self._max_game_days_ahead:
            self._driver.back()
            return None
        
        odds_1X2_all = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[FULL_TIME]])    
        game_dict['home_team'] = self.__find_name(odds_1X2_all[0])
        game_dict['away_team'] = self.__find_name(odds_1X2_all[2])
        game_dict['1'] = float(self.__find_odds(odds_1X2_all[0]))
        game_dict['X'] = float(self.__find_odds(odds_1X2_all[1]))
        game_dict['2'] = float(self.__find_odds(odds_1X2_all[2]))

        if self._bookie_headers[DOUBLE_CHANCE] in group_wrappers:
            odds_dc_all = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[DOUBLE_CHANCE]])
            game_dict['1/X'] = float(self.__find_odds(odds_dc_all[0]))
            game_dict['X/2'] = float(self.__find_odds(odds_dc_all[1]))
            game_dict['1/2'] = float(self.__find_odds(odds_dc_all[2]))

        if self._bookie_headers[HT_FT] in group_wrappers:
            odds_htft_all = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[HT_FT]])
            game_dict['1-1'] = float(self.__find_odds_borderless(odds_htft_all[0]))
            game_dict['1-X'] = float(self.__find_odds_borderless(odds_htft_all[1]))
            game_dict['1-2'] = float(self.__find_odds_borderless(odds_htft_all[2]))
            game_dict['X-1'] = float(self.__find_odds_borderless(odds_htft_all[3]))
            game_dict['X-X'] = float(self.__find_odds_borderless(odds_htft_all[4]))
            game_dict['X-2'] = float(self.__find_odds_borderless(odds_htft_all[5]))
            game_dict['2-1'] = float(self.__find_odds_borderless(odds_htft_all[6]))
            game_dict['2-X'] = float(self.__find_odds_borderless(odds_htft_all[7]))
            game_dict['2-2'] = float(self.__find_odds_borderless(odds_htft_all[8]))

        if self._bookie_headers[BTTS] in group_wrappers:
            odds_btts_all = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[BTTS]])
            game_dict['btts_yes'] = float(self.__find_odds_borderless(odds_btts_all[0]))
            game_dict['btts_no'] = float(self.__find_odds_borderless(odds_btts_all[1]))

        return game_dict

    def __extract_goals_odds(self, goals_match_html, game_dict):
        group_wrappers = self.__get_html_market_groups(goals_match_html)

        goals_ou_cols = group_wrappers[self._bookie_headers[GOALS_OU]].findAll('div', {'class': 'gl-Market_General'})
        if self._bookie_headers[ALTERNATIVE_TG] in group_wrappers:
            alt_goals_cols = group_wrappers[self._bookie_headers[ALTERNATIVE_TG]].findAll('div', {'class': 'gl-Market_General'})
            goals_ou_cols[0].append(alt_goals_cols[0])
            goals_ou_cols[1].append(alt_goals_cols[1])
            goals_ou_cols[2].append(alt_goals_cols[2])
            del alt_goals_cols

        labels = [s.text for s in\
                               goals_ou_cols[0].findAll('div', {'class': 'srb-ParticipantLabelCentered_Name'})]
        odds_over = [r.text for r in\
                         self.__find_odds_only(goals_ou_cols[1])]
        odds_under = [r.text for r in\
                         self.__find_odds_only(goals_ou_cols[2])]

        for label, over, under in zip(labels, odds_over, odds_under):
            if float(label) not in ACCEPTED_GOALS: continue;
            game_dict[f'over_{label}'] = float(over)
            game_dict[f'under_{label}'] = float(under)

        if self._bookie_headers[RESULT_TG] in group_wrappers:   
            teams = [t.text for t in group_wrappers[self._bookie_headers[RESULT_TG]].findAll('div', {'class': 'srb-ParticipantLabel_Name'})][:2]
            odds_groups = group_wrappers[self._bookie_headers[RESULT_TG]].findAll('div', {'class': 'gl-Market'})[1:]
            for t, over, under in zip(teams,
                                         self.__find_odds_subgroups(odds_groups[0]),
                                         self.__find_odds_subgroups(odds_groups[1])):
                if t == game_dict['home_team']:
                    team = 'home'
                elif t == game_dict['away_team']:
                    team = 'away'
                else:
                    continue

                over_ngoals = over.find('span', {'class': 'gl-ParticipantCentered_Handicap'}).text
                over_odds = float(self.__find_odds_centered(over))
                under_ngoals = under.find('span', {'class': 'gl-ParticipantCentered_Handicap'}).text
                under_odds = float(self.__find_odds_centered(under))

                if float(over_ngoals) in ACCEPTED_GOALS:
                    game_dict[f'{team}_&over_{over_ngoals}'] = over_odds
                if float(under_ngoals) in ACCEPTED_GOALS:
                    game_dict[f'{team}_&under_{under_ngoals}'] = under_odds


        if self._bookie_headers[TG_BTTS] in group_wrappers:
            for bet in self.__find_odds_subgroups(group_wrappers[self._bookie_headers[TG_BTTS]]):
                ou, n_goals, _, yn = bet.find('span', {'class': 'gl-ParticipantBorderless_Name'}).text.split()
                ou, yn = ou.lower(), yn.lower()

                if float(n_goals) not in ACCEPTED_GOALS: continue;

                odds = float(self.__find_odds_borderless(bet))
                game_dict[f'{ou}_{n_goals}_btts_{yn}'] = odds

        return game_dict

    def __extract_half_odds(self, half_match_html, game_dict):
        group_wrappers = self.__get_html_market_groups(half_match_html)

        ht_bets = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[HALF_TIME]])
        game_dict['ht_1'] = float(self.__find_odds(ht_bets[0]))
        game_dict['ht_X'] = float(self.__find_odds(ht_bets[1]))
        game_dict['ht_2'] = float(self.__find_odds(ht_bets[2]))

        if self._bookie_headers[HT_DOUBLE_CHANCE] in group_wrappers:
            ht_bets = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[HT_DOUBLE_CHANCE]])
            game_dict['ht_1/X'] = float(self.__find_odds(ht_bets[0]))
            game_dict['ht_X/2'] = float(self.__find_odds(ht_bets[1]))
            game_dict['ht_1/2'] = float(self.__find_odds(ht_bets[2]))

        if self._bookie_headers[FIRST_HALF_BTTS] in group_wrappers:
            bets = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[FIRST_HALF_BTTS]])
            game_dict['first_half_btts_yes'] = float(self.__find_odds_borderless(bets[0]))
            game_dict['first_half_btts_no'] = float(self.__find_odds_borderless(bets[1]))
        if self._bookie_headers[SECOND_HALF_BTTS] in group_wrappers:
            bets = self.__find_odds_subgroups(group_wrappers[self._bookie_headers[SECOND_HALF_BTTS]])
            game_dict['second_half_btts_yes'] = float(self.__find_odds_borderless(bets[0]))
            game_dict['second_half_btts_no'] = float(self.__find_odds_borderless(bets[1]))

        return game_dict

    def __get_html_market_groups(self, html):
        bs = BeautifulSoup(html, 'html.parser')
        group_wrappers = {}
        for group in bs.findAll('div', {'class': 'gl-MarketGroup'}):
            title = group.find('div', {'class': self.__odds_group_class})
            if title is None:
                title = group.find('div', {'class': 'cm-CouponMarketGroupButton_Text'})
                if title is None:
                    continue
            title = title.text
            group_wrappers[title] = group.find('div', {'class': 'gl-MarketGroup_Wrapper'})

        return group_wrappers
