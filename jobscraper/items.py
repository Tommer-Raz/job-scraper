# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class JobCandidate(scrapy.Item):
    company = scrapy.Field()
    title = scrapy.Field()
    href = scrapy.Field()
    source_url = scrapy.Field()

    # Phase B fields
    description = scrapy.Field()
    resolved_via = scrapy.Field()
