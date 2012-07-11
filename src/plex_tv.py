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

class PlexTV(object):
	def __init__(self, source, destination, pattern=".*\.(m4v|mp4)$", log=logging.getLogger("plex_tv")):
		self._source = source
		self._destination = destination
		self._pattern = pattern
		self._log = log

	@property
	def destination(self):
		return self._destination

	@property
	def log(self):
		return self._log

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
					self.log.info("Un-linking %s", subpath)
					os.unlink(file)
			return True
		return False

	def create_all_links(self):
		if self.validate_paths():
			for show in PlexTV.get_dirs(self.source):
				for season in PlexTV.get_dirs(show):
					for episode in PlexTV.get_files(season, self.pattern):
						filename, fileext = os.path.splitext(os.path.basename(episode))
						file = None
						err = None

						try:
							file = PlexTV.get_file(episode)
						except Exception e:
							err = e

						if file:
							name = PlexTV.create_file_name(file, fileext)
							if name:
								if PlexTV.create_link(episode, os.path.join(self.destination, name)):
									self.log.info("Link created for %s", name)
								else:
									self.log.info("Link exists for %s", name)
							else:	
								self.log.error("Invalid or incomplete MP4 container %s", episode)
						else:
							self.log.error("Failed to open file %s%s", episode, (" " + str(err) if error else ""))
			return True
		return False
						
	@staticmethod
	def create_file_name(file, ext):
		atoms = file.findall('.//data')
		show = PlexTV.find_item(atoms, 'tvshow')
		season = PlexTV.find_item(atoms, 'tvseason')
		title = PlexTV.find_item(atoms, 'title')
		episode = PlexTV.find_item(atoms, 'tvepisode')

		if not title:
			title = PlexTV.find_item(atoms, 'tvepisodenum')

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
	def get_search_pattern_from_extensions(extensions):
		pattern = '.*\.('
		i = 0
		for ext in extensions:
			if i > 0:
				pattern += '|'
			pattern += ext.strip().replace('*', '').replace('.', '')
			i += 1
		return pattern + ')$'

	@staticmethod
	def log_all_metadata_atoms(path, pattern, log=logging.getLogger("plex_tv")):
		files = []
		if os.path.isdir(path):
			files = PlexTV.get_files(path, pattern)
		else:
			files = [path]

		for file in files:
			mp4 = PlexTV.get_file(file)
			if mp4:
				log.info(file)
				atoms = mp4.findall('.//data')
				for atom in atoms:
					data = atom.get_attribute('data')
					log.info("   %s\t%s", atom.parent.name, data)
			else:
				log.error("Failed to open file %s", path)

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
					self.log.error('Source and destionation paths must not point to the same location.')
			else:
				self.log.error('Both source and destination paths must be directories.')
		else:
			self.log.error('Both source and destination directories must exist')
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
	def __init__(self, tv, patterns=["*.m4v", "*.mp4"], log=logging.getLogger("plex_tv")):
		super(PlexTVEventHandler, self).__init__(patterns=patterns, ignore_patterns=None, ignore_directories=True, case_sensitive=False)
		self._tv = tv
		self._log = log

	@property
	def log(self):
		return self._log

	@property
	def tv(self):
		return self._tv

	def on_any_event(self, event):
		self.loglog.info('A %s event was detected at %s', event.event_type, event.src_path)
		self.tv.clean_broken_links() and self.tv.create_all_links()

if __name__ == '__main__':
	logging.basicConfig(level=logging.INFO, format='%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
	log = logging.getLogger("plex_tv")

	config = ConfigParser.SafeConfigParser({'pid-file': '/tmp/plextvd.pid', 'extensions': '.m4v,.mp4'})
	config.read('plex_tv.cfg')

	source = sys.argv[1].strip() if len(sys.argv) > 1 else ''
	
	if not source:
		source = config.get('plextv', 'source-dir').strip()

	dest = sys.argv[2].strip() if len(sys.argv) > 2 else ''

	if not dest:
		dest = config.get('plextv', 'dest-dir').strip()

	pidfile = sys.argv[3].strip() if len(sys.argv) > 3 else ''

	if not pidfile:
		pidfile = config.get('plextv', 'pid-file').strip()

	source = os.path.abspath(os.path.expanduser(source))
	dest = os.path.abspath(os.path.expanduser(dest))
	pidfile = os.path.abspath(os.path.expanduser(pidfile))
	extensions = config.get('plextv', 'extensions').split(',')
	patterns = ['*' + e.strip() for e in extensions]
	search = PlexTV.get_search_pattern_from_extensions(extensions)

	tv = PlexTV(source, dest, pattern=search)
	tv.clean_broken_links() and tv.create_all_links()
