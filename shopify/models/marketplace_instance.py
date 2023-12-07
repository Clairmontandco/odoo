import json
import requests
from .. import shopify
from urllib.parse import urlparse
from odoo import models, fields, api, _
from odoo.modules.module import get_module_resource
from odoo.exceptions import ValidationError, AccessError

ACCOUNT_STATE = [('not_confirmed', 'Not Confirmed'), ('confirmed', 'Confirmed')]


class MkInstance(models.Model):
    _inherit = "mk.instance"

    def _get_mk_kanban_counts(self):
        super(MkInstance, self)._get_mk_kanban_counts()
        for mk_instance_id in self:
            mk_instance_id.shopify_collection_count = len(mk_instance_id.shopify_collection_ids)
            mk_instance_id.shopify_location_count = len(mk_instance_id.shopify_location_ids)

    def _get_default_fulfillment_status(self):
        fulfillment_status_id = self.env.ref('shopify.shopify_order_status_unshipped', raise_if_not_found=False)
        return [(6, 0, [fulfillment_status_id.id])] if fulfillment_status_id else False

    def _get_shopify_discount_product(self):
        return self.env.ref('shopify.shopify_discount', raise_if_not_found=False) or False

    def _get_shopify_delivery_product(self):
        return self.env.ref('shopify.shopify_delivery', raise_if_not_found=False) or False

    def shopify_mk_default_api_limit(self):
        return 250

    marketplace = fields.Selection(selection_add=[('shopify', _("Shopify"))], string='Marketplace')
    password = fields.Char("Password", copy=False)
    shop_url = fields.Char("Shopify Shop URL", copy=False, help="Exp. https://teqstars.myshopify.com")
    is_token = fields.Boolean("I have API Access Token", default=False, help="You can find Admin API Access token from Shopify Apps.", copy=False)
    api_token = fields.Char("API access token", copy=False)

    # Sale Orders Fields
    fulfillment_status_ids = fields.Many2many('shopify.order.status', 'marketplace_order_status_rel', 'mk_instance_id', 'status_id', "Fulfillment Status",
                                              default=_get_default_fulfillment_status, help="Filter orders by their fulfillment status at the time of Import Orders.")
    financial_workflow_config_ids = fields.One2many("shopify.financial.workflow.config", "mk_instance_id", "Financial Workflow Configuration")
    default_pos_customer_id = fields.Many2one('res.partner', string='Default POS Customer',
                                              domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('customer_rank','>', 0)]",
                                              help="If customer is not found in POS Orders then set this customer.")
    is_fetch_fraud_analysis_data = fields.Boolean("Fetch Fraud Analysis Data?", default=True, help="It will fetch detail of Fraud Analysis and show in the Order Form view.")
    custom_product_id = fields.Many2one('product.product', string='Custom Product',
                                        help="Shopify order with having custom item will be imported with this product in order.")
    custom_storable_product_id = fields.Many2one('product.product', string='Custom Storable Product',
                                                 help="Shopify order with having custom fulfillable item will be imported with this product in order.")
    gift_card_product_id = fields.Many2one('product.product', string='Gift Card Product', domain=[('type', '=', 'service')],
                                           help="Shopify gift card orders will be imported with this product (Only Service type product).")
    tip_product_id = fields.Many2one('product.product', string='Tip Product', domain=[('type', '=', 'service')],
                                     help="Shopify Tip order line will be imported with this product (Only Service type product).")
    duties_product_id = fields.Many2one('product.product', string='Duties Product', domain=[('type', '=', 'service')],
                                        help="Shopify Duties order line will be imported with this product (Only Service type product).")
    shopify_import_after_order = fields.Datetime("Shopify Import Order After", copy=False, help="Orders will be import after this date.")

    # Email & Notification
    is_notify_customer = fields.Boolean("Notify Customer?", default=False,
                                        help="Whether the customer should be notified. If set to true, then an email will be sent when the fulfillment is created or updated.")

    # Webhook
    webhook_url = fields.Char("Shopify Webhook URL", copy=False)
    webhook_ids = fields.One2many("shopify.webhook.ts", "mk_instance_id", "Shopify Webhooks")

    # Dashboard fields
    shopify_collection_ids = fields.One2many('shopify.collection.ts', 'mk_instance_id', string="Collections")
    shopify_collection_count = fields.Integer("Collection Count", compute='_get_mk_kanban_counts')
    shopify_location_ids = fields.One2many('shopify.location.ts', 'mk_instance_id', string="Locations")
    shopify_location_count = fields.Integer("Location Count", compute='_get_mk_kanban_counts')

    # Customer Fields.
    is_create_company_contact = fields.Boolean("Shopify Create Company Contact?", default=False, help="It will create company contact if found company while creating Customer.")

    # Payout Fields
    payout_report_last_sync_date = fields.Date("Payout Last Sync Date")
    payout_journal_id = fields.Many2one('account.journal', string='Payout Journal', domain="[('company_id', '=', company_id)]")
    is_payout_auto_process = fields.Boolean("Auto Process Payout Report?", help="System will automatically process/reconcile payout report with invoice at the time of import payout process.")
    payout_account_config_ids = fields.One2many('shopify.payout.account.config', 'mk_instance_id', string="Payout Account Config")

    @api.model
    def create(self, vals):
        if vals.get('marketplace', '') == 'shopify':
            if not urlparse(vals.get('shop_url', '')).scheme:
                raise ValidationError(_("URL must include http or https!"))
            if vals.get('shop_url', '').endswith('/'):
                vals.update({'shop_url': vals.get('shop_url')[:-1]})
        res = super(MkInstance, self).create(vals)
        if vals.get('marketplace', '') == 'shopify':
            res.onchange_shopify_product_id()
            # Create Webhook URL
            odoo_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            instance_url = "{}/{}/".format(self.env.cr.dbname, res.id)
            res.webhook_url = odoo_url + '/shopify/webhook/notification/' + instance_url
            # res.fetch_shopify_webhook() TODO: Remove comment if needed.
            res.shopify_set_default_pos_customer()
        return res

    def write(self, vals):
        if vals.get('marketplace') == 'shopify' or self.marketplace == 'shopify':
            # Create Webhook URL
            odoo_url = self.get_base_url()
            instance_url = "{}/{}".format(self.env.cr.dbname, self.id)
            vals.update({'webhook_url': odoo_url + '/shopify/webhook/notification/' + instance_url})
            if vals.get('api_limit', False) and vals.get('api_limit') > 250:
                raise ValidationError(_("You cannot set API Fetch record limit more than 250."))
            if 'shop_url' in vals and vals.get('shop_url', '').endswith('/'):
                vals.update({'shop_url': vals.get('shop_url')[:-1]})
        res = super(MkInstance, self).write(vals)
        for rec in self:
            if rec.marketplace == 'shopify':
                rec.shopify_set_default_pos_customer()
                rec.onchange_shopify_product_id()
                if not urlparse(rec.shop_url).scheme:
                    raise ValidationError(_("URL must include http or https protocol!"))
        return res

    @api.onchange('gift_card_product_id', 'tip_product_id', 'duties_product_id', 'custom_storable_product_id', 'custom_storable_product_id', 'marketplace')
    def onchange_shopify_product_id(self):
        if not self.gift_card_product_id and self.marketplace == 'shopify':
            self.gift_card_product_id = self.env.ref('shopify.shopify_gift_card_product', False) or False
        if not self.tip_product_id and self.marketplace == 'shopify':
            self.tip_product_id = self.env.ref('shopify.shopify_tip_product', False) or False
        if not self.duties_product_id and self.marketplace == 'shopify':
            self.duties_product_id = self.env.ref('shopify.shopify_duties_product', False) or False
        if not self.custom_product_id and self.marketplace == 'shopify':
            self.custom_product_id = self.env.ref('shopify.shopify_custom_line_product', raise_if_not_found=False) or False
        if not self.custom_storable_product_id and self.marketplace == 'shopify':
            self.custom_storable_product_id = self.env.ref('shopify.shopify_custom_storable_line_product', raise_if_not_found=False) or False

    def shopify_set_default_pos_customer(self):
        if not self.default_pos_customer_id:
            partner_obj = self.env['res.partner']
            pos_customer_id = partner_obj.search(
                ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id), ('name', '=', 'POS Customer ({})'.format(self.name)), ('customer_rank', '>', 0)])
            if not pos_customer_id:
                partner_vals = {'name': 'POS Customer ({})'.format(self.name), 'customer_rank': 1}
                pos_customer_id = partner_obj.create(partner_vals)
            self.default_pos_customer_id = pos_customer_id.id
        return True

    def shopify_mk_kanban_badge_color(self):
        return "#95BF46"

    def shopify_mk_kanban_image(self):
        return get_module_resource('shopify', 'static/description', 'shopify_logo.png')

    def connection_to_shopify(self):
        session = shopify.Session(self.shop_url, '2023-04', self.api_token if self.is_token else self.password)
        shopify.ShopifyResource.activate_session(session)
        return True

    def shopify_action_confirm(self):
        self.connection_to_shopify()
        try:
            shop = shopify.Shop.current()
            shop_dict = shop.to_dict()
            self.set_pricelist(shop_dict.get('currency'))
            self.env['shopify.location.ts'].import_location_from_shopify(self)
        except Exception as e:
            raise AccessError(e)

    def shopify_hide_instance_field(self):
        return ['fbm_order_prefix', 'api_limit']

    def reset_to_draft(self):
        res = super(MkInstance, self).reset_to_draft()

        if self.marketplace == 'shopify':
            self.connection_to_shopify()
            for webhook in self.webhook_ids:
                webhook.shopify_delete_webhook()
        return res

    def shopify_marketplace_operation_wizard(self):
        action = self.env.ref('base_marketplace.action_marketplace_operation').read()[0]
        action['views'] = [(self.env.ref('shopify.shopify_mk_operation_form_view').id, 'form')]
        return action

    def fetch_shopify_webhook(self):
        self.env['shopify.webhook.ts'].fetch_all_webhook_from_shopify(self)
        return True

    def delete_shopify_webhook(self):
        self.connection_to_shopify()
        webhooks = shopify.Webhook().find()
        odoo_url = self.get_base_url()
        for webhook in webhooks:
            webhook_dict = webhook.to_dict()
            address = webhook_dict.get('address')
            if address.endswith('/'):
                address = address[:-1]
            if odoo_url == address:
                webhook.destroy()
        return True

    def shopify_setup_schedule_actions(self, mk_instance_id):
        cron_obj = self.env['ir.cron']
        shopify_cron_ids = self.env['ir.cron'].search([('mk_instance_id', '=', self.id), '|', ('active', '=', True), ('active', '=', False)])
        cron_list = [{'cron_name': 'Shopify [{}] : Import Order'.format(mk_instance_id.name), 'method_name': 'cron_auto_import_shopify_orders', 'model_name': 'sale.order', 'interval_type': 'minutes', 'interval_number': 15},
                     {'cron_name': 'Shopify [{}] : Export Order Status/Tracking Information'.format(mk_instance_id.name), 'method_name': 'cron_auto_update_order_status', 'model_name': 'sale.order', 'interval_type': 'minutes', 'interval_number': 25},
                     {'cron_name': 'Shopify [{}] : Export Product\'s Inventory'.format(mk_instance_id.name), 'method_name': 'cron_auto_export_stock', 'model_name': 'mk.listing', 'interval_type': 'minutes', 'interval_number': 30},
                     {'cron_name': 'Shopify [{}] : Import Product\'s Inventory'.format(mk_instance_id.name), 'method_name': 'cron_auto_import_stock', 'model_name': 'mk.listing', 'interval_type': 'days', 'interval_number': 1},
                     {'cron_name': 'Shopify [{}] : Export Product\'s Price'.format(mk_instance_id.name), 'method_name': 'cron_auto_update_product_price', 'model_name': 'mk.listing', 'interval_type': 'days', 'interval_number': 1},
                     {'cron_name': 'Shopify [{}] : Import Payout Reports'.format(mk_instance_id.name), 'method_name': 'cron_auto_import_shopify_payout_report', 'model_name': 'shopify.payout', 'interval_type': 'days', 'interval_number': 1}]
        for cron_dict in cron_list:
            shopify_cron_ids -= cron_obj.create_marketplace_cron(mk_instance_id,
                cron_dict['cron_name'], method_name=cron_dict['method_name'], model_name=cron_dict['model_name'], interval_type=cron_dict['interval_type'], interval_number=cron_dict['interval_number'])
        if shopify_cron_ids:
            shopify_cron_ids.unlink()
        return True
