# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"

    commission_rule_on = fields.Selection([
        ('manual', 'Manual Set'),
        ('sales_team', 'Sales Person and Team'),
        ('sales_partner', 'Customer of Sale Order')],
        default='sales_team',  required=True,
        string="Get rule on",
    )

    commission_amount_on = fields.Selection([
        ('amount_untaxed', 'Untaxed Amount'),
        ('product_template', 'Only for Product allow commission'),
        ('product_category', 'Only for Category allow commission')],
        default='amount_untaxed', required=True,
        string="Set Amount on",
    )

