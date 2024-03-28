# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import Warning


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    commission_rule_on = fields.Selection(related='company_id.commission_rule_on', readonly=False, store=False)
    commission_amount_on = fields.Selection(related='company_id.commission_amount_on', readonly=False, store=False)
    # 默认提成产品，可变化
    commission_default_product_id = fields.Many2one(
        'product.product',
        'Commission Product',
        domain="[('type', '=', 'service')]",
        config_parameter='app_commission_default_product_id',
        default=lambda self: self.env.ref('app_sale_commission_multi_level.commission_default_product_id', False),
        help='Default product use for Commission')
