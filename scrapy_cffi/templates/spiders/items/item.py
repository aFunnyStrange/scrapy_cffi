from scrapy_cffi.item import Item, Field

class CustomItem(Item):
    session_id = Field()
    ret_cookies = Field()
    session_end = Field()
    data = Field()
    cumtom1 = Field()
    cumtom2 = Field()