from odoo import _,models,fields,api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    kits_shopify_published_scope = fields.Selection([('unpublished','Unpublished'),('web','Published in Store Only'),('global','Published in Store and POS')],'Published Scope',compute='_compute_shopigy_published_scope',store=True)

    @api.depends('mk_listing_ids')
    def _compute_shopigy_published_scope(self):
        for rec in self:
            if rec.mk_listing_ids:
                first_listing = rec.mk_listing_ids[0]
                if first_listing:
                    rec.kits_shopify_published_scope = first_listing.shopify_published_scope
            else :
                rec.kits_shopify_published_scope = False