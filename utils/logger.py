import os
from datetime import datetime

class Logging:
    INFO = 'INFO'
    ERROR = 'ERROR'
    WARNING = 'WARNING'

class Logger:
    def __init__(self, filepath, read_write='a'):
        self.filepath = filepath
        self.read_write = read_write

    def log_message(self, message, log_level=Logging.INFO):
        with open(self.filepath, self.read_write) as fp:
            fp.write(f'{datetime.now()}, ::{log_level}::, {message}')
            fp.write(os.linesep)

    def add_newline(self):
        with open(self.filepath, self.read_write) as fp:
            fp.write(os.linesep)