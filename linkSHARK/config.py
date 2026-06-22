import json
import logging
import logging.config
import os
import sys

def setup_logging(default_path=os.path.dirname(os.path.realpath(__file__)) + "/../loggerConfiguration.json",
                  default_level=logging.INFO):
    """
    Setup logging configuration

    :param default_path: path to the logger configuration
    :param default_level: defines the default logging level if configuration file is not found(default:logging.INFO)
    """
    path = default_path
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)
    
    sys.stdout = sys.stderr if '--help' in sys.argv else sys.stdout 
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
    logging.getLogger("main").handlers = [logging.StreamHandler(sys.stdout)]
    logging.getLogger("main").propagate = False


class ConfigValidationException(Exception):
    """
    Exception that is thrown if the config of class :class:`~issueshark.config.Config` could not be validated
    """
    pass


class Config(object):
    """
    Config object, that holds all configuration parameters
    """
    def __init__(self, args):
        """
        Initialization

        :param args: argumentparser of the class :class:`argparse.ArgumentParser`
        """
        self.host = args.db_hostname
        self.port = args.db_port
        self.user = args.db_user
        self.password = args.db_password
        self.database = args.db_database
        self.authentication_db = args.db_authentication
        self.log_level = args.log_level
        self.project_name = args.project_name
        self.ssl_enabled = args.ssl
        self.broken_keys = args.broken_keys
        self.correct_key = args.correct_key

    def get_debug_level(self):
        """
        Gets the correct debug level, based on :mod:`logging`
        """
        choices = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }

        return choices[self.log_level]

    def __str__(self):
        return "Config: host: %s, port: %s, user: %s, " \
               "password: %s, database: %s, authentication_db: %s, ssl: %s, project_name:%s, log_level: %s" % \
               (
                   self.host,
                   self.port,
                   self.user,
                   self.password,
                   self.database,
                   self.authentication_db,
                   self.ssl_enabled,
                   self.project_name,
                   self.log_level
               )
