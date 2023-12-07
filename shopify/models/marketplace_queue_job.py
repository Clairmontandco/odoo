import pprint
from .. import shopify
from odoo import models, fields
from psycopg2 import OperationalError
from odoo.tools.safe_eval import safe_eval
from .misc import log_traceback_for_exception


class MkQueueJob(models.Model):
    _inherit = "mk.queue.job"

    def shopify_customer_queue_process(self, draft_queue_line_id=None):
        res_partner_obj = self.env['res.partner']
        draft_queue_line_ids = draft_queue_line_id if draft_queue_line_id else self.mk_queue_line_ids.filtered(lambda x: x.state == 'draft')
        for line in draft_queue_line_ids:
            customer_dict = safe_eval(line.data_to_process)
            res_partner_obj.with_context(queue_line_id=line, mk_log_id=line.queue_id.mk_log_id).create_update_shopify_customers(customer_dict, self.mk_instance_id)
            line.write({'processed_date': fields.Datetime.now()})
        return True

    def shopify_order_queue_process(self, skip_api_call=None, draft_queue_line_id=None):
        sale_order_obj, mk_instance_id, shopify_location_obj = self.env['sale.order'], self.mk_instance_id, self.env['shopify.location.ts']
        draft_queue_line_ids = draft_queue_line_id if draft_queue_line_id else self.mk_queue_line_ids.filtered(lambda x: x.state in ['draft', 'failed'])
        if not skip_api_call:
            shopify_location_obj.import_location_from_shopify(mk_instance_id)
        for line in draft_queue_line_ids:
            order_name = ''
            try:
                shopify_order_dict = safe_eval(line.data_to_process)
                order_name = shopify_order_dict.get('name')
                with self.env.cr.savepoint():
                    order_id = sale_order_obj.with_context(queue_line_id=line, skip_queue_change_state=True, mk_log_id=line.queue_id.mk_log_id).process_import_order_from_shopify_ts(shopify_order_dict, mk_instance_id)
                if order_id:
                    line.write({'state': 'processed', 'processed_date': fields.Datetime.now(), 'order_id': order_id and order_id.id or False})
                else:
                    line.write({'state': 'failed', 'processed_date': fields.Datetime.now()})
            except OperationalError:
                self._cr.rollback()
            except Exception as e:
                log_traceback_for_exception()
                self._cr.rollback()
                log_message = "PROCESS ORDER: Error while processing Marketplace Order {}, ERROR: {}".format(order_name, e)
                self.env['mk.log'].create_update_log(mk_log_id=line.queue_id.mk_log_id, mk_instance_id=mk_instance_id,
                                                     mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': line and line.id or False}]})
                line.write({'state': 'failed', 'processed_date': fields.Datetime.now()})
            self._cr.commit()
        if not self.env.context.get('hide_notification', False):
            error_count = self.env['mk.queue.job.line'].search_count([('state', '=', 'failed'), ('id', 'in', draft_queue_line_ids.ids)])
            success_count = self.env['mk.queue.job.line'].search_count([('state', '=', 'processed'), ('id', 'in', draft_queue_line_ids.ids)])
            mk_instance_id.send_smart_notification('is_order_create', 'error', error_count)
            mk_instance_id.send_smart_notification('is_order_create', 'success', success_count)
            if error_count:
                self.create_activity_action("Please check queue job for its fail reason.")

    def shopify_product_queue_process(self, draft_queue_line_id=None):
        mk_instance_id, listing_obj = self.mk_instance_id, self.env['mk.listing']
        draft_queue_line_ids = draft_queue_line_id if draft_queue_line_id else self.mk_queue_line_ids.filtered(lambda x: x.state == 'draft')
        for line in draft_queue_line_ids:
            shopify_product_dict = safe_eval(line.data_to_process)
            mk_listing_id = self.env['mk.listing'].search([('mk_instance_id', '=', mk_instance_id.id), ('mk_id', '=', line.mk_id)])
            is_update_existing_products = True if not mk_listing_id else line.queue_id.update_existing_product
            update_product_price = True if not mk_listing_id else line.queue_id.update_product_price
            mk_listing_id = listing_obj.with_context(queue_line_id=line, mk_log_id=line.queue_id.mk_log_id).create_update_shopify_product(shopify_product_dict, mk_instance_id, update_product_price=update_product_price, is_update_existing_products=is_update_existing_products)
            line.write({'processed_date': fields.Datetime.now(), 'state': 'processed' if mk_listing_id else 'failed', 'mk_listing_id': mk_listing_id and mk_listing_id.id or False})
            self._cr.commit()
        if not self.env.context.get('hide_notification', False):
            success_count = self.env['mk.queue.job.line'].search_count([('state', '=', 'processed'), ('id', 'in', draft_queue_line_ids.ids)])
            error_count = self.env['mk.queue.job.line'].search_count([('state', '=', 'failed'), ('id', 'in', draft_queue_line_ids.ids)])
            mk_instance_id.send_smart_notification('is_product_import', 'error', error_count)
            mk_instance_id.send_smart_notification('is_product_import', 'success', success_count)

    def shopify_product_retry_failed_queue(self):
        failed_queue_line_ids = self.mk_queue_line_ids.filtered(lambda ql: ql.state == 'failed')
        failed_queue_line_ids and failed_queue_line_ids.shopify_product_retry_failed_queue()
        return True

    def shopify_order_retry_failed_queue(self):
        failed_queue_line_ids = self.mk_queue_line_ids.filtered(lambda ql: ql.state == 'failed')
        failed_queue_line_ids and failed_queue_line_ids.shopify_order_retry_failed_queue()
        return True

    def shopify_customer_retry_failed_queue(self):
        failed_queue_line_ids = self.mk_queue_line_ids.filtered(lambda ql: ql.state == 'failed')
        failed_queue_line_ids and failed_queue_line_ids.shopify_customer_retry_failed_queue()
        return True


class MkQueueJobLine(models.Model):
    _inherit = "mk.queue.job.line"

    def shopify_product_retry_failed_queue(self):
        queue_id = self.mapped('queue_id')
        queue_id.mk_instance_id.connection_to_shopify()
        for line in self.filtered(lambda x: x.mk_id):
            shopify_product = shopify.Product.find(line.mk_id)
            shopify_product_dict = shopify_product.to_dict()
            line.write({'state': 'draft', 'data_to_process': pprint.pformat(shopify_product_dict)})
            line.queue_id.with_context(hide_notification=True).shopify_product_queue_process(draft_queue_line_id=line)
        return True

    def shopify_order_retry_failed_queue(self):
        queue_id = self.mapped('queue_id')
        queue_id.mk_instance_id.connection_to_shopify()
        for line in self.filtered(lambda x: x.mk_id):
            shopify_order = shopify.Order.find(line.mk_id)
            shopify_order_dict = shopify_order.to_dict()
            line.write({'state': 'draft', 'data_to_process': pprint.pformat(shopify_order_dict)})
            line.queue_id.with_context(hide_notification=True).shopify_order_queue_process(skip_api_call=True, draft_queue_line_id=line)
        return True

    def shopify_customer_retry_failed_queue(self):
        queue_id = self.mapped('queue_id')
        queue_id.mk_instance_id.connection_to_shopify()
        for line in self.filtered(lambda x: x.mk_id):
            shopify_customer = shopify.Customer.find(line.mk_id)
            shopify_customer_dict = shopify_customer.to_dict()
            line.write({'state': 'draft', 'data_to_process': pprint.pformat(shopify_customer_dict)})
            line.queue_id.with_context(hide_notification=True).shopify_customer_queue_process(draft_queue_line_id=line)
        return True
