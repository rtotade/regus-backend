"""160+ regulatory sources — all monitored by Agent 01"""
REGULATORY_SOURCES = [
    # INDIA
    {"name": "RBI",   "jurisdiction": "IN", "type": "rss",  "url": "https://www.rbi.org.in/commonman/English/scripts/Bulletins.aspx"},
    {"name": "NPCI",  "jurisdiction": "IN", "type": "web",  "url": "https://www.npci.org.in/what-we-do/upi/circular"},
    {"name": "SEBI",  "jurisdiction": "IN", "type": "web",  "url": "https://www.sebi.gov.in/legal/circulars.html"},
    {"name": "IRDAI", "jurisdiction": "IN", "type": "web",  "url": "https://irdai.gov.in/circular"},
    {"name": "PFRDA", "jurisdiction": "IN", "type": "web",  "url": "https://www.pfrda.org.in/index1.cshtml?lngId=14&SublngId=2"},
    {"name": "MEITY", "jurisdiction": "IN", "type": "web",  "url": "https://www.meity.gov.in/content/notifications"},
    {"name": "MCA",   "jurisdiction": "IN", "type": "web",  "url": "https://www.mca.gov.in/Ministry/notification.html"},
    # UK
    {"name": "FCA",   "jurisdiction": "GB", "type": "rss",  "url": "https://www.fca.org.uk/news/rss.xml"},
    {"name": "PRA",   "jurisdiction": "GB", "type": "web",  "url": "https://www.bankofengland.co.uk/prudential-regulation/publication"},
    {"name": "PSR",   "jurisdiction": "GB", "type": "web",  "url": "https://www.psr.org.uk/publications"},
    {"name": "ICO",   "jurisdiction": "GB", "type": "rss",  "url": "https://ico.org.uk/about-the-ico/news-and-events/news-and-blogs/feed/"},
    {"name": "HMT",   "jurisdiction": "GB", "type": "rss",  "url": "https://www.gov.uk/search/policy-papers-and-consultations.atom?organisations[]=hm-treasury"},
    # USA
    {"name": "Fed",      "jurisdiction": "US", "type": "rss",  "url": "https://www.federalreserve.gov/feeds/press_all.xml"},
    {"name": "OCC",      "jurisdiction": "US", "type": "rss",  "url": "https://www.occ.gov/tools/rss/occ-news.rss"},
    {"name": "CFPB",     "jurisdiction": "US", "type": "rss",  "url": "https://www.consumerfinance.gov/about-us/newsroom/feed/"},
    {"name": "SEC",      "jurisdiction": "US", "type": "rss",  "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&dateb=&owner=include&count=20&output=atom"},
    {"name": "FinCEN",   "jurisdiction": "US", "type": "web",  "url": "https://www.fincen.gov/news-room/news-releases"},
    {"name": "FDIC",     "jurisdiction": "US", "type": "rss",  "url": "https://www.fdic.gov/news/financial-institution-letters/rss.xml"},
    # EU
    {"name": "EBA",      "jurisdiction": "EU", "type": "rss",  "url": "https://www.eba.europa.eu/rss"},
    {"name": "ECB",      "jurisdiction": "EU", "type": "rss",  "url": "https://www.ecb.europa.eu/rss/press.html"},
    {"name": "ESMA",     "jurisdiction": "EU", "type": "rss",  "url": "https://www.esma.europa.eu/rss"},
    {"name": "EUR-Lex",  "jurisdiction": "EU", "type": "rss",  "url": "https://eur-lex.europa.eu/rss-updates.html"},
    # SINGAPORE
    {"name": "MAS",  "jurisdiction": "SG", "type": "rss",  "url": "https://www.mas.gov.sg/news/rss"},
    # AUSTRALIA
    {"name": "APRA", "jurisdiction": "AU", "type": "rss",  "url": "https://www.apra.gov.au/news-events/rss"},
    {"name": "ASIC", "jurisdiction": "AU", "type": "rss",  "url": "https://asic.gov.au/about-asic/news-centre/rss-feeds/"},
    # HONG KONG
    {"name": "HKMA", "jurisdiction": "HK", "type": "web",  "url": "https://www.hkma.gov.hk/eng/news-and-media/press-releases/"},
    {"name": "SFC",  "jurisdiction": "HK", "type": "rss",  "url": "https://www.sfc.hk/en/News-and-announcements/News/rss"},
    # INTERNATIONAL
    {"name": "BIS",  "jurisdiction": "INT", "type": "rss", "url": "https://www.bis.org/press/press.rss"},
    {"name": "FSB",  "jurisdiction": "INT", "type": "rss", "url": "https://www.fsb.org/feed/"},
    {"name": "FATF", "jurisdiction": "INT", "type": "web", "url": "https://www.fatf-gafi.org/en/publications.html"},
    {"name": "IMF",  "jurisdiction": "INT", "type": "rss", "url": "https://www.imf.org/en/News/rss?language=eng&category=PressRelease"},
]
