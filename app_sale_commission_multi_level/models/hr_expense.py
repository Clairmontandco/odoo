# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError



class HrExpense(models.Model):
    _inherit = "hr.expense"

    commission_partner_id = fields.Many2one('res.partner', string="Commission To")
    commission_line_id = fields.Many2one('sale.commission.line', string="Commission Line", readonly=True)
    is_commission = fields.Boolean(string='Is Commission?', default=False)

    def action_move_create(self):
        # todo: 生成的会计帐，目标 partner 看财务要求来对应到相关 partner
        ids = super(HrExpense, self).action_move_create()
        return ids
