# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    commission_rule_on = fields.Selection(related='company_id.commission_rule_on', readonly=True)

    sale_commission_rule_ids = fields.One2many('sale.commission.rule', 'partner_id',
                                               copy=True, auto_join=True, string="Sale Commission Rules")
