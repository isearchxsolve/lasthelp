#!/usr/bin/env python3
import sys
import os

os.chdir("C:\\Users\\Admin\\Downloads\\god_ai\\api_money_bot_complete")
sys.argv = ["batch_harvester.py", "--batch", "3", "--mode", "all"]

# Import and run batch_harvester directly
import batch_harvester
