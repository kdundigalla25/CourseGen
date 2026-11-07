"""Bounded manual public-source collection, with verified cache and robots checks."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = 'UNC-Course-Planner/0.1 (manual source import)'
MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class Receipt:
    content: bytes
    url: str
    retrieved_at: datetime
    content_sha256: str


def atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as file:
            temporary = Path(file.name)
            file.write(content); file.flush(); os.fsync(file.fileno())
        os.replace(temporary,path)
    finally:
        if temporary: temporary.unlink(missing_ok=True)


class PublicCollector:
    def __init__(self, cache: Path, *, offline=False, refresh=False, client=None, pause=time.sleep):
        self.cache, self.offline, self.refresh = cache, offline, refresh
        self.client = client or httpx.Client(timeout=25,follow_redirects=False,headers={'User-Agent':USER_AGENT})
        self.pause = pause
        self.policies = {}
        self.last_request = None
        self.minimum_interval = 1

    def close(self):
        self.client.close()

    def request(self, url, *, method='GET', data=None, key=None, headers=None, fresh=False):
        parsed = urlsplit(url)
        allowed = parsed.scheme == 'https' and not parsed.query and not parsed.fragment and (
            parsed.netloc == 'catalog.unc.edu' and re.fullmatch(r'/courses/[a-z]{2,5}/|/robots.txt',parsed.path)
            or parsed.netloc == 'reports.unc.edu' and parsed.path in ('/class-search/','/robots.txt'))
        if not allowed or method not in ('GET','POST') or (method=='POST' and parsed.path!='/class-search/'):
            raise ValueError('Only canonical catalog subjects and the normal public class-search form are supported')
        identity = hashlib.sha256(f'{method}:{url}:{key or ""}'.encode()).hexdigest()
        manifest = self.cache / f'{identity}.json'
        if (self.offline or (not self.refresh and not fresh)) and manifest.exists():
            meta = json.loads(manifest.read_text(encoding='utf-8'))
            digest = meta['content_sha256']
            if not re.fullmatch('[a-f0-9]{64}',digest): raise ValueError('Invalid cached source digest')
            path = self.cache / f'{digest}.html'
            if path.stat().st_size > MAX_BYTES: raise ValueError('Cached source exceeds size limit')
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest or meta['url'] != url:
                raise ValueError('Cached source failed integrity validation')
            return Receipt(content,url,datetime.fromisoformat(meta['retrieved_at']),digest)
        if self.offline: raise ValueError('No cached source exists for this request; offline mode never downloads')
        if parsed.path!='/robots.txt': self.check_robots(f'{parsed.scheme}://{parsed.netloc}',url)
        for attempt in range(3):
            if self.last_request is not None:
                self.pause(max(0,self.minimum_interval-(time.monotonic()-self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.client.stream(method,url,data=data,headers=headers) as response:
                    if parsed.path=='/robots.txt' and response.status_code==404:
                        return Receipt(b'',url,datetime.now(timezone.utc),hashlib.sha256(b'').hexdigest())
                    if response.status_code==429:
                        raise ValueError('Source rate-limited the request; stop and retry manually later')
                    if response.status_code>=500 and attempt<2:
                        self.pause(2**attempt); continue
                    response.raise_for_status()  # Redirects and auth failures stop; no bypass.
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content)>MAX_BYTES: raise ValueError('Source exceeds 10 MB')
                    break
            except httpx.TransportError:
                if attempt==2: raise
                self.pause(2**attempt)
        receipt = Receipt(bytes(content),url,datetime.now(timezone.utc),hashlib.sha256(content).hexdigest())
        # Failed requests never replace a successful manifest. Raw responses are content addressed.
        atomic_write(self.cache / f'{receipt.content_sha256}.html',receipt.content)
        atomic_write(manifest,json.dumps(dict(url=url,retrieved_at=receipt.retrieved_at.isoformat(),content_sha256=receipt.content_sha256)).encode())
        return receipt

    def check_robots(self, origin, url):
        if origin not in self.policies:
            receipt = self.request(origin+'/robots.txt')
            parser = RobotFileParser()
            parser.parse(receipt.content.decode('utf-8').splitlines())
            self.minimum_interval = max(self.minimum_interval,parser.crawl_delay(USER_AGENT) or 0)
            rate = parser.request_rate(USER_AGENT)
            if rate: self.minimum_interval = max(self.minimum_interval,rate.seconds/rate.requests)
            self.policies[origin] = parser
        if not self.policies[origin].can_fetch(USER_AGENT,url):
            raise ValueError('Source robots guidance disallows this URL; collection stopped')
