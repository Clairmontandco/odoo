import logging
from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger("Teqstars:Shopify")


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def create_sale_order_line_ts(self, shopify_order_line_dict, tax_ids, odoo_product_id, order_id, is_delivery=False, description='', is_discount=False):
        # override method to skip update shopify description in the sale order line.
        sale_order_line_obj = self.env['sale.order.line']

        price = self._get_currency_based_on_instance_configuration(self.mk_instance_id, shopify_order_line_dict.get('price_set', {}))
        if not price:
            price = shopify_order_line_dict.get('price', 0.0)

        line_vals = {
            'product_id': odoo_product_id.id or False,
            'order_id': order_id.id,
            'company_id': order_id.company_id.id,
            'product_uom': odoo_product_id.uom_id and odoo_product_id.uom_id.id or False,
            'price_unit': price,
            'order_qty': shopify_order_line_dict.get('quantity', 1) or 1,
        }

        order_line_data = sale_order_line_obj.prepare_sale_order_line_ts(line_vals)

        order_line_data.update({
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

    def _get_customers_for_shopify_order(self, shopify_order_dict, mk_instance_id):
        # override method to add store name in the customer value.
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        partner_obj = self.env['res.partner']
        shopify_order_name = shopify_order_dict.get('name', '')
        store_name = False
        for attribute in shopify_order_dict.get('note_attributes'):
            if attribute.get('name', '') == 'Store name' and attribute.get('value', False):
                store_name = attribute.get('value', False) or False
                break
        if store_name:
            shopify_order_dict.get('customer', {}).update({'name': store_name})
            shopify_order_dict.get('customer', {}).get('default_address', {}).update({'name': store_name})
            if shopify_order_dict.get('billing_address', False) or False:
                shopify_order_dict.get('billing_address').update({'name': store_name})
            if shopify_order_dict.get('shipping_address', False) or False:
                shopify_order_dict.get('shipping_address').update({'name': store_name})
        company_customer_id = False
        if mk_instance_id.is_create_company_contact and shopify_order_dict.get('customer', False):
            default_address_dict = shopify_order_dict.get('customer', {}).get('default_address') if shopify_order_dict.get('customer', {}).get('default_address',
                                                                                                                                               False) else shopify_order_dict.get('customer',
                                                                                                                                                                                  {})
            is_company = True if default_address_dict.get('company', False) else False
            if is_company:
                company_customer_id = partner_obj.create_update_shopify_customers(default_address_dict, mk_instance_id)
        if not shopify_order_dict.get('customer', False) and shopify_order_dict.get('source_name', '') == 'pos' and mk_instance_id.default_pos_customer_id:
            customer_id = mk_instance_id.default_pos_customer_id
        else:
            customer_id = partner_obj.create_update_shopify_customers(shopify_order_dict.get('customer', {}), mk_instance_id, parent_id=company_customer_id)
        if not customer_id:
            log_message = "IMPORT ORDER: Customer not found in Shopify Order No: {}({})".format(shopify_order_name, shopify_order_dict.get('id'))
            self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id,
                                                 mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
            return False, False, False
        if not shopify_order_dict.get('billing_address', shopify_order_dict.get('customer', False)):
            billing_customer_id = customer_id
        else:
            billing_customer_id = partner_obj.create_update_shopify_customers(shopify_order_dict.get('billing_address', shopify_order_dict.get('customer', {})), mk_instance_id,
                                                                              type='invoice', parent_id=company_customer_id or customer_id)
        if not shopify_order_dict.get('shipping_address', shopify_order_dict.get('customer', False)):
            shipping_customer_id = customer_id
        else:
            shipping_customer_id = partner_obj.create_update_shopify_customers(shopify_order_dict.get('shipping_address', shopify_order_dict.get('customer', {})), mk_instance_id,
                                                                               type='delivery', parent_id=company_customer_id or customer_id)
        return customer_id, billing_customer_id, shipping_customer_id

    def create_sale_order_line_shopify(self, mk_instance_id, shopify_order_dict, order_id):
        # Override method to use existing Faire Commission and Faire processing fee products instead of custom line products
        shopify_order_line_list = shopify_order_dict.get('line_items')
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        for shopify_order_line_dict in shopify_order_line_list:
            shopify_product_variant_id = self.get_mk_listing_item_for_mk_order(shopify_order_line_dict.get('variant_id'), mk_instance_id)
            gift_card = shopify_order_line_dict.get('gift_card', False)
            tip = 'tip' in shopify_order_line_dict
            if not shopify_product_variant_id and shopify_order_line_dict.get('variant_id') and not gift_card and not tip:
                log_message = "IMPORT ORDER: Shopify Variant not found for Shopify Order ID {}, Variant ID: {} and Name: {}.".format(order_id.mk_id,
                                                                                                                                     shopify_order_line_dict.get('variant_id'),
                                                                                                                                     shopify_order_line_dict.get('title', ''))
                self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id,
                                                     mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
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

                    custom_product_id, listing_item_id = self.env['mk.listing'].get_odoo_product_variant_and_listing_item(mk_instance_id, shopify_order_line_dict.get("id", ""),
                                                                                                                          shopify_order_line_dict.get("barcode", ""),
                                                                                                                          shopify_order_line_dict.get("sku", ""))
                    if not custom_product_id:
                        custom_product_id = mk_instance_id.custom_storable_product_id if shopify_order_line_dict.get('requires_shipping', False) else mk_instance_id.custom_product_id
                    order_line = self.create_sale_order_line_ts(shopify_order_line_dict, tax_ids, custom_product_id, order_id)

            discount_amount = sum([self._get_currency_based_on_instance_configuration(self.mk_instance_id, discount_allocation.get('amount_set', {})) for discount_allocation in
                                   shopify_order_line_dict.get('discount_allocations') if
                                   discount_allocation])

            if discount_amount > 0.0:
                discount_desc = "Discount: {}".format(order_line.product_id.name)
                discount_order_line = self.create_sale_order_line_ts({'price': float(discount_amount / order_line.product_uom_qty) * -1, 'id': shopify_order_dict.get('id'),
                                                                      'quantity': order_line.product_uom_qty}, tax_ids, mk_instance_id.discount_product_id, order_id, is_discount=True,
                                                                     description=discount_desc)
                order_line and order_line.write({'shopify_discount_amount': discount_amount, 'related_disc_sale_line_id': discount_order_line.id})
            if shopify_order_line_dict.get('duties'):
                self._process_shopify_duties_lines(shopify_order_line_dict.get('duties'), order_line, taxes_included, mk_instance_id)
        self.create_shopify_shipping_line(mk_instance_id, shopify_order_dict, order_id)
        return True
