import logging
import dateutil
import traceback
from pytz import timezone

_logger = logging.getLogger("Teqstars:Shopify")


def convert_shopify_datetime_to_utc(datetime):
    converted_datetime = ""
    if datetime:
        datetime = dateutil.parser.parse(datetime)
        converted_datetime = datetime.astimezone(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')
    return converted_datetime or False


def log_traceback_for_exception():
    _logger.error(traceback.format_exc())
