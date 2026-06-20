"""Aggregate the latest uploads across the admin-tracked YouTube channels for
the home page's "Latest Videos" panel.

Results are cached (the YouTube Data API has a daily quota), and resolved
@handle -> channel id mappings are cached for a day.
"""
import logging
import requests
from django.conf import settings
from django.core.cache import cache
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

_CACHE_KEY = "home_latest_videos_v1"
_CACHE_TTL = 1200          # 20 minutes
_CHANNEL_ID_TTL = 86400    # 1 day for resolved @handle -> UC id
_PER_CHANNEL = 3
_TIMEOUT = 8


def _api_key():
    return getattr(settings, "YOUTUBE_API_KEY", None)


def _resolve_channel_id(ref):
    """Return a UC... channel id for a UC id or an @handle (cached)."""
    if not ref:
        return None
    if not ref.startswith("@"):
        return ref
    ck = f"yt_channel_id:{ref}"
    cached = cache.get(ck)
    if cached:
        return cached
    try:
        url = (
            "https://www.googleapis.com/youtube/v3/channels"
            f"?part=id&forHandle={ref[1:]}&key={_api_key()}"
        )
        items = requests.get(url, timeout=_TIMEOUT).json().get("items") or []
        if items:
            cid = items[0]["id"]
            cache.set(ck, cid, _CHANNEL_ID_TTL)
            return cid
    except Exception as e:
        logger.warning("YouTube: failed to resolve handle %s: %s", ref, e)
    return None


def _uploads_playlist(channel_id):
    try:
        url = (
            "https://www.googleapis.com/youtube/v3/channels"
            f"?part=contentDetails&id={channel_id}&key={_api_key()}"
        )
        items = requests.get(url, timeout=_TIMEOUT).json().get("items") or []
        if items:
            return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        logger.warning("YouTube: failed to get uploads playlist for %s: %s", channel_id, e)
    return None


def _latest_from_channel(channel):
    cid = _resolve_channel_id(channel.youtube_channel_id)
    if not cid:
        return []
    playlist = _uploads_playlist(cid)
    if not playlist:
        return []
    try:
        url = (
            "https://www.googleapis.com/youtube/v3/playlistItems"
            f"?part=snippet&playlistId={playlist}&maxResults={_PER_CHANNEL}&key={_api_key()}"
        )
        out = []
        for item in requests.get(url, timeout=_TIMEOUT).json().get("items", []):
            sn = item.get("snippet", {})
            vid = sn.get("resourceId", {}).get("videoId")
            if not vid:
                continue
            thumbs = sn.get("thumbnails", {})
            thumb = (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url", "")
            out.append({
                "video_id": vid,
                "title": sn.get("title", ""),
                "thumbnail": thumb,
                "channel_name": channel.name,
                "published_at": sn.get("publishedAt", ""),
                "published_dt": parse_datetime(sn.get("publishedAt", "")),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        return out
    except Exception as e:
        logger.warning("YouTube: failed to fetch videos for %s: %s", channel.name, e)
    return []


def get_latest_videos(limit=5):
    """Latest uploads across active tracked channels, newest first (cached)."""
    if not _api_key():
        return []
    cached = cache.get(_CACHE_KEY)
    if cached is None:
        from .models import TrackedChannel
        videos = []
        for ch in TrackedChannel.objects.filter(is_active=True):
            videos.extend(_latest_from_channel(ch))
        videos.sort(key=lambda v: v["published_at"], reverse=True)
        cache.set(_CACHE_KEY, videos, _CACHE_TTL)
        cached = videos
    return cached[:limit]
