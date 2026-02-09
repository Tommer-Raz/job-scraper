import scrapy

class JobResolverSpider(scrapy.Spider):
    name = "job_resolver"

    def start_requests(self):
        """
        Phase B input:
        - Items produced by Phase A
        - Typically passed via feed export, DB, or pipeline
        """

        for job in self.load_jobs():
            if job.get("href"):
                yield scrapy.Request(
                    job["href"],
                    callback=self.parse_job_page,
                    meta={"job": job}
                )
            else:
                # Inline job (no navigation)
                yield job

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

    def load_jobs(self):
        """
        Placeholder:
        - load Phase A output from JSON / DB / file
        """
        raise NotImplementedError