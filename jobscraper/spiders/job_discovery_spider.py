import scrapy
import re
import json
from jobscraper.items import JobCandidate
from w3lib.html import remove_tags
from scrapy_playwright.page import PageMethod

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
        self.companies = []

        if urls_file:
            with open(urls_file, "r", encoding="utf8") as f:
                self.companies = json.load(f)

    async def start(self):
        for company in self.companies:
            job = JobCandidate(
                company = company.get("Company"),
                source_url = company.get("Careers URL")
            )
            yield scrapy.Request(company.get("Careers URL"), callback=self.parse, meta={"job": dict(job)})
        # job = JobCandidate(
        #         company = "zenity",
        #         source_url = "https://zenity.io/careers",
        #     )
        # yield scrapy.Request("https://zenity.io/careers", callback=self.parse, meta={"job": dict(job),})
    
    def parse(self, response):
        job = response.meta["job"]
        found_any = False
        script_text = self.js_var_extract(response, "COMPANY_POSITIONS_DATA")
        if script_text:
            for pos in self.script_extract(response, script_text, job):
                found_any = True
                yield pos 
        if not found_any:
            for pos in self.html_extract(response, job):
                found_any = True
                yield pos 
        # if not found_any and not response.meta.get("is_playwright"):
        #     self.logger.error("3")
        #     job['is_playwright'] = True

        #     yield scrapy.Request(
        #     url=response.url,
        #     callback=self.parse,
        #     meta={
        #         "job": job,
        #         "playwright": True, 
        #         "is_playwright": True, # Mark this so we don't loop forever
        #         "playwright_page_methods": [
        #             # Option A: Wait until the network goes quiet (Next.js is done fetching)
        #             # PageMethod("wait_for_load_state", "networkidle"),

        #             # Option B: Wait for ANY link in the careers section 
        #             # (Adjust the selector based on the container ID if known)
        #             PageMethod("wait_for_selector", "a[href*='job'], a[href*='career']"), 
        #         ],
        #     },
        #     dont_filter=True # Tell Scrapy: "Yes, I know I just visited this URL, do it anyway."
        # )
      
    def parse_job_page(self, response):
        """
        Parse the description from the position page.
        Happen on a followup of a job link - when the job is in it's own page.
        """
        job = response.meta["job"]       
        if job["resolved_via"] == "js":
            pos_details = self.js_var_extract(response, "POSITION_DATA")
            if pos_details:
                details_list = json.loads(pos_details).get("custom_fields", {}).get("details", [])
                full_description = [item.get("value", "") for item in details_list if item.get("value")]
                combined_description = "\n\n".join(full_description)
                job["description"] = self.clean_description(remove_tags(combined_description))
                job["resolved_via"] = "js"
        elif job["resolved_via"] == "html_extract":
            structured_desc = self.json_ld_description_extract(response)
            if structured_desc:
                job["description"] = self.clean_description(remove_tags(structured_desc))
                job["resolved_via"] = "json-ld"
            else:
                for s in response.xpath("//script | //style"): 
                    s.drop()

                description = response.css(
                    ".job-content, .page-content, main, article, .job-description, .description"
                ).xpath("string(.)").get()
                if not description or len(description.strip()) < 150:
                    description = response.xpath(
                        "//div[contains(., 'Requirements') or contains(., 'Responsibilities') "
                        "or contains(., 'Qualifications') or contains(., 'About the role')]"
                        "[last()]//string(.)").get()
                job["description"] = self.clean_description(description)
                job["resolved_via"] = "html_extract"

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

    def script_extract(self, response, script_text, job):
        try:
            positions = json.loads(script_text)
            for pos in positions:
                if self.ROLE_KEYWORDS.search(pos.get('name', '')):
                    job_url = pos.get('url_active_page')
                    job['title'] = pos.get('name')
                    job['href'] = pos.get('job_url')
                    job['resolved_via'] = 'js'
                    yield response.follow(
                        job_url, 
                        callback=self.parse_job_page, 
                        meta={'job': dict(job)} # Pass the JSON data we already have
                    )
        except json.JSONDecodeError:
            self.logger.error("Failed to parse JSON from script")
    
    def js_var_extract(self, response, var_name):
        xpath_pattern = rf'//script[contains(text(), "{var_name}")]/text()'
        script_text = response.xpath(xpath_pattern).get()
        if script_text:
            regex_pattern = rf'{var_name}\s*=\s*(\[.*?\]|\{{.*?\}});'
            match = re.search(regex_pattern, script_text, re.DOTALL)

            if match:
                json_string = match.group(1)
                return json_string
        return None

    def html_extract(self, response, job):
        # We deliberately over-collect and filter in code
        for el in response.css("a[href], button, div, li, span, h1, h2, h3, h4, h5, h6"):
            text = self.parse_text(el.xpath("normalize-space(.)").get())
            if not text:
                continue

            # href = self.parse_href(response, el.attrib.get("href"))
            href = self.parse_href(response, el.xpath(
            ".//@href | "                     # Link is the element itself
            "./ancestor::a/@href | "          # Link is a parent
            "./preceding-sibling::a[1]/@href | " # Link is a sibling (like Zenity!)
            "../following-sibling::a[1]/@href"  # Link is a sibling after
        ).get())
            if not href:
                continue
            job['title'] = text
            job['href'] = href
            job['resolved_via'] = 'html_extract'
            yield response.follow(href, 
                                  callback=self.parse_job_page, 
                                  meta={"job": dict(job),})
            # yield response.follow(href, 
            #                       callback=self.parse_job_page, 
            #                       meta={"job": dict(job),                
            #                             "playwright": job['is_playwright'], 
            #                             "playwright_page_methods": [
            #                                 PageMethod("wait_for_selector", "a[href*='job'], a[href*='career']"), 
            #                         ],})
    
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
        if not description:
            return None
        cleaned_desc = re.sub(r'\s+', ' ', description).strip()
        cleaned_desc = re.sub(r'[\u200b\u200c\u200d]', '', cleaned_desc)
        return cleaned_desc