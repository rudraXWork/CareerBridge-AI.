import ipaddress
import json
import os
import socket
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from backend.config import api_key

USER_AGENT = 'CareerBridgeAIStudentProject/0.1'


class ServiceError(Exception):
    pass


def request_json(method, url, provider, **kwargs):
    try:
        response = httpx.request(method, url, timeout=35, **kwargs)
        if response.status_code == 202:
            raise ServiceError(f'{provider} is still processing. Try again later.')
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        # Do not expose URLs that contain provider API keys.
        raise ServiceError(f'{provider} returned HTTP {exc.response.status_code}. Check API access and quota.') from exc
    except (httpx.RequestError, ValueError) as exc:
        raise ServiceError(f'{provider} could not return a valid response. Try again later.') from exc


def search_web(query, limit=5):
    key = api_key('TAVILY_API_KEY')
    if not key:
        raise ServiceError('Add TAVILY_API_KEY for live discovery, or provide a job description/person directly.')
    data = request_json('POST', 'https://api.tavily.com/search', 'Tavily',
                        headers={'Authorization': f'Bearer {key}'},
                        json={'query': query, 'max_results': limit, 'search_depth': 'basic',
                              'include_answer': False, 'include_raw_content': False})
    return data.get('results', [])


def validate_public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ServiceError('Use a public HTTP or HTTPS URL without credentials.')
    try:
        if parts.port not in (None, 80, 443):
            raise ServiceError('Only standard public web ports are supported.')
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ServiceError('Local and private network URLs are not supported.')
    except (socket.gaierror, ValueError) as exc:
        raise ServiceError('Could not resolve this public URL.') from exc
    return parts


def public_get(url):
    with httpx.Client(timeout=15, headers={'User-Agent': USER_AGENT}, trust_env=False) as client:
        for _ in range(4):
            validate_public_url(url)
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ServiceError('Public page exceeds the 2 MB fetch limit.')
                    chunks.append(chunk)
                return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace'), url
    raise ServiceError('This URL redirected too many times.')


def check_robots(url):
    parts = validate_public_url(url)
    robots_url = f'{parts.scheme}://{parts.netloc}/robots.txt'
    parser = RobotFileParser()
    try:
        text, _ = public_get(robots_url)
        parser.parse(text.splitlines())
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return
        raise ServiceError('This site does not allow access to its crawling rules.') from exc
    except httpx.RequestError as exc:
        raise ServiceError('Could not check this site’s crawling rules; paste the description instead.') from exc
    if not parser.can_fetch(USER_AGENT, url):
        raise ServiceError('This site disallows automated access to that page. Paste its text instead.')


def browser_html(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT, service_workers='block')

            def route_request(route):
                try:
                    validate_public_url(route.request.url)
                    if route.request.resource_type in ('image', 'media', 'font'):
                        route.abort()
                    else:
                        if route.request.is_navigation_request():
                            check_robots(route.request.url)
                        route.continue_()
                except ServiceError:
                    route.abort()

            page.route('**/*', route_request)
            page.goto(url, wait_until='domcontentloaded', timeout=20000)
            page.wait_for_selector('body', timeout=5000)
            return page.content()
        finally:
            browser.close()


def fetch_page(url):
    try:
        check_robots(url)
        html, final_url = public_get(url)
        if final_url != url:
            check_robots(final_url)
        soup = BeautifulSoup(html, 'html.parser')
        if len(page_text(soup).split()) < 30 and os.getenv('USE_PLAYWRIGHT', '').lower() == 'true':
            try:
                soup = BeautifulSoup(browser_html(final_url), 'html.parser')
            except Exception as exc:
                raise ServiceError('Browser fallback could not read this public page. Paste the text instead.') from exc
        return soup, final_url
    except httpx.HTTPStatusError as exc:
        raise ServiceError(f'Public page returned HTTP {exc.response.status_code}. Paste its text instead.') from exc
    except httpx.RequestError as exc:
        raise ServiceError('Public page could not be fetched. Paste its text instead.') from exc


def page_text(soup):
    copy = BeautifulSoup(str(soup), 'html.parser')
    for node in copy(['script', 'style', 'nav', 'footer', 'header']):
        node.decompose()
    main = copy.find('main') or copy.find('article') or copy
    return main.get_text('\n', strip=True)[:50_000]


def structured_items(soup, kind):
    def walk(item):
        if isinstance(item, list):
            for value in item:
                yield from walk(value)
        elif isinstance(item, dict):
            types = item.get('@type', [])
            if kind in (types if isinstance(types, list) else [types]):
                yield item
            for value in item.values():
                if isinstance(value, (dict, list)):
                    yield from walk(value)

    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            yield from walk(json.loads(tag.string or tag.get_text()))
        except (ValueError, TypeError):
            continue
