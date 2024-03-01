from odoo import models, fields, api

class product_template(models.Model):
    _inherit = 'product.template'

    kits_manufacture_ok = fields.Boolean('Manufacture on demand', compute='_compute_kits_manufacture_ok', inverse='_set_kits_manufacture_ok', store=True)

    @api.depends('product_variant_ids', 'product_variant_ids.kits_manufacture_ok')
    def _compute_kits_manufacture_ok(self):
        for record in self:
            if len(record.product_variant_ids) == 1:
                record.kits_manufacture_ok = record.product_variant_ids.kits_manufacture_ok
            else:
                record.kits_manufacture_ok = False

    def _set_kits_manufacture_ok(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.kits_manufacture_ok = template.kits_manufacture_ok