import configparser
import os

# config.ini lives next to mqtt-energi.py, independent of the working directory
CFG_NAME = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini"
)

config_file = configparser.ConfigParser()


def read():
    config = configparser.ConfigParser()
    config.read(CFG_NAME)
    return config
