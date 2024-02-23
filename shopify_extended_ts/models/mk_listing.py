from odoo import _, api, fields, models, tools

class MkListing(models.Model):
    _inherit = "mk.listing"

    tag_ids = fields.Many2many("shopify.tags.ts", "shopify_tags_ts_rel", "product_tmpl_id", "tag_id", "Shopify Tags",compute='_compute_tag_ids',store=True,readonly=0)

    @api.model
    def create(self,vals):
        res = super(MkListing, self).create(vals)
        product_tmpl_id = res.product_tmpl_id
        product_tags = product_tmpl_id.x_studio_many2many_field_bOjgj if product_tmpl_id else None
        shopify_tags = res.tag_ids
        need_to_create_product_tags = shopify_tags.filtered(lambda t:t.name not in product_tags.mapped('x_name'))
        need_to_create_shopify_tags = product_tags.filtered(lambda t:t.x_name not in shopify_tags.mapped('name'))
        if need_to_create_product_tags:
            need_to_create_product_tags_name = need_to_create_product_tags.mapped('name')
            in_product_tags = self.env['x_product_tags'].search([('x_name','in',need_to_create_product_tags_name)])
            for tag in in_product_tags:
                need_to_create_product_tags_name.remove(tag.x_name)
                product_tmpl_id.x_studio_many2many_field_bOjgj = [(4, tag.id)]
            for tag in need_to_create_product_tags_name:
                product_tag_id = self.env['x_product_tags'].create({'x_name':tag})
                product_tmpl_id.x_studio_many2many_field_bOjgj = [(4, product_tag_id.id)]
        if need_to_create_shopify_tags:
            need_to_create_shopify_tags_name = need_to_create_shopify_tags.mapped('x_name')
            in_shopify_tags = self.env['shopify.tags.ts'].search([('name','in',need_to_create_shopify_tags_name)])
            for tag in in_shopify_tags:
                need_to_create_shopify_tags_name.remove(tag.name)
                res.tag_ids = [(4, tag.id)]
            for tag in need_to_create_shopify_tags_name:
                shopify_tag_id = self.env['shopify.tags.ts'].create({'name':tag})
                res.tag_ids = [(4, shopify_tag_id.id)]
        return res

    def write(self, vals):
        res = super(MkListing, self).write(vals)
        if vals.get('tag_ids') and not(self._context.get('from_compute_tag_ids')):
            product_tmpl_id = self.product_tmpl_id
            product_tags = product_tmpl_id.x_studio_many2many_field_bOjgj
            shopify_tags = self.tag_ids
            need_to_create_product_tags = shopify_tags.filtered(lambda t:t.name not in product_tags.mapped('x_name'))
            need_to_remove_product_tags = product_tags.filtered(lambda t:t.x_name not in shopify_tags.mapped('name'))
            if need_to_create_product_tags:
                need_to_create_product_tags_name = need_to_create_product_tags.mapped('name')
                in_product_tags = self.env['x_product_tags'].search([('x_name','in',need_to_create_product_tags_name)])
                for tag in in_product_tags:
                    need_to_create_product_tags_name.remove(tag.x_name)
                    product_tmpl_id.x_studio_many2many_field_bOjgj = [(4, tag.id)]
                for tag in need_to_create_product_tags_name:
                    product_tag_id = self.env['x_product_tags'].create({'x_name':tag})
                    product_tmpl_id.x_studio_many2many_field_bOjgj = [(4, product_tag_id.id)]
            if set(need_to_remove_product_tags.ids).issubset(product_tmpl_id.x_studio_many2many_field_bOjgj.ids):
                product_tmpl_id.x_studio_many2many_field_bOjgj -= need_to_remove_product_tags
        return res

    @api.depends('product_tmpl_id.x_studio_many2many_field_bOjgj')
    def _compute_tag_ids(self):
        for record in self:
            self.with_context(from_compute_tag_ids=True)
            product_tags = record.product_tmpl_id.x_studio_many2many_field_bOjgj
            shopify_tags = record.tag_ids
            need_to_create_shopify_tags = product_tags.filtered(lambda t:t.x_name not in shopify_tags.mapped('name'))
            need_to_remove_shopify_tags = shopify_tags.filtered(lambda t:t.name not in product_tags.mapped('x_name'))
            if need_to_create_shopify_tags:
                need_to_create_shopify_tags_name = need_to_create_shopify_tags.mapped('x_name')
                in_shopify_tags = self.env['shopify.tags.ts'].search([('name','in',need_to_create_shopify_tags_name)])
                for tag in in_shopify_tags:
                    need_to_create_shopify_tags_name.remove(tag.name)
                    record.tag_ids = [(4, tag.id)]
                for tag in need_to_create_shopify_tags_name:
                    shopify_tag_id = self.env['shopify.tags.ts'].create({'name':tag})
                    record.tag_ids = [(4, shopify_tag_id.id)]
            if set(need_to_remove_shopify_tags.ids).issubset(record.tag_ids.ids):
                record.tag_ids -= need_to_remove_shopify_tags
