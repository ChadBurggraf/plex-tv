import logging
import os
import sys
from plex_tv import PlexTV

if __name__ == '__main__':
	logging.basicConfig(level=logging.INFO, format='%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
	log = logging.getLogger("plex_tv")

	path = sys.argv[1].strip() if len(sys.argv) > 1 else ''

	if path:
		path = os.path.abspath(os.path.expanduser(path))

	PlexTV.log_all_metadata_atoms(path, '.*\.(m4v|mp4)$', log)