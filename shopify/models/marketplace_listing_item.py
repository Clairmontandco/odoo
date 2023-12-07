from odoo import models, fields

CONTINUE_SELLING = [('continue', 'Allow'), ('deny', 'Deny'), ('parent_product', 'Same as Product Template')]
INVENTORY_MANAGEMENT = [('shopify', 'Track Quantity'), ('dont_track', 'Dont track Inventory')]
WEIGHT_UNIT = [('g', 'Gram'), ('kg', 'KG'), ('oz', 'Oz'), ('lb', 'LB')]


class MkListingItem(models.Model):
    _inherit = "mk.listing.item"

    def _get_default_taxable_value(self):
        is_taxable = False
        if self.mk_listing_id:
            is_taxable = self.mk_listing_id.is_taxable
        return is_taxable

    def _get_default_weight_unit(self):
        product_weight_in_lbs_param = self.env['ir.config_parameter'].sudo().get_param('product.weight_in_lbs')
        if product_weight_in_lbs_param == '1':
            return 'lb'
        else:
            return 'kg'

    def _compute_shopify_inventory(self):
        for rec in self:
            location_ids = self.env['shopify.location.ts'].search([('mk_instance_id', '=', rec.mk_instance_id.id), ('is_import_export_stock', '=', True)])
            shopify_current_stock = 0.0
            for shopify_location_id in location_ids:
                location_id = shopify_location_id.location_id or False
                if location_id:
                    variant_quantity = rec.product_id.get_product_stock(rec.export_qty_type, rec.export_qty_value, location_id, rec.mk_instance_id.stock_field_id.name)
                    shopify_current_stock += variant_quantity
            rec.shopify_current_stock = shopify_current_stock

    inventory_item_id = fields.Char('Inventory Item ID')
    shopify_image_id = fields.Char("Shopify Image ID")
    inventory_management = fields.Selection(INVENTORY_MANAGEMENT, default='shopify')
    continue_selling = fields.Selection(CONTINUE_SELLING, default='parent_product', help='If true then Customer can place order while product is out of stock.')
    is_taxable = fields.Boolean("Charge tax on this product?", default=_get_default_taxable_value)
    weight_unit = fields.Selection(WEIGHT_UNIT, default=_get_default_weight_unit, help='The unit of measurement that applies to the product variant weight.')
    shopify_last_stock_update_date = fields.Datetime("Shopify Last Stock Updated On", copy=False, help="Date were stock updated to Shopify.")
    shopify_current_stock = fields.Float(string="Inventory", compute="_compute_shopify_inventory")

    def open_shopify_inventory(self):
        return True
