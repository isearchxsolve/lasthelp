#!/usr/bin/env python3
import sys
import os

os.chdir("C:\\Users\\Admin\\Downloads\\god_ai\\api_money_bot_complete")

# Parse arguments
import argparse
parser = argparse.ArgumentParser(description="Batch Universal Harvester")
parser.add_argument("--mode", choices=["signup", "signin", "harvest", "all", "detect"], default="all")
parser.add_argument("--batch", type=int, default=4, help="Batch size (parallel count)")
parser.add_argument("--platforms", nargs="+", help="Specific platforms (default: all)")
parser.add_argument("--resume", type=str, default="", help="Resume from this platform (skip earlier ones)")
args = parser.parse_args()

# Import and run batch_harvester directly
import batch_harvester

# Run the batch
batch_harvester.main(args)
