"""Adds Metal Archives album search support to the autotagger.
"""
import logging
import metallum
from beets.autotag.hooks import AlbumInfo, TrackInfo, Distance
from beets.plugins import BeetsPlugin
from beets import config
from iso3166 import countries

log = logging.getLogger('beets')

DATA_SOURCE = 'Metal Archives'
ID_PREFIX = 'ma-'

class MetalArchivesPlugin(BeetsPlugin):
    def __init__(self):
        super(MetalArchivesPlugin, self).__init__()
        self.config.add({
            'source_weight': 1.0,
            'lyrics': False,
        })

        stages = []
        if self.config['lyrics']:
            stages.append(self.fetch_lyrics)
        self.import_stages = stages

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

    def fetch_lyrics(self, session, task):
        """Fetch track lyrics from Metal Archives
        """
        for item in task.imported_items():
            if not self._is_source_id(item.mb_albumid):
                continue

            track_id = self._strip_prefix(item.mb_trackid)

            lyrics = metallum.lyrics_for_id(track_id)

            if not lyrics:
                continue

            item.lyrics = unicode(lyrics)
            if config['import']['write'].get(bool):
                item.try_write()
            item.store()

    def album_for_id(self, album_id):
        """Fetches an album by its Metal Archives ID and returns an AlbumInfo object
        or None if the album is not found.
        """
        if not self._is_source_id(album_id):
            return

        result = metallum.album_for_id(self._strip_prefix(album_id))

        if result:
            return self.get_album_info(result)

    def get_albums(self, artist, album):
        """Returns a list of AlbumInfo objects for a Metal Archives search query.
        """
        albums = []

        try:
            results = metallum.album_search(album, band=artist, strict=False, band_strict=False)
        except metallum.NoSearchResultsError:
            return albums

        for result in results:
            album = result.get()
            albums.append(self.get_album_info(album))

        return albums

    def get_album_info(self, album):
        """Returns an AlbumInfo object for a Metal Archives album object.
        """
        artist = album.bands[0]
        tracks = self.get_tracks(album.tracks)
        album_id = self._add_prefix(album.id)
        artist_id = self._add_prefix(artist.id)

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
        track_id = self._add_prefix(track.id)
        artist_id = self._add_prefix(track.band.id)
        return TrackInfo(unicode(track.title), track_id, unicode(track.band.name), artist_id, track.duration, track.overall_number,
                         track.disc_number, track.number)

    def _add_prefix(self, id):
        """Add source id prefix to id
        """
        return ID_PREFIX + str(id)

    def _strip_prefix(self, id):
        """Strip source id prefix from id
        """
        return id[len(ID_PREFIX):]

    def _is_source_id(self, id):
        """Check if an id string contains the source id prefix
        """
        return id[:len(ID_PREFIX)] == ID_PREFIX
