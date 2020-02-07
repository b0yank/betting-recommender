import numpy as np
import pandas as pd
from datetime import datetime
import time
import urllib
import re
import json
from bs4 import BeautifulSoup


from constants import TEAMS_CSV_PATH, LEAGUES_CSV_PATH, GAMES_CSV_PATH, GAMES_BY_TEAM_CSV_PATH
from utils import fix_unicode, Logging

SEASON_START_MONTH = 7
    
class FootballDataService:
    """ Abstract football games database class.
    """
    def __init__(self):
        self._games = None
        self._games_by_team = None
        self._teams = None
        self._leagues = None

    @property
    def games(self):
        if self._games is None:
            self._games = pd.read_csv(GAMES_CSV_PATH).astype(dtype={'date': 'datetime64[ns]'})      
        return self._games

    @property
    def teams(self):
        if self._teams is None:
            self._teams = pd.read_csv(TEAMS_CSV_PATH)
        return self._teams
    
    @property
    def leagues(self):
        if self._leagues is None:
            self._leagues = pd.read_csv(LEAGUES_CSV_PATH)
        return self._leagues
    
    @property
    def games_by_team(self):
        if self._games_by_team is None:
            self._games_by_team = pd.read_csv(GAMES_BY_TEAM_CSV_PATH).astype(dtype={'date': 'datetime64[ns]'})
        return self._games_by_team

    def get_league_id(self, league_name, country): raise NotImplementedError;
    def get_team_id(self, team_name, country): raise NotImplementedError;
    def provide_games(self, league_ids, start_date, end_date): raise NotImplementedError;
    def update_games_db(self): raise NotImplementedError;


