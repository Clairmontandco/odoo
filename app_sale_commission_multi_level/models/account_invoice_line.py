# -*- coding: utf-8 -*-

import datetime
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"
    # 参考 is_downpayment, 报销 expense
