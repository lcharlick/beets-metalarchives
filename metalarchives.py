"""Adds Metal Archives album search support to the autotagger.
"""
import logging
import metallum
from beets.autotag.hooks import AlbumInfo, TrackInfo, Distance, string_dist
from beets.plugins import BeetsPlugin
from beets import config, ui
from iso3166 import countries

log = logging.getLogger('beets')

DATA_SOURCE = 'Metal Archives'
ID_PREFIX = 'ma-'


def _add_prefix(id):
    """Add source id prefix to id
    """
    return ID_PREFIX + str(id)


def _strip_prefix(id):
    """Strip source id prefix from id
    """
    return id[len(ID_PREFIX):]


def _is_source_id(id):
    """Check if an id string contains the source id prefix
    """
    return id[:len(ID_PREFIX)] == ID_PREFIX


class MetalArchivesPlugin(BeetsPlugin):
    def __init__(self):
        super(MetalArchivesPlugin, self).__init__()
        self.config.add({
            'source_weight': 1.0,
            'lyrics': False,
            'lyrics_search': False,
            'instrumental': '',
        })

        stages = []
        if self.config['lyrics'].get(bool):
            stages.append(self.fetch_lyrics)
        self.import_stages = stages

    def commands(self):
        cmd = ui.Subcommand('metalarchives', help='metal archives data source')
        cmd.parser.add_option('-l', '--lyrics', dest='lyrics',
                              action='store_true', default=False,
                              help='fetch track lyrics from metal archives')

        def func(lib, opts, args):
            if opts.lyrics:
                for item in lib.items(ui.decargs(args)):
                    self.fetch_item_lyrics(item)

        cmd.func = func
        return [cmd]

    def album_distance(self, items, album_info, mapping):
        """Returns the album distance.
        """
        dist = Distance()
        if album_info.data_source == DATA_SOURCE:
            dist.add('source', self.config['source_weight'].as_number())
        return dist

    def candidates(self, items, artist, album, va_likely):
        """Returns a list of AlbumInfo objects for Metal Archives search results
        matching an album and artist (if not various).
        """
        return self.get_albums(artist, album)

    def fetch_item_lyrics(self, item):
        """Fetch track lyrics from Metal Archives
        """
        lyrics = ''

        # Skip if lyrics are already present
        if item.lyrics:
            return

        # If this track was matched from metal archives, we can just use
        # the track id
        if _is_source_id(item.mb_albumid):
            self._log.debug(u'fetching lyrics: {0.artist} - {0.title}', item)

            track_id = _strip_prefix(item.mb_trackid)
            try:
                lyrics = metallum.lyrics_for_id(track_id)
            except metallum.NetworkError as e:
                self._log.debug('network error: {0}', e)
                return

        # Otherwise perform an album search
        elif self.config['lyrics_search'].get(bool):
            self._log.debug(u'searching for lyrics: {0.artist} - {0.title}', item)

            try:
                results = metallum.album_search(item.album, band=item.artist, strict=False,
                                                year_from=item.year, year_to=item.year)
            except metallum.NetworkError as e:
                self._log.debug('network error: {0}', e)
                return

            for result in results:
                # TODO: use Distance object to calculate actual album distance
                # using all data fields (title, year, number of tracks, etc)
                album = result.get()
                if len(album.tracks) >= item.track:
                    track = album.tracks[item.track - 1]
                    dist = string_dist(item.title, unicode(track.title))
                    # TODO: make threshold config key
                    if dist > 0.1:
                        continue

                    try:
                        lyrics = track.lyrics
                    except metallum.NetworkError as e:
                        self._log.debug('network error: {0}', e)
                        return
        else:
            return

        if lyrics:
            message = ui.colorize('text_success', 'found lyrics')
            if lyrics == u'(<em>Instrumental</em>)':
                lyrics = self.config['instrumental'].get()
            item.lyrics = unicode(lyrics)
            if config['import']['write'].get(bool):
                item.try_write()
            item.store()
        else:
            message = ui.colorize('text_error', 'no lyrics found')

        self._log.info(u'{0.artist} - {0.album} - {0.title}: {1}', item, message)

    def fetch_lyrics(self, session, task):
        """Fetch lyrics from Metal Archives for each track
        """
        for item in task.imported_items():
            self.fetch_item_lyrics(item)

    def album_for_id(self, album_id):
        """Fetches an album by its Metal Archives ID and returns an AlbumInfo object
        or None if the album is not found.
        """
        if not _is_source_id(album_id):
            return

        try:
            result = metallum.album_for_id(_strip_prefix(album_id))
        except metallum.NetworkError as e:
            self._log.debug('network error: {0}', e)
            return

        return self.get_album_info(result)

    def get_albums(self, artist, album):
        """Returns a list of AlbumInfo objects for a Metal Archives search query.
        """
        albums = []
        try:
            results = metallum.album_search(album, band=artist, strict=False, band_strict=False)
        except metallum.NetworkError as e:
            self._log.debug('network error: {0}', e)
            return

        for result in results:
            try:
                album = result.get()
            except metallum.NetworkError as e:
                self._log.debug('network error: {0}', e)
                continue
            albums.append(self.get_album_info(album))

        return albums

    def get_album_info(self, album):
        """Returns an AlbumInfo object for a Metal Archives album object.
        """
        artist = album.bands[0]
        tracks = self.get_tracks(album.tracks)
        album_id = _add_prefix(album.id)
        artist_id = _add_prefix(artist.id)

        try:
            country = countries.get(artist.country).alpha2
        except KeyError:
            country = ''

        return AlbumInfo(unicode(album.title), album_id, unicode(album.band_names), artist_id, tracks,
                         albumtype=album.type, va=False, year=album.year, month=album.date.month,
                         day=album.date.day, label=unicode(album.label), mediums=album.disc_count,
                         country=unicode(country), data_source=DATA_SOURCE, data_url=metallum.BASE_URL + '/' + album.url)

    def get_tracks(self, tracklist):
        """Returns a list of TrackInfo objects for a Metal Archives tracklist.
        """
        tracks = []
        for track in tracklist:
            tracks.append(self.get_track_info(track))
        return tracks

    def get_track_info(self, track):
        """Returns a TrackInfo object for a Metal Archives track object.
        """
        track_id = _add_prefix(track.id)
        artist_id = _add_prefix(track.band.id)
        return TrackInfo(unicode(track.title), track_id, unicode(track.band.name), artist_id, track.duration, track.overall_number,
                         track.disc_number, track.number)
