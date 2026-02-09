import scrapy
import re
from jobscraper.items import JobCandidate

class JobDiscoverySpider(scrapy.Spider):
    name = "job_discovery"

    # Seed URLs = your CSV careers pages
    start_urls = [
        "https://dreamgroup.com/careers/",
        # many more
    ]

    ROLE_KEYWORDS = re.compile(
        r"\b(devops|mlops|sre)\b",
        re.IGNORECASE
    )

    NOISE_KEYWORDS = re.compile(
        r"(privacy|terms|about|contact|blog|login)",
        re.IGNORECASE
    )
    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse)
    
    def parse(self, response):
        """
        Phase A:
        - Iterate over clickable / visible text nodes
        - Identify job-like titles
        - Emit candidate job items
        """

        # We deliberately over-collect and filter in code
        for el in response.css("a, button, div, li"):
            text = el.xpath("normalize-space(.)").get()
            if not text:
                continue

            # Heuristic filters (cheap + deterministic)
            if len(text) < 5 or len(text) > 80:
                continue
            if self.NOISE_KEYWORDS.search(text):
                continue
            if not self.ROLE_KEYWORDS.search(text):
                continue

            href = el.attrib.get("href")

            yield JobCandidate(
                company=self._company_from_url(response.url),
                title=text,
                href=response.urljoin(href) if href else None,
                source_url=response.
                url,
            )

    def _company_from_url(self, url):
        # trivial placeholder, you already have this in CSV
        return url.split("//")[1].split("/")[0]