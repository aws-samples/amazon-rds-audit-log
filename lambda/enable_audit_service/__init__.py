"""init to update system path"""
import os
import sys
import logging

LOG_LEVEL = 'log_level'
logger = logging.getLogger()
logger.setLevel(os.environ.get(LOG_LEVEL, logging.INFO))

lambdas=''

module_dir = os.path.dirname(os.path.abspath(__file__))
module_par = os.path.normpath(os.path.join(module_dir, '.'))
sys.path.append(module_par)
