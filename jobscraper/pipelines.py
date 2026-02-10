# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from scrapy import Request


class JobResolutionPipeline:
    """
    Pipeline that:
    - Receives Phase A items
    - Schedules Phase B requests if needed
    """

    def process_item(self, item, spider):
        # Only act on Phase A spider output
        if spider.name != "job_discovery":
            return item

        # Case 1: job has its own page → schedule Phase B fetch
        if item.get("href"):
            spider.logger.warning(f"SCHEDULING {item['href']}")
            return Request(
                url=item["href"],
                callback=spider.parse_job_page,
                meta={"job": dict(item)},
                dont_filter=True,
            )

        # Case 2: inline job → pass through unchanged
        item["resolved_via"] = "inline"
        return item
