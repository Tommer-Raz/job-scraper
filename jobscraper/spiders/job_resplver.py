import scrapy

class JobResolverSpider(scrapy.Spider):
    name = "job_resolver"
    
    def parse_job_page(self, response):
        """
        Case 1: Job has its own page
        Extract description from HTML
        """
        job = response.meta["job"]

        description = response.css(
            "main, article, .job-description, .description"
        ).xpath("string(.)").get()

        yield {
            **job,
            "description": description.strip() if description else None,
            "resolved_via": "navigate"
        }