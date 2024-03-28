# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ProductCategory(models.Model):
    _inherit = "product.category"

    # 注意，产品目录不分多公司

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

    is_commission_apply = fields.Boolean(string='Apply Commission??', default=False)

    @api.depends()
    def _compute_commission_amount_on(self):
        for rec in self:
            rec.commission_amount_on = self.env.user.company_id.commission_amount_on
