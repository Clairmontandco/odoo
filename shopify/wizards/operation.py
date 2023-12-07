from datetime import timedelta
from odoo.exceptions import UserError
from odoo import models, fields, tools, _
from odoo.addons.shopify.models.marketplace_listing import PUBLISHED_SCOPE

SHOPIFY_OPERATIONS = [('import', 'Import'),
                      ('export', 'Export')]

SHOPIFY_IMPORT_OPERATIONS = [('import_customers', 'Import Customers'),
                             ('import_orders', 'Import Orders'),
                             ('import_listings', 'Import Listings'),
                             ('import_stock', 'Import Inventory'),
                             ('import_payout_report', 'Import Payout Report'),
                             ('import_collections', 'Import Collections')]

SHOPIFY_EXPORT_OPERATIONS = [('export_listings', 'Export Listings'),
                             ('update_listings', 'Update Listings'),
                             ('update_prices', 'Export Prices'),
                             ('update_stock', 'Export Inventory'),
                             ('update_order_status', 'Export Tracking Details'),
                             ('export_collections', 'Export Collections'),
                             ('update_collections', 'Update Collections')]


class MarketplaceOperation(models.TransientModel):
    _inherit = "mk.operation"

    def _get_default_listing_from_date(self):
        mk_instance_id = self.env.context.get('active_id')
        mk_instance_id = self.env['mk.instance'].search([('id', '=', mk_instance_id)], limit=1)
        from_date = mk_instance_id.last_listing_import_date if mk_instance_id.last_listing_import_date else fields.Datetime.now() - timedelta(30)
        from_date = fields.Datetime.to_string(from_date)
        return from_date

    def _get_default_listing_to_date(self):
        to_date = fields.Datetime.now()
        to_date = fields.Datetime.to_string(to_date)
        return to_date

    def _get_default_payout_from_date(self):
        mk_instance_id = self.env.context.get('active_id')
        mk_instance_id = self.env['mk.instance'].search([('id', '=', mk_instance_id)], limit=1)
        from_date = mk_instance_id.payout_report_last_sync_date if mk_instance_id.payout_report_last_sync_date else fields.Datetime.now() - timedelta(3)
        from_date = fields.Date.to_string(from_date)
        return from_date

    def _get_default_payout_to_date(self):
        to_date = fields.Datetime.now().date()
        to_date = fields.Date.to_string(to_date)
        return to_date

    shopify_operations = fields.Selection(SHOPIFY_OPERATIONS, string="Shopify Operation", default='import')

    # Marketplace Import Fields
    import_collections = fields.Boolean("Import Collections")
    shopify_import_operations = fields.Selection(SHOPIFY_IMPORT_OPERATIONS, string="Shopify Import Operation", default='import_customers')
    from_listing_date = fields.Datetime("Shopify From Listing Date", default=_get_default_listing_from_date)
    to_listing_date = fields.Datetime("Shopify To Listing Date", default=_get_default_listing_to_date)
    import_date_based_on = fields.Selection([("created_at_min", "Create Date"), ("updated_at_min", "Update Date")], default="updated_at_min", string="Based On")

    # Marketplace Export Fields
    is_export_collection = fields.Boolean("Export Collections?")
    is_update_collection = fields.Boolean("Update Collections?")
    shopify_export_operations = fields.Selection(SHOPIFY_EXPORT_OPERATIONS, string="Shopify Export Operation", default='export_listings')
    shopify_published_scope = fields.Selection(PUBLISHED_SCOPE, string="Published Scope",
        help="Whether the product is published to the Point of Sale channel or Online Channel or Unpublished it.")

    # Shopify Payout Fields
    from_payout_date = fields.Date("Shopify From Payout Date", default=_get_default_payout_from_date)
    to_payout_date = fields.Date("Shopify To Payout Date", default=_get_default_payout_to_date)

    def do_shopify_operations(self):
        instance = self.mk_instance_id
        if not instance:
            raise UserError(_("Please select marketplace instance to process."))

        if self.shopify_operations == 'import':
            if self.shopify_import_operations == 'import_customers':
                self.env['res.partner'].shopify_import_customers(instance)
            if self.shopify_import_operations == 'import_listings':
                action = self.env['mk.listing'].with_context(import_date_based_on=self.import_date_based_on).shopify_import_listings(instance, self.from_listing_date, self.to_listing_date, mk_listing_id=self.mk_listing_id,
                    update_product_price=self.update_product_price, update_existing_product=self.update_existing_product)
                if action and type(action) == dict:
                    return action
            if self.shopify_import_operations == 'import_stock':
                self.env['mk.listing'].shopify_import_stock(instance)
            if self.shopify_import_operations == 'import_orders':
                action = self.env['sale.order'].with_context(from_import_screen=True).shopify_import_orders(instance, self.from_date, self.to_date, mk_order_id=self.mk_order_id)
                if action and type(action) == dict:
                    return action
            if self.shopify_import_operations == 'import_collections':
                self.env['shopify.collection.ts'].import_shopify_collections(instance)
            if self.shopify_import_operations == 'import_payout_report':
                self.env['shopify.payout'].shopify_import_payout_report(instance, self.from_payout_date, self.to_payout_date)
        else:
            if self.shopify_export_operations == 'export_listings':
                self.is_set_price = True
                self.is_update_product = True
                self.export_listing_to_mk()
            if self.shopify_export_operations == 'update_listings':
                self.update_listing_to_mk()
            if self.shopify_export_operations == 'update_prices':
                self.is_update_product = False
                self.is_set_price = True
                self.update_listing_to_mk()
            if self.shopify_export_operations == 'update_stock':
                self.is_update_product = False
                self.is_set_quantity = True
                self.update_listing_to_mk()
            if self.shopify_export_operations == 'update_order_status':
                self.env['sale.order'].shopify_update_order_status(instance)
            if self.shopify_export_operations == 'export_collections':
                collection_obj = self.env["shopify.collection.ts"]
                collection_domain = [('mk_instance_id', '=', instance.id), ('exported_in_shopify', '=', False)]
                collection_ids = collection_obj.search(collection_domain)
                collection_ids and collection_ids.export_collection_to_shopify_ts()
            if self.shopify_export_operations == 'update_collections':
                collection_obj = self.env["shopify.collection.ts"]
                collection_domain = [('mk_instance_id', '=', instance.id), ('exported_in_shopify', '=', True)]
                collection_ids = collection_obj.search(collection_domain)
                collection_ids and collection_ids.update_collection_to_shopify_ts()
