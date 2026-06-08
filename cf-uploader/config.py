""" Simple config reading. """

import os
import re
import logging
import configparser

logger = logging.getLogger(__name__)


def _strip_libconfig_comment(line):
    """Strip libconfig-style // inline comments that follow a closing quote.

    libconfig treats // as a line comment; Python configparser does not.
    This handles patterns like:
        key="value"   // some comment     -> key="value"
        key="https://example.com"         -> key="https://example.com"  (unchanged)
    The regex anchors on a closing double-quote followed by whitespace+//,
    so // inside a quoted string (e.g. URLs) is never touched.
    """
    return re.sub(r'"\s*//.*$', '"', line)


def get_conf_file_contents():

    """ Test for and read the contents of the config file. """

    conf_file = '../settings.conf'
    if os.path.exists(conf_file):
        logger.info("Found conf file {}".format(conf_file))
        lines = ['[general]']
        with open(conf_file, 'r') as f:
            for line in f:
                lines.append(_strip_libconfig_comment(line.rstrip('\n')))
        return '\n'.join(lines)

    return None


def read_config_section(config, section):

    """ Read a section of a config file into a dict and return it. """

    logger.info("Reading section {} from config.".format(section))

    configuration = {}
    options = config.options(section)

    for option in options:

        try:
            configuration[option] = config.get(section, option)
            logger.debug("Successfully read option {}: {}".format(option, configuration[option]))

        except configparser.NoOptionError:
            logger.warning("Could not read config option {} from section {}".format(option, section))
            configuration[option] = None

    return configuration


def read_local_config():
    config_parser = configparser.RawConfigParser()
    config_parser.read_string(get_conf_file_contents())  # readfp() removed in Python 3.12
    return read_config_section(config_parser, "general")
