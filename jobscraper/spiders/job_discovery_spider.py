import scrapy
import re
import json
from jobscraper.items import JobCandidate

class JobDiscoverySpider(scrapy.Spider):
    name = "job_discovery"
    # start_urls = ["https://www.comeet.com/jobs/4Manalytics/B6.00F"]
    ROLE_KEYWORDS = re.compile(
    r"\b(devops|mlops)\s+(engineer)\b|\bSRE\b",
    re.IGNORECASE
)

    NOISE_KEYWORDS = re.compile(
        r"(privacy|terms|about|contact|blog|login)",
        re.IGNORECASE
    )

    def __init__(self, urls_file=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = []

        if urls_file:
            with open(urls_file, "r", encoding="utf8") as f:
                data = json.load(f)
                for item in data:
                    url = item.get("Careers URL")
                    if url:
                        self.start_urls.append(url)

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse)
    
    def parse(self, response):
        for job in self.html_extract(response):
            yield job

    def html_extract(self, response):
        # We deliberately over-collect and filter in code
        for el in response.css("a[href], button, div, li"):
            text = self.parse_text(el.xpath("normalize-space(.)").get())
            if not text:
                continue

            href = self.parse_href(response, el.attrib.get("href"))
            if not href:
                continue

            job = JobCandidate(
                company=self._company_from_url(response.url),
                title=text,
                href=href,
                source_url=response.url,
            )
            yield response.follow(href, callback=self.parse_job_page, meta={"job": dict(job)})
    
    def parse_text(self, text):
            if not text:
                return None
            # Heuristic filters (cheap + deterministic)
            if len(text) < 5 or len(text) > 80:
                return None
            if self.NOISE_KEYWORDS.search(text):
                return None
            if not self.ROLE_KEYWORDS.search(text):
                return None
            return text
    
    # Check if link is not just the same link
    def parse_href(self, response, href):
        if not href:
            return None
        parsed_href = response.urljoin(href)
        if parsed_href == response.url:
            return None
        return parsed_href

    def clean_description(self, description):
        cleaned_desc = re.sub(r'\s+', ' ', description).strip()
        cleaned_desc = re.sub(r'[\u200b\u200c\u200d]', '', cleaned_desc)
        return cleaned_desc

    def parse_job_page(self, response):
        """
        Case 1: Jobs has its own page
        Extract description from HTML
        """
        job = response.meta["job"]

        for s in response.xpath("//script | //style"): 
            s.drop()

        description = response.css(
            ".page-content, main, article, .job-description, .description"
        ).xpath("string(.)").get()

        # self.logger.error(description)
        description = self.clean_description(description)
        
        yield {
            **job,
            "description": description,
            "resolved_via": "navigate"
        }

    def _company_from_url(self, url):
        # trivial placeholder, you already have this in CSV
        return url.split("//")[1].split("/")[0]