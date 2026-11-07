import base64
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}

WIKI_HEADERS = {
    "User-Agent": "OnnoBotAI/1.0 (https://github.com/onno-bot; contact@onno.bot)",
}


def fetch_url(url: str, timeout: int = 15) -> str:
    """Fetch webpage content via HTTP GET and strip HTML tags for clean LLM reading."""
    try:
        # If Bing redirect link, extract underlying target URL
        if "bing.com/news/apiclick.aspx" in url and "url=" in url:
            m = re.search(r"url=([^&]+)", url)
            if m:
                url = urllib.parse.unquote(m.group(1))

        with httpx.Client(follow_redirects=True, timeout=timeout, headers=HEADERS) as client:
            resp = client.get(url)
            resp.raise_for_status()
            text = resp.text

            # Clean HTML tags for readable LLM consumption
            if "<html" in text.lower():
                text = re.sub(r"<script.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<nav.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<header.*?</header>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<footer.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()

            if len(text) > 4000:
                text = text[:4000] + "\n... (truncated)"
            return text
    except Exception as e:
        return f"Error fetching URL: {str(e)}"


def _decode_bing_u(u_val: str) -> str:
    """Decode base64 encoded URL inside Bing search click redirects."""
    clean_u = u_val
    if clean_u.startswith("a1"):
        clean_u = clean_u[2:]
    clean_u = clean_u.replace("-", "+").replace("_", "/")
    pad = len(clean_u) % 4
    if pad:
        clean_u += "=" * (4 - pad)
    try:
        decoded = base64.b64decode(clean_u).decode("utf-8", errors="ignore")
        if decoded.startswith("http"):
            return decoded
    except Exception:
        pass
    return ""


def search_bing_web(query: str, max_results: int = 5) -> list[dict]:
    """Search Bing Web HTML and parse organic results with real target URLs and snippets."""
    queries = [query]
    cleaned = re.sub(
        r"^(bagaimana\s+cara(nya)?|cara|tutorial|panduan|tips|langkah-langkah)\s+",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"^(siapa|apa|kenapa|mengapa|dimana|kapan|apakah|siapakah)\s+(itu\s+)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    if cleaned and cleaned.lower() != query.lower():
        queries.insert(0, cleaned)

    results = []
    seen = set()

    for q in queries:
        if len(results) >= max_results:
            break
        try:
            encoded = urllib.parse.quote(q)
            url = f"https://www.bing.com/search?q={encoded}"
            with httpx.Client(follow_redirects=True, timeout=8.0, headers=HEADERS) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    blocks = re.findall(
                        r'<li class="b_algo".*?<h2><a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a></h2>.*?<p[^>]*>(.*?)</p>',
                        resp.text,
                        re.DOTALL,
                    )
                    if not blocks:
                        items = re.findall(
                            r'<h2[^>]*><a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a></h2>',
                            resp.text,
                            re.DOTALL,
                        )
                        blocks = [(href, title, "") for href, title in items]

                    for href, title, desc in blocks:
                        href = href.replace("&amp;", "&")
                        real_url = href
                        m = re.search(r"[?&]u=([^&]+)", href)
                        if m:
                            decoded = _decode_bing_u(m.group(1))
                            if decoded:
                                real_url = decoded

                        clean_title = re.sub(r"<[^>]+>", "", title).strip()
                        clean_desc = re.sub(r"<[^>]+>", "", desc).strip()
                        if real_url.startswith("http") and "bing.com" not in real_url and clean_title:
                            if real_url not in seen:
                                seen.add(real_url)
                                results.append({
                                    "title": clean_title,
                                    "url": real_url,
                                    "snippet": clean_desc,
                                    "source": "Web",
                                })
                                if len(results) >= max_results:
                                    break
        except Exception:
            pass
    return results


def search_news(query: str, max_results: int = 5) -> list[dict]:
    """Search real-time news via unblocked Bing News and Google News RSS feeds."""
    results = []
    encoded = urllib.parse.quote(query)

    # 1. Bing News RSS
    try:
        bnews_url = f"https://www.bing.com/news/search?format=rss&q={encoded}"
        with httpx.Client(follow_redirects=True, timeout=8.0, headers=HEADERS) as client:
            resp = client.get(bnews_url)
            if resp.status_code == 200 and "<rss" in resp.text:
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item"):
                    title = item.findtext("title") or ""
                    link = item.findtext("link") or ""
                    desc = item.findtext("description") or ""
                    pub = item.findtext("pubDate") or ""
                    if "url=" in link:
                        m = re.search(r"url=([^&]+)", link)
                        if m:
                            link = urllib.parse.unquote(m.group(1))

                    if title:
                        clean_t = re.sub(r"<[^>]+>", "", title).strip()
                        clean_d = re.sub(r"<[^>]+>", "", desc).strip()
                        results.append({
                            "title": clean_t,
                            "url": link,
                            "snippet": clean_d,
                            "pub_date": pub,
                            "source": "Bing News",
                        })
                        if len(results) >= max_results:
                            break
    except Exception:
        pass

    # 2. Google News RSS
    if len(results) < max_results:
        for hl, gl, ceid in [("id", "ID", "ID:id"), ("en-US", "US", "US:en")]:
            if len(results) >= max_results:
                break
            try:
                gurl = f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid={ceid}"
                with httpx.Client(follow_redirects=True, timeout=8.0, headers=HEADERS) as client:
                    resp = client.get(gurl)
                    if resp.status_code == 200 and "<rss" in resp.text:
                        root = ET.fromstring(resp.text)
                        for item in root.findall(".//item"):
                            title = item.findtext("title") or ""
                            link = item.findtext("link") or ""
                            source = item.findtext("source") or ""
                            pub = item.findtext("pubDate") or ""
                            if title:
                                clean_t = re.sub(r"<[^>]+>", "", title).strip()
                                results.append({
                                    "title": clean_t,
                                    "url": link,
                                    "snippet": f"Sumber: {source}",
                                    "pub_date": pub,
                                    "source": "Google News",
                                })
                                if len(results) >= max_results:
                                    break
            except Exception:
                pass

    return results


def search_wikipedia(query: str, max_results: int = 3) -> list[dict]:
    """Search Indonesian and English Wikipedia for encyclopedic facts and definitions."""
    results = []
    # Clean leading question/stop words
    clean_q = re.sub(
        r"^(siapa|apa|bagaimana|mengapa|dimana|kapan|kenapa|apakah|siapakah)\s+(itu\s+)?",
        "",
        query,
        flags=re.IGNORECASE,
    )
    clean_q = re.sub(
        r"^(cara|panduan|tutorial|pengertian|definisi|sejarah|biografi|penemu|pencipta)\s+",
        "",
        clean_q,
        flags=re.IGNORECASE,
    ).strip()
    clean_q = clean_q or query

    encoded = urllib.parse.quote(clean_q)
    for lang in ["id", "en"]:
        if len(results) >= max_results:
            break
        try:
            wurl = (
                f"https://{lang}.wikipedia.org/w/api.php?"
                f"action=query&list=search&srsearch={encoded}&format=json"
            )
            with httpx.Client(timeout=6.0, headers=WIKI_HEADERS) as client:
                resp = client.get(wurl)
                if resp.status_code == 200:
                    data = resp.json()
                    for s in data.get("query", {}).get("search", [])[:max_results]:
                        t = s.get("title", "")
                        snip = re.sub(r"<[^>]+>", "", s.get("snippet", "")).strip()
                        page_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(t)}"
                        results.append({
                            "title": f"{t} (Wikipedia {lang.upper()})",
                            "url": page_url,
                            "snippet": snip,
                            "source": f"Wikipedia {lang.upper()}",
                        })
                        if len(results) >= max_results:
                            break
        except Exception:
            pass
    return results


def search_developer_code(query: str, max_results: int = 3) -> list[dict]:
    """Search GitHub and HackerNews for technical repos, exploit PoCs, and developer solutions."""
    results = []
    encoded = urllib.parse.quote(query)

    # GitHub Repos
    try:
        gh_url = f"https://api.github.com/search/repositories?q={encoded}&per_page={max_results}"
        with httpx.Client(timeout=6.0, headers=HEADERS) as client:
            resp = client.get(gh_url)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", [])[:max_results]:
                    full_name = item.get("full_name", "")
                    html_url = item.get("html_url", "")
                    desc = item.get("description") or ""
                    stars = item.get("stargazers_count", 0)
                    results.append({
                        "title": f"{full_name} (⭐ {stars})",
                        "url": html_url,
                        "snippet": desc,
                        "source": "GitHub",
                    })
    except Exception:
        pass

    # HackerNews Algolia
    if len(results) < max_results:
        try:
            hn_url = f"https://hn.algolia.com/api/v1/search?query={encoded}&hitsPerPage={max_results}"
            with httpx.Client(timeout=6.0, headers=HEADERS) as client:
                resp = client.get(hn_url)
                if resp.status_code == 200:
                    data = resp.json()
                    for hit in data.get("hits", [])[:max_results]:
                        title = hit.get("title") or hit.get("story_title")
                        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                        if title:
                            results.append({
                                "title": title,
                                "url": url,
                                "snippet": f"Points: {hit.get('points', 0)} | Comments: {hit.get('num_comments', 0)}",
                                "source": "HackerNews",
                            })
        except Exception:
            pass

    return results


def search_via_openai_responses(query: str) -> str | None:
    """Delegate to OpenAI Responses API with web_search if OPENAI_API_KEY is configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            tools=[{"type": "web_search"}],
            input=query,
        )
        return resp.output_text
    except Exception:
        return None


def web_search(query: str, max_results: int = 5) -> str:
    """Universal Web Search supporting News, Technical, Documentation, CVEs, and General Knowledge."""
    # 1. Check if user configured OpenAI Responses API with web_search
    ai_answer = search_via_openai_responses(query)
    if ai_answer:
        return ai_answer

    q_lower = query.lower()
    all_hits = []
    seen_urls = set()

    # Determine intent
    is_news = any(w in q_lower for w in [
        "berita", "news", "hari ini", "terbaru", "today", "terkini",
        "update", "2024", "2025", "2026", "sidang", "pemilu", "harga", "bbm"
    ])
    is_knowledge = any(w in q_lower for w in [
        "siapa", "apa itu", "pengertian", "definisi", "sejarah", "who is", "what is", "biografi", "penemu"
    ])
    is_tech = any(w in q_lower for w in [
        "cve-", "exploit", "github", "poc", "repo", "library", "python", "docker", "linux",
        "tutorial", "install", "script", "command", "bash", "golang", "rust", "reverse"
    ])

    # 1. If explicit news intent, search news first
    if is_news:
        for item in search_news(query, max_results=max_results):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_hits.append(item)

    # 2. Knowledge/Encyclopedia intent (Wikipedia)
    if is_knowledge and len(all_hits) < max_results:
        for item in search_wikipedia(query, max_results=3):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_hits.append(item)

    # 3. Developer/Cybersecurity specialized search (GitHub, HackerNews)
    if is_tech and len(all_hits) < max_results:
        for item in search_developer_code(query, max_results=3):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_hits.append(item)

    # 4. General Bing Web search (handles any website, tutorial, docs, article)
    if len(all_hits) < max_results:
        for item in search_bing_web(query, max_results=max_results):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_hits.append(item)

    # 5. Fallback: if still empty, search news feeds as last resort
    if not all_hits:
        for item in search_news(query, max_results=max_results):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_hits.append(item)

    if not all_hits:
        return f"No search results found for query: {query}"

    # Format results cleanly for LLM
    output_lines = []
    for hit in all_hits[:max_results]:
        title = hit.get("title", "Untitled")
        url = hit.get("url", "")
        snip = hit.get("snippet", "")
        pub = hit.get("pub_date", "")
        src = hit.get("source", "Web")

        line = f"• {title}"
        if pub:
            line += f" ({pub})"
        if snip:
            line += f"\n  Snippet: {snip[:300]}"
        if url:
            line += f"\n  Link: {url}"
        output_lines.append(line)

    return "\n\n".join(output_lines)
