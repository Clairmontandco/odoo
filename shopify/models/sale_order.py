import time
import pytz
import pprint
import logging
from .. import shopify
from random import randint
from datetime import timedelta
import urllib.parse as urlparse
from odoo.exceptions import UserError
from odoo import models, fields, tools, api, _
from .misc import convert_shopify_datetime_to_utc
from odoo.addons.shopify.models.misc import log_traceback_for_exception

_logger = logging.getLogger("Teqstars:Shopify")

FINANCIAL_STATUS = [('pending', 'Pending'),
                    ('authorized', 'Authorized'),
                    ('partially_paid', 'Partially Paid'),
                    ('paid', 'Paid'),
                    ('partially_refunded', 'Partially Refunded'),
                    ('refunded', 'Refunded'),
                    ('voided', 'Voided')]

FULFILLMENT_STATUS = [('fulfilled', 'Fulfilled'),
                      ('unfulfilled', 'Unfulfilled'),
                      ('partial', 'Partial'),
                      ('restocked', 'Restocked')]

SOURCE_NAME = [('web', 'Online Store'),
               ('pos', 'POS'),
               ('shopify_draft_order', 'Draft Orders'),
               ('iphone', 'iPhone'),
               ('android', 'Android')]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('fraud_analysis_ids')
    def _check_fraud_orders(self):
        for order_id in self:
            if any(fraud_analysis_id['recommendation'] != 'accept' for fraud_analysis_id in order_id.fraud_analysis_ids):
                order_id.is_fraud_order = True
            else:
                order_id.is_fraud_order = False

    shopify_closed_at = fields.Datetime("Order Closing Date", copy=False)
    fraud_analysis_ids = fields.One2many("shopify.fraud.analysis", "order_id", string="Fraud Analysis", copy=False)
    is_fraud_order = fields.Boolean('Fraud Order?', default=False, copy=False, compute='_check_fraud_orders', store=True)
    shopify_financial_status = fields.Selection(FINANCIAL_STATUS, "Financial Status", help="The status of payments associated with the order in marketplace.")
    fulfillment_status = fields.Selection(FULFILLMENT_STATUS, copy=False, help="The order's status in terms of fulfilled line items:\n\n"
                                                                               "Fulfilled: Every line item in the order has been fulfilled.\n"
                                                                               "Unfulfilled: None of the line items in the order have been fulfilled.\n"
                                                                               "Partial: At least one line item in the order has been fulfilled.\n"
                                                                               "Restocked: Every line item in the order has been restocked and the order canceled.")
    shopify_source_name = fields.Selection(SOURCE_NAME, string="Order Source", copy=False, help="Know source of Order creation.")
    shopify_order_source_name = fields.Char("Shopify Order Source", copy=False, help="Know source of Order creation.")
    shopify_checkout_id = fields.Char("Checkout ID", copy=False, help="Know Checkout ID of Order.")
    shopify_force_refund = fields.Boolean('Force Refund in Odoo?', default=False, copy=False)
    shopify_payment_gateway_id = fields.Many2one("shopify.payment.gateway.ts", "Shopify Payment Gateway", help="Payment gateway of Shopify Order.", copy=False)

    def fetch_orders_from_shopify(self, from_date, to_date, shopify_fulfillment_status_ids, limit=250, mk_order_id=False):
        shopify_order_list, page_info = [], False
        if mk_order_id:
            order_list = []
            for order in ''.join(mk_order_id.split()).split(','):
                order_list.append(shopify.Order().find(order))
            return order_list
        utc_timezone = pytz.timezone("UTC")
        to_date = utc_timezone.localize(to_date)
        from_date = utc_timezone.localize(from_date)
        if 'Any' in shopify_fulfillment_status_ids.mapped('name'):
            shopify_fulfillment_status_ids = self.env.ref('shopify.shopify_order_status_any')
        from_import_screen = self.env.context.get('from_import_screen', False)
        for shopify_fulfillment_status_id in shopify_fulfillment_status_ids:
            while 1:
                if page_info:
                    page_wise_order_list = shopify.Order().find(limit=limit, page_info=page_info)
                else:
                    if from_import_screen:
                        page_wise_order_list = shopify.Order().find(status='any', fulfillment_status=shopify_fulfillment_status_id.status, processed_at_min=from_date, processed_at_max=to_date, limit=limit)
                    else:
                        page_wise_order_list = shopify.Order().find(status='any', fulfillment_status=shopify_fulfillment_status_id.status, updated_at_min=from_date, updated_at_max=to_date, limit=limit)
                page_url = page_wise_order_list.next_page_url
                parsed = urlparse.parse_qs(page_url)
                page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
                shopify_order_list = page_wise_order_list + shopify_order_list
                if not page_info:
                    break
        return shopify_order_list

    def check_validation_for_import_sale_orders(self, shopify_order_line_list, mk_instance_id, shopify_order_dict):
        is_importable, order_number = True, shopify_order_dict.get('name', '')
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        mk_listing_item_obj, mk_listing_obj = self.env['mk.listing.item'], self.env['mk.listing']

        # validation for Financial workflow
        financial_workflow_config_id = self.validate_shopify_financial_workflow(shopify_order_dict, mk_instance_id)
        if not financial_workflow_config_id:
            return False, financial_workflow_config_id

        for shopify_order_line_dict in shopify_order_line_list:
            variant_id = shopify_order_line_dict.get('variant_id', False)
            if variant_id:
                shopify_variant = mk_listing_item_obj.search([('mk_id', '=', variant_id), ('mk_instance_id', '=', mk_instance_id.id)])
                if shopify_variant or shopify_order_line_dict.get('gift_card', False) or False:
                    continue
                try:
                    shopify_variant = shopify.Variant().find(variant_id)
                except:
                    log_message = "IMPORT ORDER: Cannot find Shopify Listing Item ID {} in Shopify, Order reference {}.".format(variant_id, order_number)
                    self.env['mk.log'].create_update_log(mk_log_id=mk_log_id, mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
                    is_importable = False
                    break
                product_tmpl_id = shopify_order_line_dict.get('product_id', False)
                if shopify_variant:
                    shopify_variant_dict = shopify_variant.to_dict()
                    sku = shopify_variant_dict.get('sku', '')
                    barcode = shopify_variant_dict.get('barcode', '')
                    if product_tmpl_id:
                        shopify_product = shopify.Product().find(product_tmpl_id)
                        shopify_product_dict = shopify_product.to_dict()
                        mk_listing_obj.create_update_shopify_product(shopify_product_dict, mk_instance_id, update_product_price=True, is_update_existing_products=True)

                    odoo_product_variant_id, listing_item_id = mk_listing_obj.get_odoo_product_variant_and_listing_item(mk_instance_id, shopify_variant_dict.get("id", ""), barcode, sku)
                    if not odoo_product_variant_id:
                        log_message = "IMPORT ORDER: Marketplace Item SKU {} Not found for Order {}".format(sku, order_number)
                        self.env['mk.log'].create_update_log(mk_log_id=mk_log_id, mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
                        is_importable = False
                        break
        return is_importable, financial_workflow_config_id

    def validate_shopify_financial_workflow(self, shopify_order_dict, mk_instance_id):
        main_workflow_config_id, not_found = False, False
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        gateway_list = shopify_order_dict.get('payment_gateway_names', ['Untitled']) or ['Untitled']
        main_gateway = [transaction.get('gateway') for transaction in shopify_order_dict.get('transactions', []) if transaction.get('gateway', '') != 'gift_card']
        gateway_list = list(set(gateway_list + main_gateway))
        main_gateway = main_gateway and main_gateway[0] or gateway_list and gateway_list[0] or 'Untitled'

        for gateway in gateway_list:
            if not gateway and main_gateway:
                gateway = main_gateway
            shopify_payment_gateway_id = self.env['shopify.payment.gateway.ts'].search([('code', '=', gateway), ('mk_instance_id', '=', mk_instance_id.id)], limit=1)
            if not shopify_payment_gateway_id:
                shopify_payment_gateway_id = self.env['shopify.payment.gateway.ts'].create({'name': gateway, 'code': gateway, 'mk_instance_id': mk_instance_id.id})

            financial_workflow_config_id = self.env['shopify.financial.workflow.config'].search(
                ['|', ('financial_status', '=', shopify_order_dict.get('financial_status')), ('financial_status', '=', 'any'), ('mk_instance_id', '=', mk_instance_id.id),
                 ('payment_gateway_id', '=', shopify_payment_gateway_id.id)], limit=1)
            marketplace_workflow_id = financial_workflow_config_id.order_workflow_id or False
            if gateway == main_gateway:
                main_workflow_config_id = financial_workflow_config_id
            if not marketplace_workflow_id:
                log_message = "IMPORT ORDER: Financial Workflow Configuration not found for Shopify Order {}. Please configure the order workflow under the Workflow tab with Payment " \
                              "Gateway {} and Financial Status {} in Instance Configuration (Marketplaces > Configuration > Instance).".format(
                    shopify_order_dict.get('name'), shopify_payment_gateway_id.name, shopify_order_dict.get('financial_status'))
                self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict={
                    'error': [{'log_message': log_message, 'payment_gateway_id': shopify_payment_gateway_id.id, 'financial_status': shopify_order_dict.get('financial_status'), 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
                not_found = True
        return False if not_found else main_workflow_config_id

    def get_shopify_order_source(self, shopify_order_dict):
        source_name = shopify_order_dict.get('source_name', 'web') or 'web'
        if source_name == 'web':
            readable_source_name = 'Online Store'
        elif source_name == 'pos':
            readable_source_name = 'POS'
        elif source_name == 'shopify_draft_order':
            readable_source_name = 'Draft Orders'
        elif source_name == 'iphone':
            readable_source_name = 'iPhone'
        elif source_name == 'android':
            readable_source_name = 'Android'
        else:
            readable_source_name = source_name
        return readable_source_name

    def create_shopify_sale_order(self, shopify_order_dict, mk_instance_id, customer_id, billing_customer_id, shipping_customer_id, financial_workflow_config_id):
        self._set_payment_term_to_shopify_customer(customer_id, financial_workflow_config_id)
        shopify_source_name = self.get_shopify_order_source(shopify_order_dict)
        currency = self._get_shopify_order_currency(shopify_order_dict, mk_instance_id)
        pricelist_id = self._get_shopify_pricelist_id(mk_instance_id, currency)
        fiscal_position_id = self.env['account.fiscal.position'].with_company(mk_instance_id.company_id).get_fiscal_position(customer_id.id) or customer_id.property_account_position_id
        sale_order_vals = self.prepare_sale_order_values(shopify_order_dict, customer_id, billing_customer_id, shipping_customer_id, mk_instance_id, pricelist_id, fiscal_position_id, shopify_source_name, financial_workflow_config_id)
        order_id = self.create(sale_order_vals)
        return order_id

    def _set_payment_term_to_shopify_customer(self, customer_id, financial_workflow_config_id):
        if financial_workflow_config_id:
            payment_term_id = financial_workflow_config_id.payment_term_id
            if payment_term_id:
                customer_id.write({'property_payment_term_id': payment_term_id.id})

    def _get_shopify_order_currency(self, shopify_order_dict, mk_instance_id):
        if mk_instance_id.use_marketplace_currency:
            currency = shopify_order_dict.get('presentment_currency')
        else:
            currency = shopify_order_dict.get('currency')

        order_currency_id = self.env['res.currency'].with_context(active_test=False).search([('name', '=', currency)], limit=1)
        return order_currency_id

    def _get_shopify_pricelist_id(self, mk_instance_id, currency):
        product_pricelist_obj = self.env['product.pricelist']
        if mk_instance_id.pricelist_id and mk_instance_id.pricelist_id.currency_id != currency:
            if not currency.active:
                currency.active = True
            name = 'Shopify: %s' % mk_instance_id.name
            pricelist_id = product_pricelist_obj.search([('name', '=', name), ('currency_id', '=', currency.id)])
            if not pricelist_id:
                pricelist_id = product_pricelist_obj.create({'name': name, 'currency_id': currency.id, 'company_id': self.env.user.company_id.id})
        else:
            pricelist_id = mk_instance_id.pricelist_id or False
        return pricelist_id

    def prepare_sale_order_values(self, shopify_order_dict, customer_id, billing_customer_id, shipping_customer_id, mk_instance_id, pricelist_id, fiscal_position_id, shopify_source_name, financial_workflow_config_id):
        sale_order_vals = {
            'state': 'draft',
            'partner_id': customer_id.id,
            'partner_invoice_id': billing_customer_id.ids[0] if billing_customer_id else customer_id.id,
            'partner_shipping_id': shipping_customer_id.ids[0] if shipping_customer_id else customer_id.id,
            'date_order': convert_shopify_datetime_to_utc(shopify_order_dict.get("processed_at", "")),
            'expected_date': convert_shopify_datetime_to_utc(shopify_order_dict.get("processed_at", "")),
            'company_id': mk_instance_id.company_id.id,
            'warehouse_id': mk_instance_id.warehouse_id.id,
            'fiscal_position_id': fiscal_position_id.id,
            'pricelist_id': pricelist_id and pricelist_id.id or False,
            'team_id': mk_instance_id.team_id.id or False,
        }

        if mk_instance_id.use_marketplace_sequence:
            order_prefix = mk_instance_id.order_prefix
            order_name = shopify_order_dict.get("name", '')
            if order_prefix:
                order_name = "{}{}".format(order_prefix, shopify_order_dict.get("name", ''))
            sale_order_vals.update({'name': order_name})

        sale_order_vals = self.prepare_sales_order_vals_ts(sale_order_vals, mk_instance_id)

        sale_order_vals.update({'note': shopify_order_dict.get('note'),
                                'mk_id': shopify_order_dict.get('id'),
                                'user_id': mk_instance_id.salesperson_user_id.id,
                                'mk_order_number': shopify_order_dict.get('name'),
                                'shopify_financial_status': shopify_order_dict.get('financial_status'),
                                'mk_instance_id': mk_instance_id.id,
                                'shopify_checkout_id': shopify_order_dict.get('checkout_id', '') or '',
                                'fulfillment_status': shopify_order_dict.get('fulfillment_status', 'unfulfilled') or 'unfulfilled',
                                'shopify_order_source_name': shopify_source_name or '',
                                'shopify_payment_gateway_id': financial_workflow_config_id.payment_gateway_id.id})

        shopify_tag_vals = self.prepage_order_tag_vals(shopify_order_dict.get('tags'))
        if shopify_tag_vals:
            sale_order_vals.update(shopify_tag_vals)

        if financial_workflow_config_id:
            marketplace_workflow_id = financial_workflow_config_id.order_workflow_id
            sale_order_vals.update({
                'picking_policy': marketplace_workflow_id.picking_policy,
                'payment_term_id': customer_id.property_payment_term_id and customer_id.property_payment_term_id.id or False,
                'order_workflow_id': marketplace_workflow_id.id})

        return sale_order_vals

    def prepage_order_tag_vals(self, shopify_tags):
        def _get_default_color():
            return randint(1, 11)

        crm_tag_obj, tag_list = self.env['crm.tag'], []
        for tag in shopify_tags.split(','):
            if len(tag) < 1:
                continue
            shopify_tag_id = crm_tag_obj.search([('name', '=', tag)], limit=1)
            if not shopify_tag_id:
                shopify_tag_id = crm_tag_obj.create({'name': tag, 'color': _get_default_color()})
            tag_list.append(shopify_tag_id.id)
        return {'tag_ids': [(6, 0, tag_list)]}

    def get_odoo_shopify_location_from_id(self, shopify_location_id):
        shopify_location_obj = self.env['shopify.location.ts']
        location_id = shopify_location_obj.search([('shopify_location_id', '=', shopify_location_id), ('mk_instance_id', '=', self.mk_instance_id.id)]) if shopify_location_id else False
        if not location_id:
            shopify_location_obj.import_location_from_shopify(self.mk_instance_id)
            location_id = shopify_location_obj.search([('shopify_location_id', '=', shopify_location_id), ('mk_instance_id', '=', self.mk_instance_id.id)]) if shopify_location_id else False
        return location_id

    def create_sale_order_line_ts(self, shopify_order_line_dict, tax_ids, odoo_product_id, order_id, is_delivery=False, description='', is_discount=False):
        sale_order_line_obj = self.env['sale.order.line']

        price = self._get_currency_based_on_instance_configuration(self.mk_instance_id, shopify_order_line_dict.get('price_set', {}))
        if not price:
            price = shopify_order_line_dict.get('price', 0.0)

        line_vals = {
            'name': description if description else (shopify_order_line_dict.get('name') or odoo_product_id.display_name),
            'product_id': odoo_product_id.id or False,
            'order_id': order_id.id,
            'company_id': order_id.company_id.id,
            'product_uom': odoo_product_id.uom_id and odoo_product_id.uom_id.id or False,
            'price_unit': price,
            'order_qty': shopify_order_line_dict.get('quantity', 1) or 1,
        }

        order_line_data = sale_order_line_obj.prepare_sale_order_line_ts(line_vals)

        order_line_data.update({
            'name': description if description else (shopify_order_line_dict.get('name') or odoo_product_id.display_name),
            'is_delivery': is_delivery,
            'is_discount': is_discount,
            'mk_id': shopify_order_line_dict.get('id')
        })

        if shopify_order_line_dict.get('location_id', False):
            shopify_location_id = self.get_odoo_shopify_location_from_id(shopify_order_line_dict.get('location_id'))
            if not shopify_location_id or (shopify_location_id and not shopify_location_id.order_warehouse_id or not shopify_location_id.location_id):
                raise UserError(_("Please set Warehouse and Location in the Shopify Location {}. Marketplaces > Shopify > Configuration > Locations ".format(shopify_location_id.name)))
            shopify_location_id and order_line_data.update({'shopify_location_id': shopify_location_id.id})

        if order_id and order_id.mk_instance_id.tax_system == 'according_to_marketplace':
            order_line_data.update({'tax_id': tax_ids})

        order_line = sale_order_line_obj.create(order_line_data)
        return order_line

    def get_shopify_delivery_method(self, carrier_name, mk_instance_id):
        carrier_obj = self.env['delivery.carrier']
        carrier_id = carrier_obj.search(['|', ('name', '=', carrier_name), ('shopify_code', '=', carrier_name)], limit=1)
        if not carrier_id:
            carrier_id = carrier_obj.search(['|', ('name', 'ilike', carrier_name), ('shopify_code', 'ilike', carrier_name)], limit=1)
        if not carrier_id:
            carrier_id = carrier_obj.create({'name': carrier_name, 'shopify_code': carrier_name, 'product_id': mk_instance_id.delivery_product_id.id})
        return carrier_id

    def _get_shopify_odoo_taxes(self, mk_instance_id, tax_lines, included=True):
        tax_line_list = []
        for tax_dict in tax_lines:
            if float(tax_dict.get('price', 0.0)) > 0.0:
                tax_line_list.append({'rate': tax_dict.get('rate', '') * 100, 'title': tax_dict.get('title', '')})
        tax_ids = self.get_odoo_tax(mk_instance_id, tax_line_list, included)
        return tax_ids

    def create_shopify_shipping_line(self, mk_instance_id, shopify_order_dict, order_id):

        for shopify_shipping_dict in shopify_order_dict.get('shipping_lines', []):
            tax_ids = False
            if mk_instance_id.tax_system == 'according_to_marketplace':
                tax_line_list = []
                for tax_dict in shopify_shipping_dict.get('tax_lines', []):
                    if float(tax_dict.get('price', 0.0)) > 0.0:
                        tax_line_list.append({'rate': tax_dict.get('rate', '') * 100, 'title': tax_dict.get('title', '')})

                tax_ids = self.get_odoo_tax(mk_instance_id, tax_line_list, shopify_order_dict.get('taxes_included'))
            carrier_name = shopify_shipping_dict.get('title', 'Shopify Delivery Method')
            carrier_id = self.get_shopify_delivery_method(carrier_name, mk_instance_id)
            order_id.write({'carrier_id': carrier_id.id})
            shipping_product = carrier_id.product_id
            order_line = self.create_sale_order_line_ts(shopify_shipping_dict, tax_ids, shipping_product, order_id, is_delivery=True, description=carrier_name)
            discount_amount = sum([self._get_currency_based_on_instance_configuration(self.mk_instance_id, discount_allocation.get('amount_set', {})) for discount_allocation in shopify_shipping_dict.get('discount_allocations') if
                                   discount_allocation])
            if discount_amount > 0.0:
                discount_desc = "Discount: {}".format(mk_instance_id.discount_product_id.name)
                discount_order_line = self.create_sale_order_line_ts({'price': float(discount_amount) * -1, 'id': shopify_order_dict.get('id')},
                                                                     tax_ids, mk_instance_id.discount_product_id, order_id, is_discount=True, description=discount_desc)
                order_line and order_line.write({'shopify_discount_amount': discount_amount, 'related_disc_sale_line_id': discount_order_line.id})

    def prepare_shopify_order_line_wise_location(self, shopify_order_dict):
        for shopify_order_line_dict in shopify_order_dict:
            for fulfillment_dict in shopify_order_dict.get('fulfillments'):
                location_id = fulfillment_dict.get('location_id')
                fulfillment_line = [line_item for line_item in fulfillment_dict.get('line_items', []) if line_item.get('id') == shopify_order_line_dict.get('id')]
                if fulfillment_line:
                    shopify_order_line_dict.update({'location_id': location_id})
        return True

    def _process_shopify_duties_lines(self, duties, order_line, taxes_included, mk_instance_id):
        duties_desc = "Duties: {}".format(order_line.product_id.name)
        for duty in duties:
            tax_ids = self._get_shopify_odoo_taxes(mk_instance_id, duty.get('tax_lines', []), taxes_included)
            amount = self._get_currency_based_on_instance_configuration(self.mk_instance_id, duty.get('price_set', {}))
            if amount > 0.0:
                duties_order_line = self.create_sale_order_line_ts({'price': float(amount), 'id': duty.get('id'), 'quantity': 1}, tax_ids, mk_instance_id.duties_product_id, self,
                                                                   is_discount=False, description=duties_desc)
        return True

    def create_sale_order_line_shopify(self, mk_instance_id, shopify_order_dict, order_id):
        shopify_order_line_list = shopify_order_dict.get('line_items')
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        for shopify_order_line_dict in shopify_order_line_list:
            shopify_product_variant_id = self.get_mk_listing_item_for_mk_order(shopify_order_line_dict.get('variant_id'), mk_instance_id)
            gift_card = shopify_order_line_dict.get('gift_card', False)
            tip = 'tip' in shopify_order_line_dict
            if not shopify_product_variant_id and shopify_order_line_dict.get('variant_id') and not gift_card and not tip:
                log_message = "IMPORT ORDER: Shopify Variant not found for Shopify Order ID {}, Variant ID: {} and Name: {}.".format(order_id.mk_id, shopify_order_line_dict.get('variant_id'), shopify_order_line_dict.get('title', ''))
                self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
                return False
            odoo_product_id = False
            if gift_card:
                odoo_product_id = mk_instance_id.gift_card_product_id or self.env.ref('shopify.shopify_gift_card_product', False)
            elif tip:
                odoo_product_id = mk_instance_id.tip_product_id or self.env.ref('shopify.shopify_tip_product', False)
            elif shopify_product_variant_id:
                odoo_product_id = shopify_product_variant_id.product_id
            tax_ids = False
            taxes_included = shopify_order_dict.get('taxes_included', False)
            if mk_instance_id.tax_system == 'according_to_marketplace':
                tax_ids = self._get_shopify_odoo_taxes(mk_instance_id, shopify_order_line_dict.get('tax_lines', []), taxes_included)
            if shopify_product_variant_id or odoo_product_id:
                order_line = self.create_sale_order_line_ts(shopify_order_line_dict, tax_ids, odoo_product_id, order_id)
            else:
                if not shopify_order_line_dict.get('variant_id', False) and not shopify_order_line_dict.get('product_exist', False):
                    if not mk_instance_id.custom_product_id or not mk_instance_id.custom_storable_product_id:
                        log_message = "IMPORT ORDER: Shopify Custom Product not found for Shopify Order ID {}, Please set Product in Custom Product field in Order tab of Instance " \
                                      "configuration.".format(order_id.mk_id)
                        self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id,
                            mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
                        return False
                    custom_product_id = mk_instance_id.custom_storable_product_id if shopify_order_line_dict.get('requires_shipping', False) else mk_instance_id.custom_product_id
                    order_line = self.create_sale_order_line_ts(shopify_order_line_dict, tax_ids, custom_product_id, order_id)

            discount_amount = sum([self._get_currency_based_on_instance_configuration(self.mk_instance_id, discount_allocation.get('amount_set', {})) for discount_allocation in shopify_order_line_dict.get('discount_allocations') if
                                   discount_allocation])

            if discount_amount > 0.0:
                discount_desc = "Discount: {}".format(order_line.product_id.name)
                discount_order_line = self.create_sale_order_line_ts({'price': float(discount_amount / order_line.product_uom_qty) * -1, 'id': shopify_order_dict.get('id'),
                                                                      'quantity': order_line.product_uom_qty}, tax_ids, mk_instance_id.discount_product_id, order_id, is_discount=True, description=discount_desc)
                order_line and order_line.write({'shopify_discount_amount': discount_amount, 'related_disc_sale_line_id': discount_order_line.id})
            if shopify_order_line_dict.get('duties'):
                self._process_shopify_duties_lines(shopify_order_line_dict.get('duties'), order_line, taxes_included, mk_instance_id)
        self.create_shopify_shipping_line(mk_instance_id, shopify_order_dict, order_id)
        return True

    def fetch_order_fulfillment_location_from_shopify(self, shopify_order_dict):
        # This method set location in the Shopify order line dict.
        fulfillments = shopify.FulfillmentOrders.find(order_id=shopify_order_dict.get('id'))
        fulfillment_list = [fulfillment.to_dict() for fulfillment in fulfillments]
        if fulfillment_list:
            for fulfillment_dict in fulfillment_list:
                if fulfillment_dict.get('status', '') not in ['cancelled', 'incomplete']:
                    for line_item in fulfillment_dict.get('line_items'):
                        [shopify_order_line_item.update({'location_id': fulfillment_dict.get('assigned_location_id'), 'fulfillment_order_line_item_id': line_item.get('id'),
                                                         'fulfillment_order_id': line_item.get('fulfillment_order_id')}) for shopify_order_line_item in
                         shopify_order_dict.get('line_items', []) if shopify_order_line_item.get('id') == line_item.get('line_item_id')]
        return shopify_order_dict

    def _get_customers_for_shopify_order(self, shopify_order_dict, mk_instance_id):
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        partner_obj = self.env['res.partner']
        shopify_order_name = shopify_order_dict.get('name', '')
        company_customer_id = False
        customer_dict = shopify_order_dict.get('customer', {}) or {}
        if mk_instance_id.is_create_company_contact and shopify_order_dict.get('customer', False):
            default_address_dict = customer_dict.get('default_address') if customer_dict.get('default_address', False) else customer_dict
            is_company = True if default_address_dict.get('company', False) else False
            if is_company:
                company_customer_id = partner_obj.create_update_shopify_customers(default_address_dict, mk_instance_id)
        if not customer_dict and shopify_order_dict.get('source_name', '') == 'pos' and mk_instance_id.default_pos_customer_id:
            customer_id = mk_instance_id.default_pos_customer_id
        else:
            customer_id = partner_obj.create_update_shopify_customers(customer_dict, mk_instance_id, parent_id=company_customer_id)
        if not customer_id:
            log_message = "IMPORT ORDER: Customer not found in Shopify Order No: {}({})".format(shopify_order_name, shopify_order_dict.get('id'))
            self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
            return False, False, False
        if not shopify_order_dict.get('billing_address', customer_dict):
            billing_customer_id = customer_id
        else:
            billing_customer_id = partner_obj.create_update_shopify_customers(shopify_order_dict.get('billing_address', customer_dict), mk_instance_id, type='invoice', parent_id=company_customer_id or customer_id)
        if not shopify_order_dict.get('shipping_address', customer_dict):
            shipping_customer_id = customer_id
        else:
            shipping_customer_id = partner_obj.create_update_shopify_customers(shopify_order_dict.get('shipping_address', customer_dict), mk_instance_id, type='delivery', parent_id=company_customer_id or customer_id)
        return customer_id, billing_customer_id, shipping_customer_id

    def _update_warehouse_based_on_shopify_location(self):
        # Update order's warehouse based on shopify location.
        shopify_location_id = self.order_line.mapped('shopify_location_id')
        if len(shopify_location_id) > 1:
            shopify_location_id = shopify_location_id[0]
        if shopify_location_id and shopify_location_id.order_warehouse_id:
            self.warehouse_id = shopify_location_id.order_warehouse_id.id

    def _get_shopify_refund_line_ids(self, refund_data_line):
        refund_line_item_dict = {}
        for refund_line_item in refund_data_line.get('refund_line_items', []):
            quantity = refund_line_item.get('quantity')
            line_item_id = refund_line_item.get('line_item_id')
            if refund_line_item_dict.get(line_item_id):
                refund_line_item_dict.update({line_item_id: (refund_line_item_dict.get(line_item_id) + quantity)})
            else:
                refund_line_item_dict.update({line_item_id: quantity})
        return refund_line_item_dict

    def _update_credit_note_from_shopify_refund_data(self, refund_invoice, refund_line_item_dict):
        to_remove_move_lines = self.env['account.move.line']
        previous_mk_id = ''
        for new_move_line in refund_invoice.invoice_line_ids:
            mk_id = int(new_move_line.sale_line_ids.mk_id)
            if mk_id and refund_line_item_dict.get(mk_id):
                new_move_line.with_context(check_move_validity=False).write({'quantity': refund_line_item_dict.get(mk_id)})
            elif new_move_line.product_id.id == self.mk_instance_id.discount_product_id.id and refund_line_item_dict.get(previous_mk_id):
                new_move_line.with_context(check_move_validity=False).write({'quantity': previous_move_line.quantity, 'price_unit': -(previous_move_line.price_unit / 2)})
            elif new_move_line.product_id.id == self.mk_instance_id.discount_product_id.id and not refund_line_item_dict.get(previous_mk_id):
                new_move_line.with_context(check_move_validity=False).write({'quantity': 0})
            else:
                to_remove_move_lines += new_move_line
            previous_move_line = new_move_line
            previous_mk_id = int(new_move_line.sale_line_ids.mk_id)
        to_remove_move_lines and to_remove_move_lines.with_context(check_move_validity=False).write({'quantity': 0})
        return True

    def _get_currency_based_on_instance_configuration(self, mk_instance_id, amount_dict):
        if mk_instance_id.use_marketplace_currency:
            amount = float(amount_dict.get('presentment_money', {}).get('amount', 0.0)) or 0.0
        else:
            amount = float(amount_dict.get('shop_money', {}).get('amount', 0.0)) or 0.0
        return amount

    def _create_order_adjustment_line_shopify(self, refund_data_line, refund_invoice, taxes_included):
        account_move_line_obj = self.env['account.move.line']
        order_adjustments = refund_data_line.get('order_adjustments')
        if not order_adjustments:
            return False

        for adjustment in order_adjustments:
            tax_ids = []
            if adjustment.get('kind') == 'shipping_refund':
                delivery_line = self.order_line.filtered(lambda l: l.product_id == self.mk_instance_id.delivery_product_id)
                tax_ids = delivery_line.tax_id.ids
            total_adjustment = self._get_currency_based_on_instance_configuration(self.mk_instance_id, adjustment.get('amount_set'))
            if taxes_included:
                total_adjustment += self._get_currency_based_on_instance_configuration(self.mk_instance_id, adjustment.get('tax_amount_set'))
            adjustment_product_id = self.env.ref('base_marketplace.marketplace_adjustment_product', False)
            adjustment_move_vals = {'name': adjustment.get('reason', 'Refund Adjustment'), 'product_id': adjustment_product_id.id,
                                    'quantity': 1, 'price_unit': abs(total_adjustment), 'move_id': refund_invoice.id, 'partner_id': refund_invoice.partner_id.id, 'tax_ids': tax_ids}
            adjustment_move_vals = account_move_line_obj.new(adjustment_move_vals)
            adjustment_move_vals._onchange_product_id()
            new_vals = account_move_line_obj._convert_to_write(adjustment_move_vals._cache)
            new_vals.update({'quantity': 1, 'price_unit': abs(total_adjustment), 'tax_ids': tax_ids})
            account_move_line_obj.with_context(check_move_validity=False).create(new_vals)

    def _get_shipping_refund_amount_shopify(self, refund_data_line):
        shipping_amount = 0.0
        for adjustment in refund_data_line.get('order_adjustments'):
            if adjustment.get('kind') == 'shipping_refund':
                shipping_amount = float(adjustment.get('amount'))
        return shipping_amount

    def _create_shopify_credit_note_and_adjust_amount(self, shopify_order_dict, refund_data_line, invoice_ids):
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        refund_line_item_dict = self._get_shopify_refund_line_ids(refund_data_line)
        date = self.env.context.get('date', convert_shopify_datetime_to_utc(refund_data_line.get('created_at')))
        move_reversal = self.env['account.move.reversal'].with_context(active_model="account.move", active_ids=invoice_ids.ids).create({
            'reason': refund_data_line.get('note', 'Refunded from Shopify') or 'Refunded from Shopify',
            'refund_method': 'refund',
            'date': date,
            'journal_id': invoice_ids[0].journal_id.id
        })
        move_reversal.reverse_moves()
        refund_invoice = move_reversal.new_move_ids
        refund_invoice.write({'shopify_refund_id': refund_data_line.get('id')})
        self._update_credit_note_from_shopify_refund_data(refund_invoice, refund_line_item_dict)
        taxes_included = shopify_order_dict.get('taxes_included')
        self._create_order_adjustment_line_shopify(refund_data_line, refund_invoice, taxes_included)
        if not self._check_shopify_descripency(refund_data_line, refund_invoice):
            shopify_refund_amount = sum([float(transaction.get('amount', 0.0)) for transaction in refund_data_line.get('transactions') if transaction.get('status') == 'success'])
            log_message = "Automatic credit note creation is skipped due to a discrepancy between the Shopify refund total({}) and Odoo's credit note total({}). Please create the credit note in Odoo manually for Shopify Order {}.".format(
                shopify_refund_amount, refund_invoice.amount_total, shopify_order_dict.get('name'))
            self.env['mk.log'].create_update_log(mk_instance_id=self.mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict={
                'error': [{'log_message': 'IMPORT ORDER: {}'.format(log_message), 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
            queue_line_id and queue_line_id.queue_id.create_activity_action(log_message)
            refund_invoice.unlink()
            return False
        container = {'records': refund_invoice}
        refund_invoice.with_context(**{'check_move_validity': False})._recompute_dynamic_lines(container)
        if refund_invoice.state == 'draft':
            refund_invoice.action_post()
        if self.env.context.get('refund_journal_id', False):
            self.env['account.payment.register'].with_context(active_model='account.move', active_ids=refund_invoice.ids).create({'journal_id': self.env.context.get('refund_journal_id')})._create_payments()
        return True

    def _create_shopify_credit_note(self, shopify_order_dict):
        account_move_obj = self.env['account.move']
        invoice_ids = self.invoice_ids.filtered(lambda x: x.move_type == 'out_invoice' and x.state == 'posted')
        for refund_data_line in shopify_order_dict.get('refunds'):
            existing_refund_id = account_move_obj.search([("shopify_refund_id", "=", refund_data_line.get('id')), ("mk_instance_id", "=", self.mk_instance_id.id)])
            if existing_refund_id:
                continue
            self._create_shopify_credit_note_and_adjust_amount(shopify_order_dict, refund_data_line, invoice_ids)
        return True

    def _check_validation_to_process_credit_note(self, shopify_order_dict):
        if not self.order_workflow_id.is_create_credit_note:
            return False

        if not shopify_order_dict.get('financial_status', '') in ['refunded', 'partially_refunded']:
            return False

        if not self.invoice_ids:
            _logger.info("SHOPIFY CREDIT NOTE: Cannot create Credit note because related invoice not found for Order {}".format(self.name))
            return False

        invoice_ids = self.invoice_ids.filtered(lambda x: x.move_type == 'out_invoice' and x.state == 'posted')
        if not invoice_ids:
            _logger.info("SHOPIFY CREDIT NOTE: Cannot create Credit note because related invoice not found for Order {}".format(self.name))
            return False

        if not self._check_invoice_policy_ordered():
            _logger.info("SHOPIFY CREDIT NOTE: Cannot create Credit note because some product is not delivered for Order {}".format(self.name))
            return False

        # If there is any manual refund created, then we are not create automatic refund according to Shopify.
        if self.invoice_ids.filtered(lambda x: x.move_type == 'out_refund' and not x.shopify_refund_id):
            _logger.info("SHOPIFY CREDIT NOTE: Cannot create Credit note because there is already credit note created for Order {}".format(self.name))
            return False
        return True

    def _process_shopify_refund_in_odoo(self, shopify_order_dict):
        if not self.env.context.get('skip_check_transaction', False):
            trans_list = [transaction for transaction in shopify_order_dict.get('transactions', []) if transaction and transaction.get('status') == 'success' and transaction.get('kind') in ['capture', 'sale']]
            if not trans_list:
                return False

        if not self._check_validation_to_process_credit_note(shopify_order_dict):
            return False

        self._create_shopify_credit_note(shopify_order_dict)
        return True

    def _process_shopify_draft_orders(self, shopify_order_dict):
        if not self.state == 'draft':
            return False
        shopify_order_line_list = shopify_order_dict.get('line_items')
        is_importable, financial_workflow_config_id = self.check_validation_for_import_sale_orders(shopify_order_line_list, self.mk_instance_id, shopify_order_dict)
        if not is_importable:
            return False
        self.order_workflow_id = financial_workflow_config_id.order_workflow_id
        self.with_context(create_date=convert_shopify_datetime_to_utc(shopify_order_dict.get("processed_at", "")), order_dict=shopify_order_dict).do_marketplace_workflow_process()
        return "IMPORT ORDER: Shopify Order {}({}) is successfully updated.".format(shopify_order_dict.get('name', ''), shopify_order_dict.get('id'))

    def process_import_order_from_shopify_ts(self, shopify_order_dict, mk_instance_id):
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        shopify_order_name = shopify_order_dict.get('name', '')
        existing_order_id = self.search([('mk_id', '=', shopify_order_dict.get('id')), ('mk_instance_id', '=', mk_instance_id.id)])
        if existing_order_id:
            fulfillment_status = shopify_order_dict.get('fulfillment_status', 'unfulfilled') or 'unfulfilled'
            log_message = existing_order_id._process_shopify_draft_orders(shopify_order_dict)  # process draft orders
            existing_order_id.with_context(operation_type='import', mk_log_id=mk_log_id).auto_validate_shopify_delivery_order(shopify_order_dict.get('fulfillments'))
            existing_order_id.with_context(skip_check_transaction=True)._process_shopify_refund_in_odoo(shopify_order_dict)  # create refund according to the Shopify.
            shopify_tag_vals = existing_order_id.prepage_order_tag_vals(shopify_order_dict.get('tags'))

            update_order_vals = {'shopify_financial_status': shopify_order_dict.get('financial_status'),
                                 'fulfillment_status': fulfillment_status,
                                 'updated_in_marketplace': True if fulfillment_status == 'fulfilled' else False}
            if shopify_tag_vals and shopify_order_dict.get('tags'):
                update_order_vals.update(shopify_tag_vals)

            existing_order_id.write(update_order_vals)
            if not log_message:
                log_message = "IMPORT ORDER: Shopify Order {}({}) is already imported.".format(shopify_order_name, shopify_order_dict.get('id'))
            self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id,
                mk_log_line_dict={'success': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
            return existing_order_id

        if not self.check_marketplace_order_date(convert_shopify_datetime_to_utc(shopify_order_dict.get("processed_at", "")), mk_instance_id):
            log_message = "IMPORT ORDER: Shopify Order {}({}) is skipped due to order created prior to the date configured on Import Order After in Instance.".format(shopify_order_name, shopify_order_dict.get('id'))
            self.env['mk.log'].create_update_log(mk_log_id=mk_log_id, mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
            return False

        self.fetch_order_transaction_from_shopify(shopify_order_dict)  # Fetch payment transactions from Shopify and add to the order dict.

        shopify_order_line_list = shopify_order_dict.get('line_items')
        is_importable, financial_workflow_config_id = self.check_validation_for_import_sale_orders(shopify_order_line_list, mk_instance_id, shopify_order_dict)
        if not is_importable:
            return False

        customer_id, billing_customer_id, shipping_customer_id = self.with_context(mk_log_id=mk_log_id, queue_line_id=queue_line_id or False)._get_customers_for_shopify_order(shopify_order_dict, mk_instance_id)
        if not customer_id:
            return False

        customer = self.new({'partner_id': customer_id.id})
        customer.onchange_partner_id()
        customer_dict = customer._convert_to_write({name: customer[name] for name in customer._cache})

        self.fetch_order_fulfillment_location_from_shopify(shopify_order_dict)  # Fetch fulfillment location for order lines from Shopify and set in order dict.

        order_id = self.create_shopify_sale_order(shopify_order_dict, mk_instance_id, customer_id, billing_customer_id, shipping_customer_id, financial_workflow_config_id)
        if not order_id:
            return False

        if not order_id.create_sale_order_line_shopify(mk_instance_id, shopify_order_dict, order_id):
            order_id.unlink()
            return False

        order_id._update_warehouse_based_on_shopify_location()

        if mk_instance_id.is_fetch_fraud_analysis_data:
            self.env['shopify.fraud.analysis'].create_fraud_analysis(shopify_order_dict.get('id'), order_id)
        if not order_id.is_fraud_order:
            order_id.with_context(create_date=convert_shopify_datetime_to_utc(shopify_order_dict.get("processed_at", "")), order_dict=shopify_order_dict).do_marketplace_workflow_process()
            order_id.order_workflow_id.is_validate_invoice and order_id._process_shopify_refund_in_odoo(shopify_order_dict)
        if order_id:
            log_message = 'IMPORT ORDER: Successfully imported marketplace order {}({})'.format(order_id.name, order_id.mk_id)
            self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict={'success': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
        return order_id

    def fetch_order_transaction_from_shopify(self, shopify_order_dict):
        transactions = shopify.Transaction.find(order_id=shopify_order_dict.get('id'))
        trans_list = [transaction.to_dict() for transaction in transactions if transaction and transaction.status == 'success' and transaction.kind in ['capture', 'sale']]
        if trans_list:
            shopify_order_dict.update({'transactions': trans_list})
        return shopify_order_dict

    def import_shopify_order_by_id(self, shopify_order_list, mk_instance_id):
        res_id_list = []
        mk_log_id = self.env.context.get('mk_log_id', False)
        for shopify_order in shopify_order_list:
            shopify_order_dict = shopify_order.to_dict()
            try:
                with self.env.cr.savepoint():
                    order_id = self.with_context(mk_log_id=mk_log_id).process_import_order_from_shopify_ts(shopify_order.to_dict(), mk_instance_id)
                    order_id and res_id_list.append(order_id.id)
            except Exception as e:
                log_traceback_for_exception()
                self._cr.rollback()
                log_message = "PROCESS ORDER: Error while processing Marketplace Order {} ({}), ERROR: {}".format(shopify_order_dict.get('name'), shopify_order_dict.get('id'), e)
                if not mk_log_id.exists():
                    mk_log_id = self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, operation_type='import')
                self.env['mk.log'].create_update_log(mk_log_id=mk_log_id, mk_log_line_dict={'error': [{'log_message': log_message}]})
            self._cr.commit()
        return res_id_list

    def create_shopify_order_queue_job(self, mk_instance_id, shopify_order_list):
        res_id_list = []
        batch_size = mk_instance_id.queue_batch_limit or 100
        for shopify_orders in tools.split_every(batch_size, shopify_order_list):
            queue_id = mk_instance_id.action_create_queue(type='order')
            for order in shopify_orders:
                shopify_order_dict = order.to_dict()
                name = shopify_order_dict.get('name', '') or ''
                line_vals = {
                    'mk_id': shopify_order_dict.get('id') or '',
                    'state': 'draft',
                    'name': name.strip(),
                    'data_to_process': pprint.pformat(shopify_order_dict),
                    'mk_instance_id': mk_instance_id.id,
                }
                queue_id.action_create_queue_lines(line_vals)
            res_id_list.append(queue_id.id)
        return res_id_list

    def shopify_import_orders(self, mk_instance_ids, from_date=False, to_date=False, mk_order_id=False):
        res_id_list, action = [], False
        if not isinstance(mk_instance_ids, list):
            mk_instance_ids = [mk_instance_ids]
        for mk_instance_id in mk_instance_ids:
            mk_instance_id.connection_to_shopify()
            mk_log_id = self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, operation_type='import')
            if not from_date:
                from_date = mk_instance_id.last_order_sync_date if mk_instance_id.last_order_sync_date else fields.Datetime.now() - timedelta(3)
            if not to_date:
                to_date = fields.Datetime.now()
            from_date = from_date - timedelta(minutes=10)
            shopify_fulfillment_status_ids = mk_instance_id.fulfillment_status_ids
            shopify_order_list = self.fetch_orders_from_shopify(from_date, to_date, shopify_fulfillment_status_ids, mk_order_id=mk_order_id)
            if mk_order_id and shopify_order_list:
                res_id_list = self.with_context(mk_log_id=mk_log_id).import_shopify_order_by_id(shopify_order_list, mk_instance_id)
                if not mk_log_id.log_line_ids and not self.env.context.get('log_id', False):
                    mk_log_id.unlink()
                self._cr.commit()
                if res_id_list:
                    return mk_instance_id.action_open_model_view(res_id_list, 'sale.order', 'Shopify Order')
                if mk_log_id.exists():
                    return mk_instance_id.action_open_model_view(mk_log_id.ids, 'mk.log', 'Log')
                return True
            if shopify_order_list:
                res_id_list = self.create_shopify_order_queue_job(mk_instance_id, shopify_order_list)
            if not mk_log_id.log_line_ids and not self.env.context.get('log_id', False):
                mk_log_id.unlink()
            mk_instance_id.last_order_sync_date = to_date
        if res_id_list:
            action = mk_instance_id.action_open_model_view(res_id_list, 'mk.queue.job', 'Shopify Order Queue')
        return action

    def update_shopify_order_line_location(self, shopify_order_dict):
        for order_line_dict in shopify_order_dict.get('line_items'):
            location_id = order_line_dict.get('location_id')
            mk_id = order_line_dict.get('id')
            order_line_id = self.order_line.search([('mk_id', '=', mk_id)])
            if order_line_id and location_id:
                shopify_location_id = self.get_odoo_shopify_location_from_id(location_id)
                if shopify_location_id:
                    order_line_id.shopify_location_id = shopify_location_id.id
        return True

    def get_shopify_pickings(self, mk_instance_id):
        picking_ids = self.env["stock.picking"].search([('updated_in_marketplace', '=', False),
                                                        ('location_dest_id.usage', '=', 'customer'),
                                                        '|',
                                                        ('mk_instance_id', '=', mk_instance_id.id),
                                                        ('backorder_id.mk_instance_id', '=', mk_instance_id.id),
                                                        ('cancel_in_marketplace', '=', False),
                                                        ('state', '=', 'done'),
                                                        ('is_marketplace_exception', '=', False)], order='date')
        return picking_ids

    def shopify_update_order_status(self, mk_instance_ids, manual_process=True):
        if not isinstance(mk_instance_ids, list):
            mk_instance_ids = [mk_instance_ids]
        for mk_instance_id in mk_instance_ids:
            mk_instance_id.connection_to_shopify()
            if self.env.context.get('active_model', '') == 'mk.instance':
                manual_process = False
            picking_ids = self.get_shopify_pickings(mk_instance_id)
            for picking in picking_ids:
                # Updating instance in a case if we have backorder and backorder doesn't have instance set.
                if not picking.mk_instance_id:
                    picking.write({'mk_instance_id': mk_instance_id.id})
                picking.process_update_order_status_shopify(manual_process)
        return True

    def cancel_in_shopify(self):
        view = self.env.ref('shopify.cancel_in_shopify_form_view')
        context = dict(self._context)
        context.update({'active_model': 'sale.order', 'active_id': self.id, 'active_ids': self.ids})
        return {
            'name': _('Cancel Order In Shopify'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mk.cancel.order',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': context
        }

    def refund_in_shopify(self):
        cancel_order_wizard_obj = self.env['mk.cancel.order']
        view = self.env.ref('shopify.refund_in_shopify_form_view')
        context = dict(self._context)
        context.update({'active_model': 'sale.order', 'active_id': self.id, 'active_ids': self.ids})
        wizard_vals = cancel_order_wizard_obj.shopify_refund_wizard_default_get(self)
        res_id = cancel_order_wizard_obj.create(wizard_vals)
        return {
            'name': _('Refund Order In Shopify'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mk.cancel.order',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': res_id.id,
            'context': context
        }

    def cron_auto_import_shopify_orders(self, mk_instance_id):
        mk_instance_id = self.env['mk.instance'].browse(mk_instance_id)
        if mk_instance_id.state == 'confirmed':
            self.shopify_import_orders(mk_instance_id)
        return True

    def cron_auto_update_order_status(self, mk_instance_id):
        mk_instance_id = self.env['mk.instance'].browse(mk_instance_id)
        if mk_instance_id.state == 'confirmed':
            mk_log_id = self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, operation_type='export')
            mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
            self.with_context(mk_log_line_dict=mk_log_line_dict, mk_log_id=mk_log_id).shopify_update_order_status(mk_instance_id, manual_process=False)
            self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict=mk_log_line_dict)
            if not mk_log_id.log_line_ids and not self.env.context.get('log_id', False):
                mk_log_id.unlink()
        return True

    def shopify_open_sale_order_in_marketplace(self):
        marketplace_url = self.mk_instance_id.shop_url + '/admin/orders/' + self.mk_id
        return marketplace_url

    def shopify_reconcile_invoice(self, order_workflow_id, invoice_id, transaction):
        amount = float(transaction.get('amount', 0.0)) if transaction and isinstance(transaction, dict) and transaction.get('amount', 0.0) else 0.0
        if invoice_id.amount_residual < amount:
            amount = invoice_id.amount_residual
        payment_vals = self.with_context(transaction=transaction)._prepare_payment_vals(order_workflow_id, invoice_id, amount=amount)
        payment = self.env['account.payment'].create(payment_vals)
        liquidity_lines, counterpart_lines, writeoff_lines = payment._seek_for_lines()
        payment.action_post()
        lines = (counterpart_lines + invoice_id.line_ids.filtered(lambda line: line.account_internal_type == 'receivable'))
        source_balance = abs(sum(lines.mapped('amount_residual')))
        payment_balance = abs(sum(counterpart_lines.mapped('balance')))
        delta_balance = source_balance - payment_balance

        # Balance are already the same.
        if not invoice_id.company_currency_id.is_zero(delta_balance):
            lines.reconcile()

    def shopify_pay_and_reconcile(self, order_workflow_id, invoice_id):
        transactions = self.env.context.get('order_dict', {}).get('transactions', {})
        if not transactions:
            self.mk_instance_id.connection_to_shopify()
            shopify_transactions = shopify.Transaction.find(order_id=self.mk_id)
            transactions = [transaction.to_dict() for transaction in shopify_transactions if transaction and transaction.status == 'success' and transaction.kind in ['capture', 'sale']]
        if transactions:
            for transaction in transactions:
                financial_status = self.env.context.get('order_dict', {}).get('financial_status')
                payment_gateway = transaction.get('gateway', 'Untitled') or 'Untitled'
                shopify_payment_gateway_id = self.env['shopify.payment.gateway.ts'].search([('code', '=', payment_gateway), ('mk_instance_id', '=', self.mk_instance_id.id)], limit=1)
                shopify_workflow_id = self.env['shopify.financial.workflow.config'].search(
                    [('payment_gateway_id', '=', shopify_payment_gateway_id.id), ('financial_status', '=', financial_status), ('mk_instance_id', '=', self.mk_instance_id.id)], limit=1)
                self.shopify_reconcile_invoice(shopify_workflow_id.order_workflow_id, invoice_id, transaction)
        else:
            self.shopify_reconcile_invoice(order_workflow_id, invoice_id, False)
        return True

    def shopify_get_order_fulfillment_status(self):
        return True if self.fulfillment_status == 'fulfilled' else False

    def _force_set_quantity_done(self, fulfillment, picking):
        if not picking:
            return False
        process = False
        queue_line_id = self.env.context.get('queue_line_id', False)
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        for fulfillment_line in fulfillment.get('line_items', []):
            order_line = self.order_line.filtered(lambda x: x.mk_id == str(fulfillment_line.get('id', '')))
            if order_line.product_uom_qty == order_line.qty_delivered:
                continue
            mrp_installed = self.env['ir.module.module'].sudo().search([('name', '=', 'mrp'), ('state', '=', 'installed')])
            product_id = order_line.product_id
            bom_lines = False
            to_fulfill_quantity = float(fulfillment_line.get('quantity'))
            if mrp_installed:
                bom = self.env['mrp.bom'].sudo()._bom_find(products=product_id, company_id=self.company_id.id, bom_type='phantom')[product_id]
                if bom:
                    factor = product_id.uom_id._compute_quantity(to_fulfill_quantity, bom.product_uom_id) / bom.product_qty
                    boms, bom_lines = bom.sudo().explode(product_id, factor, picking_type=bom.picking_type_id)
            if bom_lines:
                for bom_line, line_data in bom_lines:
                    stock_move = picking.move_lines.filtered(lambda x: x.sale_line_id.id == order_line.id and x.product_id == bom_line.product_id)
                    if stock_move:
                        stock_move._action_assign()
                        stock_move._set_quantity_done(line_data['qty'])
                        process = True
            else:
                stock_move = picking.move_lines.filtered(lambda x: x.sale_line_id.id == order_line.id)
                if stock_move:
                    stock_move._action_assign()
                    stock_move._set_quantity_done(min(to_fulfill_quantity, stock_move.product_uom_qty))
                    process = True
            if process:
                log_message = _('UPDATE ORDER STATUS IN ODOO: Product {} with {} Quantity successfully shipped in Odoo for Sale Order {} and Delivery Order {}.'.format(product_id.display_name, to_fulfill_quantity, self.name, picking.name))
                mk_log_line_dict['success'].append({'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False})
        return process

    def _update_delivery_order_detail_shopify(self, fulfillment, picking_id):
        tracking_ref_list = []
        mk_log_id = self.env.context.get('mk_log_id', False)
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        shopify_fulfillment_id = str(fulfillment.get('id', ''))
        for tracking_number in fulfillment.get('tracking_numbers', False):
            tracking_ref_list.append(tracking_number)
        tracking_ref = tracking_ref_list and ','.join(tracking_ref_list) or False
        picking_vals = {'updated_in_marketplace': True, 'is_marketplace_exception': False, 'exception_message': False}
        if fulfillment.get('tracking_company', False):
            carrier_id = self.get_shopify_delivery_method(fulfillment.get('tracking_company'), self.mk_instance_id)
            carrier_id and picking_vals.update({'carrier_id': carrier_id.id})
        if not picking_id.carrier_tracking_ref and tracking_ref:
            picking_vals.update({'carrier_tracking_ref': tracking_ref, 'shopify_fulfillment_id': shopify_fulfillment_id})
        picking_id.write(picking_vals)
        self.env['mk.log'].create_update_log(mk_instance_id=self.mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict=mk_log_line_dict)
        return picking_id

    def auto_validate_shopify_delivery_order(self, fulfillments):
        """
        Auto validate Shopify delivery orders.
        :param fulfillments: List of Shopify fulfillments.
        """
        # Get the context variables.
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})

        # Validate each fulfillment.
        for fulfillment in fulfillments:
            shopify_fulfillment_id = str(fulfillment.get('id', ''))
            if shopify_fulfillment_id in self.picking_ids.mapped('shopify_fulfillment_id'):
                continue

            # Get the pickings for the fulfillment.
            picking_ids = self.picking_ids.filtered(lambda p: p.location_dest_id.usage == "customer" and p.state in ['confirmed', 'assigned'])
            for picking_id in picking_ids:

                # Quality check validation.
                if hasattr(picking_id, "quality_check_todo"):
                    if getattr(picking_id, "quality_check_todo"):
                        log_message = _('UPDATE ORDER STATUS IN ODOO: Cannot auto fulfill Shopify Order {}, ERROR: {} {}. Please check quality manually.'.format(self.name, picking_id.name, 'Failed Due To Open Quality Checks For Delivery Order'))
                        self.env['mk.log'].create_update_log(mk_log_id=mk_log_id, mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
                        continue

                # Force the quantity done for the fulfillment.
                process = self.with_context(mk_log_line_dict=mk_log_line_dict, queue_line_id=queue_line_id, mk_log_id=mk_log_id)._force_set_quantity_done(fulfillment, picking_id)
                if not process:
                    continue

                # Validate the picking.
                res = picking_id.with_context(skip_sms=True).button_validate()
                if isinstance(res, dict):
                    if res.get('res_model', False):
                        record = self.env[res.get('res_model')].with_context(res.get("context")).create({})
                        record.process()

                # Update the picking if it is done.
                if picking_id.state == "done":
                    self._update_delivery_order_detail_shopify(fulfillment, picking_id)
        return True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    shopify_discount_amount = fields.Float("Shopify Discount Amount")
    shopify_location_id = fields.Many2one("shopify.location.ts", "Shopify Location", copy=False)
