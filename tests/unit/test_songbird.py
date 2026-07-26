import json
import pytest
from api.songbird import (
    YoutubeMetaFetcher,
    VimeoMetaFetcher,
    SoundcloudMetaFetcher,
    MetaDbManager,
    SongMeta,
)


# --- URL parsers ---

class TestYoutubeMetaFetcher:
    def test_standard_url(self):
        f = YoutubeMetaFetcher("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert f.get_video_id() == "dQw4w9WgXcQ"

    def test_short_url(self):
        f = YoutubeMetaFetcher("https://youtu.be/dQw4w9WgXcQ")
        assert f.get_video_id() == "dQw4w9WgXcQ"

    def test_playlist_stripped_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc123"
        stripped = url.split("&list")[0]
        f = YoutubeMetaFetcher(stripped)
        assert f.get_video_id() == "dQw4w9WgXcQ"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            YoutubeMetaFetcher("https://notyoutube.com/watch?v=nope").get_video_id()


class TestVimeoMetaFetcher:
    def test_standard_url(self):
        f = VimeoMetaFetcher("https://vimeo.com/123456789")
        assert f.get_video_id() == "123456789"

    def test_player_url(self):
        f = VimeoMetaFetcher("https://player.vimeo.com/video/123456789")
        assert f.get_video_id() == "123456789"


class TestSoundcloudMetaFetcher:
    def test_standard_url(self):
        f = SoundcloudMetaFetcher("https://soundcloud.com/artist/track-name")
        assert f.get_video_id() == "artist/track-name"


# --- playlist strip ---

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc123&list=PLxyz", "https://www.youtube.com/watch?v=abc123"),
    ("https://www.youtube.com/watch?v=abc123", "https://www.youtube.com/watch?v=abc123"),
])
def test_playlist_strip(url, expected):
    assert url.split("&list")[0] == expected


# --- MetaDbManager ---

def test_metadb_add_and_get(tmp_path):
    path = tmp_path / "metadb.json"
    db = MetaDbManager(str(path))
    meta = SongMeta(url="https://youtube.com/watch?v=abc", file_path="/tmp/abc.mp3", title="Test Song")
    db.add_song_meta("abc", meta)
    result = db.get_song_meta("abc")
    assert result is not None
    assert result.url == meta.url
    assert result.title == "Test Song"


def test_metadb_get_missing(tmp_path):
    path = tmp_path / "metadb.json"
    db = MetaDbManager(str(path))
    assert db.get_song_meta("nonexistent") is None


def test_metadb_trie_populated(tmp_path):
    path = tmp_path / "metadb.json"
    db = MetaDbManager(str(path))
    meta = SongMeta(url="https://youtube.com/watch?v=abc", file_path="/tmp/abc.mp3", title="Bohemian Rhapsody")
    db.add_song_meta("abc", meta)
    matches = db.trie.starts_with("Bohem")
    assert matches is not None
    assert "Bohemian Rhapsody" in matches


def test_metadb_persists(tmp_path):
    path = tmp_path / "metadb.json"
    db = MetaDbManager(str(path))
    meta = SongMeta(url="https://youtube.com/watch?v=xyz", file_path="/tmp/xyz.mp3", title="Song")
    db.add_song_meta("xyz", meta)

    db2 = MetaDbManager(str(path))
    assert db2.get_song_meta("xyz") is not None
