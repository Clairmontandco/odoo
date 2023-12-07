import logging
import psycopg2
from odoo.http import request
from odoo import api, http, registry, SUPERUSER_ID, _
from odoo.addons.shopify.models.misc import log_traceback_for_exception

_logger = logging.getLogger("Teqstars:Shopify")


class ShopifyWebhook(http.Controller):

    @http.route('/shopify/webhook/notification/<string:db_name>/<int:mk_instance_id>', type='json', auth="public", csrf=False)
    def shopify_webhook_process(self, db_name, mk_instance_id, **kwargs):
        webhook_type = request.httprequest.headers.get('X-Shopify-Topic', False)
        try:
            db_registry = registry(db_name)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                response = request.jsonrequest or {}
                mk_instance_id = env['mk.instance'].browse(int(mk_instance_id))
                if mk_instance_id.state != 'confirmed' or not mk_instance_id.webhook_ids.filtered(lambda webhook: webhook.webhook_event == webhook_type):
                    return {'status': 'Instance {} is not in Confirmed State.'.format(mk_instance_id.name)}
                mk_log_line_dict = env.context.get('mk_log_line_dict', {'error': [], 'success': []})
                try:
                    mk_log_id = env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, operation_type='webhook')
                    self.process_webhook_response(env, webhook_type, response, mk_instance_id, mk_log_id)
                except Exception as e:
                    log_message = "Error while processing Shopify webhook {}, ERROR: {}.".format(webhook_type, e)
                    mk_log_line_dict['error'].append({'log_message': 'WEBHOOK PROCESS: {}'.format(log_message)})
                finally:
                    env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, operation_type='webhook', mk_log_line_dict=mk_log_line_dict)
                    if not mk_log_id.log_line_ids:
                        mk_log_id.unlink()
        except psycopg2.Error as e:
            _logger.error(_("SHOPIFY WEBHOOK RECEIVE: Error while Processing webhook request. ERROR: {}".format(e)))
        return {'status': 'Successfully processed.'}

    def shopify_process_fulfillment(self, existing_order_id, response, mk_log_id):
        fulfillment_status = response.get('fulfillment_status')
        update_order_dict = {'fulfillment_status': fulfillment_status}
        if existing_order_id.state in ["draft", "sent"]:
            existing_order_id.action_confirm()
        existing_order_id.with_context(operation_type='webhook', mk_log_id=mk_log_id).auto_validate_shopify_delivery_order(response.get('fulfillments'))
        if all(existing_order_id.order_line.mapped('move_ids').mapped('picking_id').mapped('updated_in_marketplace')):
            update_order_dict.update({'updated_in_marketplace': True})
        existing_order_id.write(update_order_dict)
        return existing_order_id

    def process_webhook_response(self, env, webhook_type, response, mk_instance_id, mk_log_id):
        mk_instance_id.connection_to_shopify()
        mk_log_line_dict = env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        if webhook_type in ['customers/create', 'customers/update']:
            env['res.partner'].with_context(mk_log_line_dict=mk_log_line_dict, mk_log_id=mk_log_id).create_update_shopify_customers(response, mk_instance_id)

        if webhook_type in ["products/create"]:
            mk_listing_obj = env['mk.listing']
            mk_listing_id = mk_listing_obj.with_context(mk_log_line_dict=mk_log_line_dict).create_update_shopify_product(response, mk_instance_id, update_product_price=True)
            if mk_listing_id:
                if mk_instance_id.is_sync_images:
                    mk_listing_obj.sync_product_image_from_shopify(mk_instance_id, mk_listing_id, response)

        if webhook_type in ["products/update"]:
            mk_listing_obj = env['mk.listing']
            listing_id = mk_listing_obj.search([('mk_id', '=', response.get('id')), ('mk_instance_id', '=', mk_instance_id.id)])
            if listing_id:
                mk_listing_id = mk_listing_obj.with_context(mk_log_line_dict=mk_log_line_dict).create_update_shopify_product(response, mk_instance_id, update_product_price=False)
                if mk_listing_id:
                    if mk_instance_id.is_sync_images:
                        mk_listing_obj.sync_product_image_from_shopify(mk_instance_id, mk_listing_id, response)

        if webhook_type == 'products/delete':
            mk_listing_obj = env['mk.listing']
            listing_id = mk_listing_obj.search([('mk_id', '=', response.get('id')), ('mk_instance_id', '=', mk_instance_id.id)])
            listing_name = listing_id.name
            listing_id and listing_id.unlink()
            log_message = "Successfully Deleted Listing. Listing Name: {}, Listing ID: {}".format(listing_name, response.get('id'))
            mk_log_line_dict['success'].append({'log_message': 'DELETE PRODUCT: {}'.format(log_message)})

        if webhook_type == "orders/updated":
            existing_order_id = env['sale.order'].search([('mk_id', '=', response.get('id')), ('mk_instance_id', '=', mk_instance_id.id)])
            if existing_order_id:
                env['sale.order'].with_context(operation_type='webhook', mk_log_id=mk_log_id).process_import_order_from_shopify_ts(response, mk_instance_id)
                fulfillment_status = response.get('fulfillment_status')
                if fulfillment_status in ['partial', 'fulfilled'] and existing_order_id:
                    try:
                        existing_order_id._process_shopify_draft_orders(response)  # process draft orders
                        self.shopify_process_fulfillment(existing_order_id, response, mk_log_id) # process fulfilled orders
                        existing_order_id.with_context(skip_check_transaction=True)._process_shopify_refund_in_odoo(response)  # create refund according to the Shopify.
                        shopify_tag_vals = existing_order_id.prepage_order_tag_vals(response.get('tags'))
                        if shopify_tag_vals and response.get('tags'):
                            existing_order_id.write(shopify_tag_vals)
                    except Exception as e:
                        log_traceback_for_exception()
                        mk_log_line_dict['error'].append({'log_message': 'ODOO UPDATE ORDER STATUS: Shopify order {}, ERROR: {}'.format(existing_order_id.name, e)})
                        env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict=mk_log_line_dict)

        if webhook_type == "orders/create":
            existing_order_id = env['sale.order'].search([('mk_id', '=', response.get('id')), ('mk_instance_id', '=', mk_instance_id.id)])
            if not existing_order_id:
                existing_order_id = env['sale.order'].with_context(operation_type='webhook', mk_log_id=mk_log_id).process_import_order_from_shopify_ts(response, mk_instance_id)
            fulfillment_status = response.get('fulfillment_status')
            if fulfillment_status in ['partial', 'fulfilled'] and existing_order_id:
                try:
                    self.shopify_process_fulfillment(existing_order_id, response, mk_log_id)
                except Exception as e:
                    log_traceback_for_exception()
                    mk_log_line_dict['error'].append({'log_message': 'ODOO UPDATE ORDER STATUS: Shopify order {}, ERROR: {}'.format(existing_order_id.name, e)})
                    env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict=mk_log_line_dict)
        return True
