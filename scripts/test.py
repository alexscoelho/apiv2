#!/bin/env python

import os
import sys
from pathlib import Path
from utils.environment import test_environment


if __name__ == '__main__':
    args = ''

    if len(sys.argv) > 1:
        sys.argv.pop(0)
        args = ' '.join(sys.argv)

    test_environment()
    exit_code = os.system(f'pytest {args} --disable-pytest-warnings')
    
    # python don't return 256
    if exit_code:
        sys.exit(1)
