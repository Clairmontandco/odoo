from odoo import models, fields,api ,_
from odoo.exceptions import UserError

class product_product(models.Model):
    _inherit = 'product.product'
    
    kits_manufacture_ok = fields.Boolean('Manufacture On Demand')

    def check_kits_manufacture_ok(self):
        product_ids_display_name = []
        product_ids_to_check = self
        products_without_bom_list = 'The following products do not have Bill of Materials (BOM) and because of that they are not eligible for manufacturing on-demand:\n\n'
        for product in self:
            if not product.bom_ids:
                product_ids_display_name.append(product.display_name)
                product_ids_to_check-=product

        product_ids_to_check.kits_manufacture_ok = True

        if product_ids_display_name:
            products_without_bom_list +=  '\n'.join(product_ids_display_name)
            form_view = self.env.ref('kits_manufacture_on_demand.kits_warning_wizard_form_view')
            warning_id = self.env['kits.warning.wizard'].create({'warning': products_without_bom_list})
            return {
                    'name': _('WARNING!'),
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'kits.warning.wizard',
                    'views': [(form_view.id, 'form')],
                    'res_id': warning_id.id,
                    'type': 'ir.actions.act_window',
                    'target': 'new',
                }

    def uncheck_kits_manufacture_ok(self):
        product_ids = self.filtered(lambda x: x.kits_manufacture_ok == True)
        product_ids.kits_manufacture_ok = False

    @api.onchange('kits_manufacture_ok')
    def raise_usererror_onchange_kits_manufacture_ok(self):
        if self.kits_manufacture_ok == True and not self.bom_ids:
            raise UserError('Product do not have Bill of Materials (BOM) and because of that they are not eligible for manufacturing on-demand')