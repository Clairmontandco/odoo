from odoo import _, api, fields, models, tools

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    do_not_override = fields.Boolean('Do not override')

    @api.onchange('product_tmpl_id')
    def onchange_product_tmpl_id(self):
        if self.product_tmpl_id:
            self.product_uom_id = self.product_tmpl_id.uom_id.id
            if self.product_id.product_tmpl_id != self.product_tmpl_id:
                self.product_id = False
            self.bom_line_ids.bom_product_template_attribute_value_ids = False
            self.operation_ids.bom_product_template_attribute_value_ids = False
            self.byproduct_ids.bom_product_template_attribute_value_ids = False

            domain = [('product_tmpl_id', '=', self.product_tmpl_id.id)]
            if isinstance(self.id,int):
                domain.append(('id', '!=', self.id))
            else:
                if self.id.origin:
                    domain.append(('id', '!=', self.id.origin))
            number_of_bom_of_this_product = self.env['mrp.bom'].search_count(domain)
            if number_of_bom_of_this_product:  # add a reference to the bom if there is already a bom for this product
                self.code = _("%s (new) %s", self.product_tmpl_id.name, number_of_bom_of_this_product)
            else:
                self.code = False
