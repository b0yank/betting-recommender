import numpy as np
import pandas as pd

from .odds_provider import OddsProvider
from constants import DB_PATH

class FootballDataOddsProvider(OddsProvider):
    def __init__(self, football_database, logger=None):
        super().__init__(football_database, logger)
