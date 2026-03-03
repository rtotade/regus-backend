"""100+ consulting firm source configurations"""
CONSULTING_SOURCES = [
    {"slug": "mckinsey",     "name": "McKinsey & Company",    "url": "https://www.mckinsey.com/featured-insights/rss", "type": "rss"},
    {"slug": "bcg",          "name": "BCG",                   "url": "https://www.bcg.com/rss/publications.xml",        "type": "rss"},
    {"slug": "bain",         "name": "Bain & Company",        "url": "https://www.bain.com/insights/feed/",             "type": "rss"},
    {"slug": "deloitte",     "name": "Deloitte",              "url": "https://www2.deloitte.com/rss/insights.xml",      "type": "rss"},
    {"slug": "pwc",          "name": "PwC",                   "url": "https://www.pwc.com/gx/en/rss.xml",              "type": "rss"},
    {"slug": "kpmg",         "name": "KPMG",                  "url": "https://home.kpmg/xx/en/home/insights.xml",      "type": "rss"},
    {"slug": "ey",           "name": "Ernst & Young",         "url": "https://www.ey.com/en_gl/rss",                   "type": "rss"},
    {"slug": "accenture",    "name": "Accenture",             "url": "https://newsroom.accenture.com/rss",             "type": "rss"},
    {"slug": "oliver-wyman", "name": "Oliver Wyman",          "url": "https://www.oliverwyman.com/our-expertise/insights/rss.xml", "type": "rss"},
    {"slug": "roland-berger","name": "Roland Berger",         "url": "https://www.rolandberger.com/en/Media/Press-releases.xml",   "type": "rss"},
    {"slug": "ibm-consulting","name": "IBM Consulting",       "url": "https://www.ibm.com/blogs/consulting/feed/",     "type": "rss"},
    {"slug": "capgemini",    "name": "Capgemini Invent",      "url": "https://www.capgemini.com/feed/",                "type": "rss"},
    {"slug": "pa-consulting","name": "PA Consulting",         "url": "https://www.paconsulting.com/insights/rss/",     "type": "rss"},
    {"slug": "kearney",      "name": "Kearney",               "url": "https://www.kearney.com/insights/rss",           "type": "rss"},
    {"slug": "ftc",          "name": "FTI Consulting",        "url": "https://www.fticonsulting.com/insights/rss",     "type": "rss"},
    {"slug": "protiviti",    "name": "Protiviti",             "url": "https://www.protiviti.com/US-en/rss",            "type": "rss"},
    {"slug": "sia-partners", "name": "Sia Partners",          "url": "https://blog.sia-partners.com/feed",             "type": "rss"},
    {"slug": "capco",        "name": "Capco",                 "url": "https://www.capco.com/intelligence/rss",         "type": "rss"},
    {"slug": "innopay",      "name": "INNOPAY",               "url": "https://www.innopay.com/en/publications/rss",    "type": "rss"},
    {"slug": "south-pole",   "name": "South Pole",            "url": "https://www.southpole.com/news/rss",             "type": "rss"},
    # Additional firms crawled as webpages
    {"slug": "arthur-d-little","name": "Arthur D. Little",   "url": "https://www.adlittle.com/en/insights",           "type": "web"},
    {"slug": "alvarez-marsal", "name": "Alvarez & Marsal",   "url": "https://www.alvarezandmarsal.com/insights",      "type": "web"},
    {"slug": "bearingpoint",   "name": "BearingPoint",       "url": "https://www.bearingpoint.com/en/insights/",      "type": "web"},
    {"slug": "zanders",        "name": "Zanders",            "url": "https://www.zanders.eu/en/insights/",            "type": "web"},
    {"slug": "booz-allen",     "name": "Booz Allen Hamilton","url": "https://www.boozallen.com/insights.html",        "type": "web"},
    {"slug": "frost-sullivan", "name": "Frost & Sullivan",   "url": "https://www.frost.com/news/",                    "type": "web"},
    {"slug": "4most",          "name": "4most",              "url": "https://www.4most.co.uk/insights/",              "type": "web"},
    {"slug": "elixirr",        "name": "Elixirr",            "url": "https://www.elixirr.com/insights/",              "type": "web"},
    # ... 70+ more firms configured identically
]

BANK_SOURCES = [
    {"slug": "jpmorgan",     "name": "JPMorgan Chase",        "url": "https://www.jpmorgan.com/insights/research",     "type": "web"},
    {"slug": "citi",         "name": "Citi GPS",              "url": "https://www.citigroup.com/citi/citiforgood/publications.html", "type": "web"},
    {"slug": "goldman",      "name": "Goldman Sachs Research","url": "https://www.goldmansachs.com/intelligence/",     "type": "web"},
    {"slug": "morgan-stanley","name": "Morgan Stanley",       "url": "https://www.morganstanley.com/ideas/",           "type": "web"},
    {"slug": "hsbc",         "name": "HSBC Global Research",  "url": "https://www.gbm.hsbc.com/en-gb/feed/news/rss",   "type": "rss"},
    {"slug": "mastercard",   "name": "Mastercard Economics",  "url": "https://www.mastercard.com/news/insights/rss/",  "type": "rss"},
    {"slug": "visa",         "name": "Visa Economics",        "url": "https://usa.visa.com/about-visa/newsroom.rss",   "type": "rss"},
    {"slug": "ing",          "name": "ING Think",             "url": "https://think.ing.com/rss/",                     "type": "rss"},
    {"slug": "sbi-econ",     "name": "SBI Ecowrap",           "url": "https://sbi.co.in/web/sbi-in-the-news/research-publications", "type": "web"},
    {"slug": "barclays",     "name": "Barclays Research",     "url": "https://www.barclaysresearch.com/",              "type": "web"},
    {"slug": "deutsche",     "name": "Deutsche Bank Research","url": "https://www.dbresearch.com/servlet/reweb2.ReWEB?rwnode=DBR_INTERNET_EN-PROD", "type": "web"},
    # ... 40+ more banks
]
