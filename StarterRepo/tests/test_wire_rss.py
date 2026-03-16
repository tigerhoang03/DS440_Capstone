from newssentinel.collectors.rss.wires import _discover_rss_links, _normalize_source_name


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
