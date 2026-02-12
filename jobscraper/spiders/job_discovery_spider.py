import scrapy
import re
import json
from jobscraper.items import JobCandidate
from w3lib.html import remove_tags

class JobDiscoverySpider(scrapy.Spider):
    name = "job_discovery"
    # start_urls = ["https://www.comeet.com/jobs/arpeely/57.001"]
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
        script_text = response.xpath('//script[contains(text(), "COMPANY_POSITIONS_DATA")]/text()').get()
        if script_text:
            yield from self.script_extract(response, script_text, "COMPANY_POSITIONS_DATA")
        else:
            for job in self.html_extract(response):
                yield job
      
    def parse_job_page(self, response):
        """
        Parse the description from the position page.
        Happen on a followup of a job link - when the job is in it's own page.
        """
        job = response.meta["job"]
        script_text = response.xpath('//script[contains(text(), "POSITION_DATA")]/text()').get()
        structured_desc = self.json_ld_description_extract(response)
        
        if script_text:
            pos_details = self.js_var_extract(script_text, "POSITION_DATA")
            details_list = json.loads(pos_details).get("custom_fields", {}).get("details", [])
            full_description = [item.get("value", "") for item in details_list if item.get("value")]
            combined_description = "\n\n".join(full_description)
            job["description"] = self.clean_description(remove_tags(combined_description))
            job["resolved_via"] = "js"
        elif structured_desc:
            job["description"] = self.clean_description(remove_tags(structured_desc))
            job["resolved_via"] = "json-ld"
        else:
            for s in response.xpath("//script | //style"): 
                s.drop()

            description = response.css(
                ".page-content, main, article, .job-description, .description"
            ).xpath("string(.)").get()

            # self.logger.error(description)
            job["description"] = self.clean_description(description)
            job["resolved_via"] = "navigate"
        
        yield job

    def json_ld_description_extract(self, response):
        json_ld_data = response.xpath('//script[@type="application/ld+json"]/text()').getall()
    
        structured_desc = None
        for data in json_ld_data:
            try:
                parsed = json.loads(data)
                # Sometimes it's a list, sometimes a single object
                if isinstance(parsed, list):
                    parsed = parsed[0]

                # Check if this specific JSON is a "JobPosting"
                if parsed.get("@type") == "JobPosting":
                    structured_desc = parsed.get("description")
                    break
            except (json.JSONDecodeError, KeyError):
                continue
        return structured_desc

    def script_extract(self, response, script_text, var_name):
        # 1. Find the script tag containing COMPANY_POSITIONS_DATA
        # We look for the text of any script that mentions our variable
        # 2. Use Regex to capture everything between the '=' and the ';'
        # This looks for COMPANY_POSITIONS_DATA followed by any whitespace, =, whitespace, 
        # and then captures the array []
        json_string = self.js_var_extract(script_text, var_name)
        if json_string:
            try:
                positions = json.loads(json_string)
                for pos in positions:
                    # Check our role keywords against the 'name' field
                    if self.ROLE_KEYWORDS.search(pos.get('name', '')):
                        job_url = pos.get('url_active_page')
                        job = JobCandidate(
                            company=self._company_from_url(response.url),
                            title=pos.get('name'),
                            href=job_url,
                            source_url=response.url,
                        )
                        yield response.follow(
                            job_url, 
                            callback=self.parse_job_page, 
                            meta={'job': dict(job)} # Pass the JSON data we already have
                        )
            except json.JSONDecodeError:
                self.logger.error("Failed to parse JSON from script")
    
    def js_var_extract(self, script_text, var_name):
        pattern = rf'{var_name}\s*=\s*(\[.*?\]|\{{.*?\}});'
        match = re.search(pattern, script_text, re.DOTALL)

        if match:
            json_string = match.group(1)
            return json_string
        return None

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
    
    def _company_from_url(self, url):
        # trivial placeholder, you already have this in CSV
        return url.split("//")[1].split("/")[0]