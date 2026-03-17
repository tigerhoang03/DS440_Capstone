from newssentinel.enrich.canonical import build_story_key, canonicalize_url, normalize_title


def test_canonicalize_url_removes_tracking_params():
    url = "https://Example.com/path/to/article/?utm_source=x&b=2&a=1#frag"
    got = canonicalize_url(url)
    assert got == "https://example.com/path/to/article?a=1&b=2"


def test_normalize_title():
    assert normalize_title("  Tesla, Inc. Beats Earnings! ") == "tesla inc beats earnings"


def test_story_key_ignores_tracking_noise():
    t = "NVIDIA Surges on AI Demand"
    u1 = "https://site.com/story?utm_source=abc&id=7"
    u2 = "https://site.com/story?id=7&utm_campaign=foo"
    assert build_story_key(t, u1) == build_story_key(t, u2)