class SoccerwayFootballDataService(FootballDataService):
    """ Football database using game data from www.soccerway.com
    """
    _LEAGUE_URLS = {
        0: 'https://int.soccerway.com/national/england/premier-league/',
        1: 'https://int.soccerway.com/national/england/championship/',
        2: 'https://int.soccerway.com/national/italy/serie-a/',
        3: 'https://int.soccerway.com/national/spain/primera-division/',
        4: 'https://int.soccerway.com/national/germany/bundesliga/',
        5: 'https://int.soccerway.com/national/france/ligue-1/',
        6: 'https://int.soccerway.com/national/netherlands/eredivisie/',
        7: 'https://int.soccerway.com/national/portugal/portuguese-liga-/',
        8: 'https://int.soccerway.com/national/turkey/super-lig/',
        9: 'https://int.soccerway.com/national/russia/premier-league/',
        10: 'https://int.soccerway.com/national/greece/super-league/',
        11: 'https://int.soccerway.com/national/scotland/premier-league/'
    }
    
    _LEAGUE_ID_TO_SOCCERWAY_COMP_ID = {
        0: 8,
        1: 70,
        2: 13,
        3: 7,
        4: 9,
        5: 16,
        6: 1,
        7: 63,
        8: 19,
        9: 121,
        10: 107,
        11: 43,
    }

    def __init__(self, logger):
        super().__init__()

        self.logger = logger
        
    def update_games_db(self):
        season_matches = []
        try:
            for league_id in self.leagues.index.values:
                for attempt in range(3):
                    try:
                        country = self.leagues.loc[league_id]['country']
                        league = self.leagues.loc[league_id]['league']
                        competition_id = self._LEAGUE_ID_TO_SOCCERWAY_COMP_ID[league_id]
           
                        response = urllib.request.urlopen(self._LEAGUE_URLS[league_id])
                        round_id = re.compile('r(\\d{4,5})').findall(response.geturl())[0]
                        page = 0
    
                        while True:
                            results_url = 'https://int.soccerway.com/a/block_competition_matches_summary' +\
                                            '?block_id=page_competition_1_block_competition_matches_summary_5' +\
                                            f'&callback_params={{"page":"{page - 1}","block_service_id":' +\
                                            '"competition_summary_block_competitionmatchessummary",' +\
                                            f'"round_id":{round_id},"outgroup":false,"view":2,' +\
                                            f'"competition_id":{competition_id}}}&action=changePage&params={{"page":{page}}}'

                            table_response = urllib.request.urlopen(results_url)
                            rspns = table_response.read().decode('utf-8').replace('\\"', '"').replace('\\/', '/').replace('""', '"')\
                                        .replace('\\u00fc', '\u00fc').replace('\\u00f6', '\u00f6')\
                                        .replace('\\u00e4', '\u00e4').replace('\\u00df', '\u00df')
                            bs = BeautifulSoup(rspns, 'lxml')
                            if len(bs.find('tr').contents) == 0:
                                break

                            table = bs.find('table', {'class': 'matches'})
                            ms, skipped_past_games = self.__extract_results(table, league_id, country)

                            # if no games were extracted from current results table, and we went through a game that's in the past
                            # then all of them were already in the database, hence there's no point trying to add even earlier games
                            if len(ms) == 0 and skipped_past_games:
                                break

                            if len(ms) > 0:
                                season_matches += ms

                            # print('Progress: {0:.2f}%'.format(len(season_matches) * 100 / (games_in_season)))
                            time.sleep(np.random.randint(2, 5))
                            page -= 1
                        break
                    except:
                        time.sleep(1)
                        continue

                print(f'League results for league with id {league_id} updated.')

            matches_df = pd.DataFrame.from_dict(season_matches)
            matches_df['season'] = int(self.date_to_season(datetime.now()))
            self.games.append(matches_df, ignore_index=True).to_csv(GAMES_CSV_PATH, index_label=False)

            self.__update_games_by_team()
        except Exception as ex:
            if len(season_matches) > 0:
                matches_df = pd.DataFrame.from_dict(season_matches)
                matches_df['season'] = int(self.date_to_season(datetime.now()))
                self.games.append(matches_df, ignore_index=True).to_csv(GAMES_CSV_PATH, index_label=False)

            self.logger.log_message(str(ex), Logging.ERROR)
            raise type(ex)(str(ex))
    
    def provide_games(self, league_ids, start_date, end_date):
        games = self.provide_past_games(league_ids, start_date, end_date)
        return games.append(self.provide_future_games(league_ids, start_date, end_date))
        
    def provide_past_games(self, league_ids, start_date, end_date):
        return self.games[(self.games.league_id.isin(league_ids))&\
                          (self.games.date >= start_date)&\
                          (self.games.date <= end_date)][['league_id', 'home_team_id', 'away_team_id', 'date', 'season']]
    
    def provide_future_games(self, league_ids, start_date, end_date):
        if end_date < datetime.now():
            return pd.DataFrame([])

        season = int(self.date_to_season(datetime.now()))
        upcoming_games = []
        for league_id in league_ids:
            country = self.leagues.loc[league_id]['country']
            last_game_date = self.games[self.games.league_id == league_id]['date'].max()
            
            if last_game_date > start_date:
                start_date = last_game_date
            
            league_url = self._LEAGUE_URLS[league_id] + self.date_to_season(datetime.now()) + '/'
            response = urllib.request.urlopen(league_url).read()
            round_id = re.compile('r(\\d{4,5})').findall(str(response))[0]
            competition_id = self._LEAGUE_ID_TO_SOCCERWAY_COMP_ID[league_id]
            
            page = 0
            while True:
                results_url = 'https://int.soccerway.com/a/block_competition_matches_summary' +\
                              '?block_id=page_competition_1_block_competition_matches_summary_5' +\
                              f'&callback_params={{"page":"{page - 1}","block_service_id":' +\
                              '"competition_summary_block_competitionmatchessummary",' +\
                              f'"round_id":{round_id},"outgroup":false,"view":2,' +\
                              f'"competition_id":{competition_id}}}&action=changePage&params={{"page":{page}}}'

                table_response = urllib.request.urlopen(results_url)
                rspns = table_response.read().decode('utf-8').replace('\\"', '"').replace('\\/', '/')\
                            .replace('""', '"').replace('\\u00fc', '\u00fc').replace('\\u00f6', '\u00f6')\
                            .replace('\\u00e4', '\u00e4').replace('\\u00df', '\u00df')
                bs = BeautifulSoup(rspns, 'html.parser')
                if len(bs.find('tr').contents) == 0:
                    break

                for match in bs.find('table', {'class': 'matches'}).findAll('tr', {'class': 'match'}):
                    date = datetime.strptime(match.find('td', {'class': 'date'}).text, '%d/%m/%y')
                    if date < start_date:
                        continue
                    if date > end_date:
                        break
                    
                    if 'score' in match.find('td', {'class': 'score-time'}).attrs['class']:
                        continue
                        
                    home_team = fix_unicode(match.find('td', {'class': 'team-a'}).find('a').attrs['title'])
                    away_team = fix_unicode(match.find('td', {'class': 'team-b'}).find('a').attrs['title'])
                    home_team_id = self.teams[(self.teams.country == country)&(self.teams.team == home_team)]\
                                            .index.values[0]
                    away_team_id = self.teams[(self.teams.country == country)&(self.teams.team == away_team)]\
                                            .index.values[0]
                    
                    upcoming_games.append({'date': date,
                                           'season': season,
                                           'home_team_id': home_team_id,
                                           'away_team_id': away_team_id,
                                           'league_id': league_id})
                page += 1
                
        return pd.DataFrame.from_dict(upcoming_games)

    def get_team_id(self, team_name, country):
        return self.teams[(self.teams.team == team_name)&(self.teams.country == country)].index.values[0]

    def get_league_id(self, league_name, country):
        return self.leagues[(self.leagues.league == league)&(self.leagues.country == country)].index.values[0]

    def date_to_season(self, date):
        year, month = date.year, date.month
        
        if month >= SEASON_START_MONTH:
            return str(year) + str(year + 1)
        
        return str(year - 1) + str(year)

    def __extract_results(self, matches_table, league_id, country):
        score_regex = re.compile('(\\d{1,2}) - (\\d{1,2})')
        goals_regex = re.compile('\\d+')
    
        matches_stats = []
        skipped_past_game = False
        for tr in matches_table.findAll('tr', {'class': 'match'}):        
            date = ''.join(tr.find('td', {'class': 'date'}).find('span').contents)
            team_a = fix_unicode(tr.find('td', {'class': 'team-a'}).find('a').attrs['title'])
            team_b = fix_unicode(tr.find('td', {'class': 'team-b'}).find('a').attrs['title'])
            score_time_anchor = tr.find('td', {'class': 'score-time'}).find('a')
            score_time = score_time_anchor.text

            score = score_regex.findall(score_time)
            if len(score) == 0:
                continue
        
            date = datetime.strptime(date, '%d/%m/%y')
        
            home_team_id = self.teams[(self.teams.team == team_a)&(self.teams.country == country)].index.values[0]
            away_team_id = self.teams[(self.teams.team == team_b)&(self.teams.country == country)].index.values[0]

            # skip game if it already exists in the database
            if len(self.games[(self.games.home_team_id == home_team_id)&\
                              (self.games.away_team_id == away_team_id)&\
                              (self.games.date == date)]) > 0:
                skipped_past_game = True
                continue
        
            match = {
                'weekday': date.weekday(),
                'day': date.day,
                'month': date.month,
                'year': date.year,
                'date': date,
                'home_team_id': home_team_id,
                'away_team_id': away_team_id,
                'league_id': league_id,
                'country': country
            }

            if 'PSTP' in score_time:
                continue
            
            result = tuple(map(int, score[0]))

            match_url = 'https://int.soccerway.com' + score_time_anchor.attrs['href']
            match_response = urllib.request.urlopen(match_url).read()
            match_bs = BeautifulSoup(match_response, 'lxml')            

            dl_all = match_bs.find_all('dl')
            match_facts_table = {''.join(k.text): ''.join(v.text) for dl in dl_all for k, v in\
                       zip(dl.findAll('dt'), dl.findAll('dd'))}

            ft_result = tuple(map(int, score_regex.findall(match_facts_table['Full-time'])[0]))
            ht_result = tuple(map(int, score_regex.findall(match_facts_table['Half-time'])[0]))\
                            if 'Half-time' in match_facts_table else (-1, -1)
            game_week = int(match_facts_table['Game week']) if 'Game week' in match_facts_table else -1
            ko_time = match_facts_table['Kick-off'] if 'Kick-off' in match_facts_table else None
            venue = match_facts_table['Venue'] if 'Venue' in match_facts_table else None

            ft_home, ft_away = ft_result
            ht_home, ht_away = ht_result
            match['time'] = None if ko_time is None else datetime.strptime(ko_time.strip(), '%H:%M')
            match['ft_home'] = ft_home
            match['ft_away'] = ft_away
            match['ht_home'] = ht_home
            match['ht_away'] = ht_away
            match['game_week'] = game_week
            #############################################################################
            match['venue'] = venue

            players_stats = []
            for lineups_div in match_bs.findAll('div', {'class': 'combined-lineups-container'}):
                home_lineup = lineups_div.find('div', {'class': 'left'}).find('tbody')
                away_lineup = lineups_div.find('div', {'class': 'right'}).find('tbody')

                starters = None
                for home_away, lineup in enumerate([home_lineup, away_lineup]):
                    players_tr = lineup.findAll('tr')
                    if starters is None:
                        starters = len(players_tr) == 12

                    for player_tr in players_tr:
                        if player_tr.find('a') is None:
                            continue
                    
                        player_anchor = player_tr.find('a')
                        player_name = player_anchor.text
                        player_link = player_anchor.attrs['href']
                    
                        bookings_td = player_tr.find('td', {'class': 'bookings'})
                        if bookings_td is None:
                            continue

                        bookings = [False, False, False]
                        own_goal = False
                        goals = []
                        for card_span in bookings_td.findAll('span'):
                            card_img = card_span.find('img')
                            if 'YC.png' in card_img.attrs['src']:
                                bookings[0] = True
                            if 'Y2C.png' in card_img.attrs['src']:
                                bookings[1] = True
                            if 'RC.png' in card_img.attrs['src']:
                                bookings[2] = True
                            if 'OG.png' in card_img.attrs['src']:
                                own_goal = True
                            if 'G.png' in card_img.attrs['src']:
                                goal = sum(map(int, goals_regex.findall(card_span.text)))
                                goals.append(goal)
                    
                        shirt_number_str = player_tr.find('td', {'class': 'shirtnumber'}).text
                        shirt_number = int(shirt_number_str) if shirt_number_str.isdigit() else -1
                        
                        sub_imgs = player_tr.find('td', {'class': 'player'})\
                                                .findAll('img', {'title': 'Substituted'})
                        subbed_off = False
                        subbed_in = False
                        for sub_img in sub_imgs:
                            if 'SO.png' in sub_img.attrs['src']:
                                subbed_off = True
                            if 'SI.png' in sub_img.attrs['src']:
                                subbed_in = True

                        player = {
                            'name': player_name,
                            'href': player_link,
                            'home_side': home_away == 0,
                            'shirt_number': shirt_number,
                            'starter': starters,
                            'subbed_off': subbed_off,
                            'subbed_in': subbed_in,
                            'bookings': bookings,
                            'own_goal': own_goal,
                            'goals': goals
                        }
                        players_stats.append(player)   
        
            match['players'] = players_stats
            chart_src = match_bs.find('div', {'id': 'page_match_1_block_match_stats_plus_chart_13'})
            if chart_src is None:
                chart_src = match_bs.find('div', {'id': 'page_match_1_block_match_stats_plus_chart_14'})
        
            if chart_src is not None:
                try:
                    chart_src = chart_src.find('iframe').attrs['src']

                    chart_response = urllib.request.urlopen('https://int.soccerway.com' + chart_src).read()
                    chart_bs = BeautifulSoup(chart_response, 'lxml')

                    stat_rows = chart_bs.find('table').findAll('td', {'class': 'legend'})

                    match['corners_home'] = int(stat_rows[0].contents[0])
                    match['corners_away'] = int(stat_rows[2].contents[0])
                    match['shots_on_home'] = int(stat_rows[3].contents[0])
                    match['shots_on_away'] = int(stat_rows[5].contents[0])
                    match['shots_off_home'] = int(stat_rows[6].contents[0])
                    match['shots_off_away'] = int(stat_rows[8].contents[0])
                    match['fouls_home'] = int(stat_rows[9].contents[0])
                    match['fouls_away'] = int(stat_rows[11].contents[0])
                    match['offsides_home'] = int(stat_rows[12].contents[0])
                    match['offsides_away'] = int(stat_rows[14].contents[0])

                    possession_regex = re.compile('\"y\":(\\d{1,2})')
                    possession_script = chart_bs.findAll('script', text = re.compile('\"y\":(\\d{1,2})'))
                    possession_data = [m for m in map(int, possession_regex.findall(str(possession_script)))]

                    match['possession_home'] = possession_data[1]
                    match['possession_away'] = possession_data[0]
                except: i=5;
        
            matches_stats.append(match)
        
            time.sleep(np.random.randint(1, 3))
        
        return matches_stats, skipped_past_game

    def __update_games_by_team(self):
        missing_games = self.games[self.games.date > self.games_by_team.date.max()].copy()
        if len(missing_games) == 0:
            return
    
        core_cols = ['date', 'league_id', 'season', 'home_team_id', 'away_team_id']
        get_side_cols = lambda side: [f'corners_{side}', f'fouls_{side}', f'ht_{side}', f'ft_{side}',
                                 f'offsides_{side}', f'possession_{side}', f'shots_off_{side}',
                                 f'shots_on_{side}']


        games_by_team_new = []
        for side in ['home', 'away']:
            other_side = 'home' if side == 'away' else 'away'

            games_teams = missing_games[get_side_cols(side) + core_cols].rename({
                                                                f'{side}_team_id': 'team_id',
                                                                f'{other_side}_team_id': 'opponent_id',
                                                                f'corners_{side}': 'corners_team',
                                                                f'fouls_{side}': 'fouls_team',
                                                                f'ht_{side}': 'ht_goals_team',
                                                                f'ft_{side}': 'ft_goals_team',
                                                                f'offsides_{side}': 'offsides_team',
                                                                f'possession_{side}': 'possession_team',
                                                                f'shots_off_{side}': 'shots_off_team',
                                                                f'shots_on_{side}': 'shots_on_team'
                                                            }, axis=1).copy()

            stats_opponent = missing_games[get_side_cols(other_side)].rename({
                                                                f'corners_{other_side}': 'corners_opponent',
                                                                f'fouls_{other_side}': 'fouls_opponent',
                                                                f'ht_{other_side}': 'ht_goals_opponent',
                                                                f'ft_{other_side}': 'ft_goals_opponent',
                                                                f'offsides_{other_side}': 'offsides_opponent',
                                                                f'possession_{other_side}': 'possession_opponent',
                                                                f'shots_off_{other_side}': 'shots_off_opponent',
                                                                f'shots_on_{other_side}': 'shots_on_opponent'
                                                            }, axis=1)

            games_teams = games_teams.merge(stats_opponent, how='inner', left_index=True, right_index=True)
            games_teams['is_home'] = side == 'home'

            games_by_team_new.append(games_teams)
        
        games_by_team_new = pd.concat(games_by_team_new)

        self.games_by_team.append(games_by_team_new, ignore_index=True).to_csv(GAMES_BY_TEAM_CSV_PATH, index_label=False)