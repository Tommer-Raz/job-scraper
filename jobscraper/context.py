from OpenSSL import SSL
from scrapy.core.downloader.contextfactory import ScrapyClientContextFactory


class CustomContextFactory(ScrapyClientContextFactory):
    """
    Custom context factory that allows SSL negotiation.
    """
    def getCertificateOptions(self):
        options = super(CustomContextFactory, self).getCertificateOptions()
        # This is the "Ignore" switch
        options.verify = False 
        # This allows older TLS versions (fixes 'packet length too long')
        options.method = SSL.SSLv23_METHOD 
        return options