#!/usr/bin/env python3

import os
import subprocess
import argparse
import sys

# 1. Get the current directory of the script
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. Get the parent directory (my_project)
parent_dir = os.path.dirname(current_dir)

# 3. Add the parent directory to sys.path
sys.path.append(parent_dir)

