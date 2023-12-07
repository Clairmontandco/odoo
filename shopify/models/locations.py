from .. import shopify
from odoo import models, fields


class ShopifyAccount(models.Model):
    _name = "shopify.location.ts"
    _description = 'Shopify Location'

    name = fields.Char('Account Name', required=True)
    active = fields.Boolean(default=True)
    shopify_location_id = fields.Char("Shopify Location ID", copy=False)
    mk_instance_id = fields.Many2one('mk.instance', "Instance", ondelete='cascade')
    is_default_location = fields.Boolean("Is Default Location?",
                                         help="Location that Shopify and apps will use when no other location is specified. Only locations that fulfill online orders can be used as your default location.",
                                         copy=False)
    order_warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', copy=False,
                                         help="This warehouse is set in the Order if this location is found. Otherwise set Instance's warehouse.")
    company_id = fields.Many2one('res.company', string='Company', related='mk_instance_id.company_id', store=True)
    location_id = fields.Many2one('stock.location', 'Location', help="This warehouse location is used while import/export stock.", domain="[('usage','=','internal')]")
    is_legacy = fields.Boolean('Is Legacy Location')
    is_import_export_stock = fields.Boolean('Enable Import/Export Stock?', help="If you enable then stock for this location will be use for import/export.", default=True, copy=False)

    def prepare_vals_for_location(self, location, mk_instance_id):
        vals = {'name': location.get('name'),
                'shopify_location_id': location.get('id'),
                'mk_instance_id': mk_instance_id.id,
                'is_legacy': location.get('legacy')}
        return vals

    def set_default_location(self, mk_instance_id):
        shopify_default_location = self.search([('is_default_location', '=', True), ('mk_instance_id', '=', mk_instance_id.id)], limit=1)
        if shopify_default_location:
            shopify_default_location.write({'is_default_location': False})
        default_location_id = shopify.Shop.current().to_dict().get('primary_location_id')
        default_location = default_location_id and self.search([('shopify_location_id', '=', default_location_id), ('mk_instance_id', '=', mk_instance_id.id)]) or False
        if default_location:
            default_location.write({'is_default_location': True,
                                    'order_warehouse_id': mk_instance_id.warehouse_id.id,
                                    'location_id': mk_instance_id.warehouse_id.lot_stock_id.id})
        return True

    def remove_deactivate_shopify_locations(self, active_location_ids, mk_instance_id):
        all_shopify_location = self.search([('mk_instance_id', '=', mk_instance_id.id)])
        to_remove_location = all_shopify_location - active_location_ids
        to_remove_location and to_remove_location.write({'active': False})
        return active_location_ids

    def import_location_from_shopify(self, mk_instance_id):
        active_location_ids = self
        mk_instance_id.connection_to_shopify()
        shopify_locations = shopify.Location.find(active=True)
        for location in shopify_locations:
            location = location.to_dict()
            vals = self.prepare_vals_for_location(location, mk_instance_id)
            shopify_location_id = self.with_context(active_test=False).search([('shopify_location_id', '=', location.get('id')), ('mk_instance_id', '=', mk_instance_id.id)])
            if shopify_location_id:
                vals.update({'active': True})
                shopify_location_id.write(vals)
            else:
                shopify_location_id = self.create(vals)
            active_location_ids += shopify_location_id
        self.set_default_location(mk_instance_id)
        self.remove_deactivate_shopify_locations(active_location_ids, mk_instance_id)
        return True
