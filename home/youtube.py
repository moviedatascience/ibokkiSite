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
_CHANNEL_ID_TTL = 86400    # 1 day for resolved @handle/name -> UC id
_PER_CHANNEL = 15          # fetched per channel (1 API call); home shows newest 5, /videos shows all
_TIMEOUT = 8


def _api_key():
    return getattr(settings, "YOUTUBE_API_KEY", None)


def clear_cache():
    """Drop the aggregated video cache (called when tracked channels change)."""
    cache.delete(_CACHE_KEY)


def _resolve_channel_id(ref):
    """Resolve a UC id, @handle, or channel name to a UC... channel id (cached).

    Tries the cheap forHandle lookup first, then falls back to search so a
    slightly-off handle or a plain channel name still resolves.
    """
    if not ref:
        return None
    ref = ref.strip()
    # Already a channel id.
    if ref.startswith("UC") and len(ref) >= 20:
        return ref
    ck = f"yt_channel_id:{ref}"
    cached = cache.get(ck)
    if cached:
        return cached

    cid = None
    handle = ref[1:] if ref.startswith("@") else ref
    # 1) Official handle lookup (1 unit).
    try:
        url = (
            "https://www.googleapis.com/youtube/v3/channels"
            f"?part=id&forHandle={handle}&key={_api_key()}"
        )
        items = requests.get(url, timeout=_TIMEOUT).json().get("items") or []
        if items:
            cid = items[0]["id"]
    except Exception as e:
        logger.warning("YouTube: forHandle failed for %s: %s", ref, e)
    # 2) Fallback: search by name/handle (100 units, but cached for a day).
    if not cid:
        try:
            url = (
                "https://www.googleapis.com/youtube/v3/search"
                f"?part=id&type=channel&maxResults=1&q={handle}&key={_api_key()}"
            )
            items = requests.get(url, timeout=_TIMEOUT).json().get("items") or []
            if items:
                cid = items[0]["id"]["channelId"]
        except Exception as e:
            logger.warning("YouTube: search fallback failed for %s: %s", ref, e)

    if cid:
        cache.set(ck, cid, _CHANNEL_ID_TTL)
    else:
        logger.warning("YouTube: could not resolve channel reference %r", ref)
    return cid


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
    """Uploads across active tracked channels, newest first (cached).

    Pass limit=None to get the full aggregated pool (used by the /videos page).
    """
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
    return cached if limit is None else cached[:limit]
