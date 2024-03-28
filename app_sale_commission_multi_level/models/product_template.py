# -*- coding: utf-8 -*-
from odoo import fields, models, api, _

class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _get_commission_amount_on(self):
        commission_amount_on = self.env.user.company_id.commission_amount_on
        return commission_amount_on

    commission_amount_on = fields.Selection([
        ('amount_untaxed', 'Untaxed Amount'),
        ('product_template', 'Only for Product allow commission'),
        ('product_category', 'Only for Category allow commission')],
        string="Set Amount on", readonly=True,
        compute='_compute_commission_amount_on',
        default=_get_commission_amount_on
    )

    is_commission_apply = fields.Boolean(string='Apply Commission?', default=False)
    # 技术字体，true 时此产品用于设置提成相关
    is_commission_product = fields.Boolean(
        'Is Commission Product ?'
    )

    @api.depends('company_id')
    def _compute_commission_amount_on(self):
        for rec in self:
            rec.commission_amount_on = self.env.user.company_id.commission_amount_on
