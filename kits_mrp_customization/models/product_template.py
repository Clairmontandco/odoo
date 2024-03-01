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

    def kits_update_rule_by_product_tmpl_tags(self):
        for rec in self:
            categ_product_tag = rec.categ_id.categ_product_tag
            if categ_product_tag.id in rec.x_studio_many2many_field_bOjgj.ids:
                product_category = rec.categ_id
                for product in rec.product_variant_ids:
                    action = product_category.with_context(product=product)
                    action.kits_action_create_update_replanish()
                    action.kits_action_create_update_putaway_rules()
                    action.action_create_bom()
                    action.kits_action_update_route()

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