from newssentinel.collectors.rss.wires import (
    _build_conditional_headers,
    _discover_rss_links,
    _normalize_source_name,
    _update_feed_http_cache,
)


def test_discover_rss_links_from_listing_page():
    html = """
    <html><body>
      <a href="/rss/technology.xml">Tech</a>
      <a href="https://www.prnewswire.com/rss/finance.rss">Finance</a>
      <a href="/about">About</a>
    </body></html>
    """
    links = _discover_rss_links(
        listing_url="https://www.prnewswire.com/rss/",
        html=html,
        max_links=10,
    )
    assert links == [
        "https://www.prnewswire.com/rss/technology.xml",
        "https://www.prnewswire.com/rss/finance.rss",
    ]


def test_source_name_normalization():
    assert _normalize_source_name("https://www.prnewswire.com/rss/foo.xml") == "prnewswire_rss"
    assert _normalize_source_name("https://www.globenewswire.com/rss/news.xml") == "globenewswire_rss"


def test_discover_rss_links_from_js_window_location():
    html = r"""
    <html><body>
      <script>
        javascript:window.location.href='\/rss\/news\u002Dreleases\u002Dlist.rss'
      </script>
    </body></html>
    """
    links = _discover_rss_links(
        listing_url="https://www.prnewswire.com/rss/",
        html=html,
        max_links=10,
    )
    assert links == ["https://www.prnewswire.com/rss/news-releases-list.rss"]


def test_discover_globenewswire_path_based_rss_links():
    html = """
    <html><body>
      <a href="/AtomFeed/orgclass/1/feedTitle/GlobeNewswire - News about Public Companies">ATOM</a>
      <a href="/JSWidgetFeed/orgclass/1/feedTitle/GlobeNewswire - News about Public Companies">Java Script</a>
      <a href="/RssFeed/orgclass/1/feedTitle/GlobeNewswire - News about Public Companies">RSS</a>
    </body></html>
    """
    links = _discover_rss_links(
        listing_url="https://www.globenewswire.com/rss/list",
        html=html,
        max_links=10,
    )
    assert links == [
        "https://www.globenewswire.com/AtomFeed/orgclass/1/feedTitle/GlobeNewswire - News about Public Companies",
        "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/GlobeNewswire - News about Public Companies",
    ]


def test_build_conditional_headers_from_cache():
    headers = _build_conditional_headers(
        {"etag": '"abc123"', "last_modified": "Mon, 01 Jan 2026 00:00:00 GMT"}
    )
    assert headers == {
        "If-None-Match": '"abc123"',
        "If-Modified-Since": "Mon, 01 Jan 2026 00:00:00 GMT",
    }


def test_update_feed_http_cache_writes_only_when_headers_present():
    cache: dict[str, dict[str, str]] = {}
    feed_url = "https://example.com/feed.xml"
    _update_feed_http_cache(cache=cache, feed_url=feed_url, response_headers={})
    assert feed_url not in cache

    _update_feed_http_cache(
        cache=cache,
        feed_url=feed_url,
        response_headers={
            "ETag": '"etag-1"',
            "Last-Modified": "Tue, 02 Jan 2026 00:00:00 GMT",
        },
    )
    assert cache[feed_url] == {
        "etag": '"etag-1"',
        "last_modified": "Tue, 02 Jan 2026 00:00:00 GMT",
    }
