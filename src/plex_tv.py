#!/usr/bin/env python

"""
Walks all TV Shows in an iTunes library and creates Plex-friendly symlinks out of them.

Configure this script by editing plex_tv.cfg
"""

import ConfigParser
import logging
import io
import os
import re
import sys
import time
from daemon import Daemon
from mp4file.mp4file import Mp4File
from watchdog.events import LoggingEventHandler, PatternMatchingEventHandler
from watchdog.observers import Observer

__author__ = "Chad Burggraf"
__copyright__ = "Copyright 2012, Chad Burggraf"
__license__ = "MIT"
__status__ = "Prototype"

config = ConfigParser.SafeConfigParser({'pid-file': '/tmp/plextvd.pid', 'extensions': '.m4v,.mp4'})
config.read('plex_tv.cfg')

log = logging.getLogger("tv")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class PlexTV(object):
	def __init__(self, source, destination, pattern=".*\.(m4v|mp4)$"):
		self._source = source
		self._destination = destination
		self._pattern = pattern

	@property
	def destination(self):
		return self._destination

	@property
	def pattern(self):
		return self._pattern

	@property
	def source(self):
		return self._source

	def clean_broken_links(self):
		if self.validate_paths():
			for subpath in os.listdir(self.destination):
				file = os.path.join(self.destination, subpath)
				if os.path.islink(file) and not os.path.exists(os.readlink(file)):
					log.info("Un-linking %s", subpath)
					os.unlink(file)
			return True
		return False

	def create_all_links(self):
		if self.validate_paths():
			for show in PlexTV.get_dirs(self.source):
				for season in PlexTV.get_dirs(show):
					for episode in PlexTV.get_files(season, self.pattern):
						filename, fileext = os.path.splitext(os.path.basename(episode))
						file = PlexTV.get_file(episode)

						if file:
							name = PlexTV.create_file_name(file, fileext)
							if name:
								if PlexTV.create_link(episode, os.path.join(self.destination, name)):
									log.info("Link created for %s", name)
								else:
									log.info("Link exists for %s", name)
							else:	
								log.error("Invalid or incomplete MP4 container %s%s", filename, fileext)
						else:
							log.error("Failed to open file %s%s", filename, fileext)
			return True
		return False
						
	@staticmethod
	def create_file_name(file, ext):
		atoms = file.findall('.//data')
		show = PlexTV.find_item(atoms, 'tvshow')
		season = PlexTV.find_item(atoms, 'tvseason')
		title = PlexTV.find_item(atoms, 'title')
		episode = PlexTV.find_item(atoms, 'tvepisode')

		if show and season > 0 and title and episode > 0:
			return "%s - S%02dE%02d - %s%s" % (PlexTV.remove_invalid_path_chars(show), season, episode, PlexTV.remove_invalid_path_chars(title), ext)
		else:
			return None

	@staticmethod
	def create_link(source, dest):
		if not os.path.exists(dest):
			os.symlink(source, dest)
			return True
		return False

	@staticmethod
	def find_item(atoms, name):
		for atom in atoms:
			if atom.parent and atom.parent.name == name:
				return atom.get_attribute('data')
		return None

	@staticmethod
	def get_dirs(path):
		dirs = []
		for subpath in os.listdir(path):
			dirpath = os.path.join(path, subpath)
			if os.path.isdir(dirpath):
				dirs.append(dirpath)
		return dirs

	@staticmethod
	def get_file(path):
		try:
			return Mp4File(path)
		except IOError:
			return None

	@staticmethod
	def get_files(path, pattern):
		files = []
		for subpath in os.listdir(path):
			filepath = os.path.join(path, subpath)
			if re.search(pattern, subpath) and os.path.isfile(filepath) and not os.path.islink(filepath):
				files.append(filepath)
		return files

	@staticmethod
	def remove_invalid_path_chars(name):
		for c in '\/:*?"<>|':
			name = name.replace(c, '')
		return name

	def validate_paths(self):
		if os.path.exists(self.source) and os.path.exists(dest):
			if os.path.isdir(self.source) and os.path.isdir(dest):
				if not os.path.samefile(self.source, dest):
					return True
				else:
					log.error('Source and destionation paths must not point to the same location.')
			else:
				log.error('Both source and destination paths must be directories.')
		else:
			log.error('Both source and destination directories must exist')
		return False

class PlexTVDaemon(Daemon):
	def __init__(self, pidfile, tv, patterns):
		super(PlexTVDaemon, self).__init__(pidfile)
		self._tv = tv
		self._handler = PlexTVEventHandler(tv, patterns)
		self._observer = Observer()
		self._observer.schedule(self.handler, self.tv.source, recursive=True)

	@property
	def handler(self):
		return self._handler

	@property
	def observer(self):
		return self._observer

	@property
	def tv(self):
		return self._tv

	def run(self):
		self.tv.clean_broken_links() and self.tv.create_all_links()
		observer.start()

		while True:
			time.sleep(1)

	def stop(self):
		self.observer.stop()
		self.observer.join()
		super.stop()

class PlexTVEventHandler(PatternMatchingEventHandler):
	def __init__(self, tv, patterns=["*.m4v", "*.mp4"]):
		super(PlexTVEventHandler, self).__init__(patterns=patterns, ignore_patterns=None, ignore_directories=True, case_sensitive=False)
		self._tv = tv

	@property
	def tv(self):
		return self._tv

	def on_any_event(self, event):
		log.info('A %s event was detected at %s', event.event_type, event.src_path)
		self.tv.clean_broken_links() and self.tv.create_all_links()

def _get_search_pattern_from_extensions(extensions):
	pattern = '.*\.('
	i = 0
	for ext in extensions:
		if i > 0:
			pattern += '|'
		pattern += ext.strip().replace('*', '').replace('.', '')
		i += 1
	return pattern + ')$'

if __name__ == '__main__':
	source = os.path.abspath(os.path.expanduser(config.get('plextvd', 'source-dir')))
	dest = os.path.abspath(os.path.expanduser(config.get('plextvd', 'dest-dir')))
	pidfile = os.path.abspath(os.path.expanduser(config.get('plextvd', 'pid-file')))
	extensions = config.get('plextvd', 'extensions').split(',')
	patterns = ['*' + e.strip() for e in extensions]
	search = _get_search_pattern_from_extensions(extensions)

	tv = PlexTV(source, dest, pattern=search)
	tv.clean_broken_links() and tv.create_all_links()
