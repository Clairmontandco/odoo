from odoo import api, fields, models

class product_replenish(models.TransientModel):
    _inherit = 'product.replenish'

    is_manufacturing_on_demand = fields.Boolean('Invisible All Fields')

    @api.onchange('product_id','product_tmpl_id')
    def check_kits_invisible_fields(self):
        create_production = self.env['ir.config_parameter'].sudo().get_param('kits_manufacture_on_demand.create_production')
        if (self.product_id.kits_manufacture_ok or self.product_tmpl_id.kits_manufacture_ok) and create_production: 
            self.is_manufacturing_on_demand = True
