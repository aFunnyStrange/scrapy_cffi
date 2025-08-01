import asyncio, re
from urllib.parse import urlparse
from curl_cffi import requests
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..models.api import SettingsInfo

class RobotsTxtRules:
    def __init__(self, rules=None, fallback=False):
        self.rules = rules or []
        self.fallback = fallback

    def is_allowed(self, url: str) -> bool:
        parsed_url = urlparse(url)
        path = parsed_url.path or "/"

        matched_rule = None
        matched_length = -1

        for rule_type, rule_path in self.rules:
            if path.startswith(rule_path):
                if len(rule_path) > matched_length:
                    matched_length = len(rule_path)
                    matched_rule = rule_type
        return matched_rule != "disallow"

def parse_robots_txt(text: str, user_agent: str = "*") -> RobotsTxtRules:
    lines = text.splitlines()
    agent_blocks = {}
    current_agents = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(r"(?i)^(user-agent|allow|disallow):\s*(.+)$", line)
        if not match:
            continue

        key, value = match.group(1).lower(), match.group(2).strip()

        if key == "user-agent":
            agent = value.lower()
            current_agents = [agent]
            if agent not in agent_blocks:
                agent_blocks[agent] = []
        elif key in ("allow", "disallow"):
            for agent in current_agents:
                agent_blocks.setdefault(agent, []).append((key, value))

    ua = user_agent.lower()
    matched_agents = [agent for agent in agent_blocks if agent in ua]
    if matched_agents:
        rules = []
        for agent in matched_agents:
            rules.extend(agent_blocks[agent])
        return RobotsTxtRules(rules)
    elif "*" in agent_blocks:
        return RobotsTxtRules(agent_blocks["*"])
    else:
        return RobotsTxtRules([])

class RobotsManager:
    def __init__(self, settings: "SettingsInfo"):
        self.settings = settings
        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        self._rules_cache = {}
        self._lock = asyncio.Lock()
        self._session = requests.AsyncSession()

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(settings=crawler.settings)

    async def load_rules_for_hosts(self, robot_urls):
        tasks = []
        async with self._lock:
            for url in robot_urls:
                domain = urlparse(url).netloc
                if domain not in self._rules_cache:
                    tasks.append(self._load_single(url, domain))
        await asyncio.gather(*tasks)

    async def _load_single(self, url, domain):
        rules = RobotsTxtRules([], fallback=True)
        try:
            resp = await self._session.get(url, headers={
                "sec-ch-prefers-color-scheme": "light",
                "sec-ch-ua-mobile": "?0",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "user-agent": self.settings.USER_AGENT
            }, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                rules = parse_robots_txt(text, self.settings.USER_AGENT)
                if not rules.rules:
                    self.logger.info(f"robots.txt from {url} has no rules, allowing all.")
                    rules = RobotsTxtRules([], fallback=True)
            elif resp.status_code == 404:
                self.logger.debug(f"robots.txt not found on {url}, allowing all.")
            else:
                self.logger.warning(f"robots.txt load failed from {url}, status: {resp.status_code}")
        except Exception as e:
            self.logger.warning(f"Error fetching robots.txt from {url}, disallowing all. -> {e}")
            rules = RobotsTxtRules([("disallow", "/")], fallback=False)

        async with self._lock:
            self._rules_cache[domain] = rules

    def is_allowed(self, url: str) -> bool:
        domain = urlparse(url).netloc
        rules: RobotsTxtRules = self._rules_cache.get(domain)
        return rules.is_allowed(url) if rules else True
