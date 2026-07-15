"""Launch Freqtrade with offline exchange patch."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import offline_patch
offline_patch.patch()

from freqtrade.main import main
sys.exit(main())
