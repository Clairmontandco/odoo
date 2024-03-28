# -*- coding: utf-8 -*-
from odoo import models, fields, api

class Team(models.Model):
    _inherit = 'crm.team'

    commission_rule_on = fields.Selection(related='company_id.commission_rule_on', readonly=True, store=False)

    sale_commission_rule_ids = fields.One2many('sale.commission.rule', 'team_id',
                                               copy=True, auto_join=True, string="Sale Commission Rules")

