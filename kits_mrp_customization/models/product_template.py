from odoo import _,models,fields,api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_kcash_rewards = fields.Boolean('Clairmont Cash Product')
    hide_from_order = fields.Boolean('Hide From Order')

    manufacturing_default_code = fields.Char('Manufacturing Internal Reference',compute='_compute_manufacturing_default_code',inverse='_set_manufacturing_default_code',store=True)

    @api.model_create_multi
    def create(self, vals_list):
        templates = super(ProductTemplate, self).create(vals_list)
        for template, vals in zip(templates, vals_list):
            related_vals = {}
            if vals.get('manufacturing_default_code'):
                related_vals['manufacturing_default_code'] = vals['manufacturing_default_code']
            if related_vals:
                template.write(related_vals)
        return templates

    def write(self,vals_list):
        new_tag=[]
        if vals_list.get('x_studio_many2many_field_bOjgj'):
            new_tag = list(filter(lambda x: x not in self.x_studio_many2many_field_bOjgj.ids, vals_list.get('x_studio_many2many_field_bOjgj')[0][2]))
        res = super(ProductTemplate,self).write(vals_list)
        if new_tag :
            categ_product_tag = self.categ_id.categ_product_tag
            if categ_product_tag.id in new_tag:
                product_category = self.categ_id
                for product in self.product_variant_ids:
                    action = product_category.with_context(product=product)
                    action.kits_action_create_update_replanish()
                    action.kits_action_create_update_putaway_rules()
                    action.action_create_bom()
                    action.kits_action_update_route()
        return res

    @api.depends('product_variant_ids', 'product_variant_ids.manufacturing_default_code')
    def _compute_manufacturing_default_code(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.manufacturing_default_code = template.product_variant_ids.manufacturing_default_code
        for template in (self - unique_variants):
            template.manufacturing_default_code = False

    def _set_manufacturing_default_code(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.manufacturing_default_code = template.manufacturing_default_code