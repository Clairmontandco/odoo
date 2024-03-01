from odoo import models, fields

class product_product(models.Model):
    _inherit = 'product.product'

    kits_manufacture_ok = fields.Boolean('Manufacture on demand')

