from odoo import models, fields, _
from odoo.exceptions import UserError
from odoo.addons.shopify import shopify


class StockMove(models.Model):
    _inherit = "stock.move"

    def _assign_picking_post_process(self, new=False):
        res = super(StockMove, self)._assign_picking_post_process(new=new)
        order_id = self.sale_line_id.order_id
        if new and order_id.marketplace == 'shopify' and order_id.fulfillment_status == 'fulfilled':
            picking_id = self.mapped('picking_id')
            picking_id and picking_id.write({'updated_in_marketplace': True, 'is_marketplace_exception': False, 'exception_message': False})
        return res


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    shopify_fulfillment_id = fields.Char(string='Fulfillment ID', copy=False)

    def shopify_update_order_status_to_marketplace(self):
        self.mk_instance_id.connection_to_shopify()
        self.process_update_order_status_shopify(manual_process=True)
        return True

    def process_update_order_status_shopify(self, manual_process=False):
        self.ensure_one()
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        order_id = self.sale_id
        if not order_id:
            log_message = 'UPDATE ORDER STATUS: There is no Sale Order not linked with this Delivery.'
            not manual_process and mk_log_line_dict['error'].append({'log_message': log_message})
            self.write({'is_marketplace_exception': True, 'exception_message': log_message})
            return False
        if not order_id.mk_id:
            log_message = 'UPDATE ORDER STATUS: Cannot find Marketplace Identification in Sale order {}.'.format(order_id.name)
            not manual_process and mk_log_line_dict['error'].append({'log_message': log_message})
            self.write({'is_marketplace_exception': True, 'exception_message': log_message})
            return False
        try:
            shopify_order = shopify.Order.find(order_id.mk_id)
            shopify_order_dict = shopify_order.to_dict()
            if shopify_order_dict.get('cancelled_at') and shopify_order_dict.get('cancel_reason'):
                log_message = 'UPDATE ORDER STATUS: Shopify order {} is already cancelled in Shopify.'.format(order_id.name)
                self.write({'is_marketplace_exception': True, 'exception_message': log_message})
                not manual_process and mk_log_line_dict['success'].append({'log_message': log_message})
                self._cr.commit()
                return False
            if shopify_order_dict.get('fulfillment_status') == 'fulfilled':
                self.write({'updated_in_marketplace': True, 'is_marketplace_exception': False, 'exception_message': False})
                order_id.write({'updated_in_marketplace': True})
                not manual_process and mk_log_line_dict['success'].append({'log_message': 'UPDATE ORDER STATUS: Shopify order {} is already updated in Shopify.'.format(order_id.name)})
                self._cr.commit()
                return True
            if shopify_order_dict.get('financial_status') == 'refunded':
                log_message = 'UPDATE ORDER STATUS: You cannot fulfill Shopify order {} because it is refunded in Shopify.'.format(order_id.name)
                self.write({'is_marketplace_exception': True, 'exception_message': log_message})
                not manual_process and mk_log_line_dict['success'].append({'log_message': log_message})
                self._cr.commit()
                return False
            order_id.fetch_order_fulfillment_location_from_shopify(shopify_order_dict)
            order_id.update_shopify_order_line_location(shopify_order_dict)
        except Exception as e:
            not manual_process and mk_log_line_dict['error'].append({'log_message': 'UPDATE ORDER STATUS: Shopify order {}, ERROR: {}.'.format(order_id.name, e)})
            return False
        self.process_picking_for_update_order_status_in_shopify(order_id, shopify_order_dict, manual_process)
        if all(order_id.order_line.mapped('move_ids').mapped('picking_id').mapped('updated_in_marketplace')):
            order_id.write({'fulfillment_status': 'fulfilled', 'updated_in_marketplace': True})
        self._cr.commit()
        return True

    def process_picking_for_update_order_status_in_shopify(self, shopify_order_id, shopify_order_dict, manual_process=False):
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        if not shopify_order_id.order_line.mapped('mk_id'):
            log_message = 'Cannot update order status because Shopify Order Line ID not found in Order {}'.format(shopify_order_id.name)
            mk_log_line_dict['error'].append({'log_message': 'UPDATE ORDER STATUS: {}'.format(log_message)})
            self.write({'is_marketplace_exception': True, 'exception_message': log_message})
            return False

        line_item_list = self.update_fulfillment_value_to_shopify(shopify_order_id, shopify_order_dict)

        if line_item_list:
            self.write({'updated_in_marketplace': True, 'is_marketplace_exception': False, 'exception_message': False})
            if not manual_process:
                mk_log_line_dict['success'].append({'log_message': 'UPDATE ORDER STATUS: Successfully updated Shopify order {}'.format(shopify_order_id.name)})
        return True

    def update_fulfillment_value_to_shopify(self, shopify_order_id, shopify_order_dict):
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        line_item_dict = self.shopify_prepare_fulfillment_line_vals(shopify_order_dict)
        if not line_item_dict:
            log_message = 'Order lines not found for Shopify Order {} while trying to update Order status'.format(shopify_order_id.name)
            mk_log_line_dict['error'].append({'log_message': 'UPDATE ORDER STATUS: {}'.format(log_message)})
            self.write({'is_marketplace_exception': True, 'exception_message': log_message})
            return False

        tracking_info = {"number": self.carrier_tracking_ref or '',
                         "url": self.carrier_tracking_url or '',
                         "company": self.carrier_id and self.carrier_id.shopify_code or self.carrier_id.name or ''}
        for fulfillment_order_id in line_item_dict:
            line_item_list = line_item_dict.get(fulfillment_order_id)
            # location_name_list.append(location_id)
            # thanks to https://stackoverflow.com/a/9427216
            # below line is used to remove duplicate dict because in Kit type product it may be possible that duplicate line dict will be created.
            line_item_list = [dict(t) for t in {tuple(d.items()) for d in line_item_list}]
            try:
                fulfillment_result = shopify.Fulfillment.create({'tracking_info': tracking_info,
                                                                 'line_items_by_fulfillment_order': [{"fulfillment_order_id": fulfillment_order_id,
                                                                                                      "fulfillment_order_line_items": line_item_list}],
                                                                 'notify_customer': shopify_order_id.mk_instance_id.is_notify_customer})
            except Exception as e:
                log_message = 'Error while trying to update Order status of Shopify Order {}.ERROR: {}'.format(shopify_order_id.name, e)
                mk_log_line_dict['error'].append({'log_message': 'UPDATE ORDER STATUS: {}'.format(log_message)})
                self.write({'is_marketplace_exception': True, 'exception_message': log_message})
                return False
            if fulfillment_result and fulfillment_result.errors and fulfillment_result.errors.errors:
                errors = ",".join(error for error in fulfillment_result.errors.errors.get('base'))
                log_message = 'Shopify Order {} is not updated due to some issue. REASON: {}'.format(shopify_order_id.name, errors)
                mk_log_line_dict['error'].append({'log_message': 'UPDATE ORDER STATUS: {}'.format(log_message)})
                self.write({'is_marketplace_exception': True, 'exception_message': log_message})
                return False
        return True

    def shopify_prepare_fulfillment_line_vals(self, shopify_order_dict):
        self.ensure_one()
        line_item_dict = {}
        mrp = self.env['ir.module.module'].search([('name', '=', 'mrp'), ('state', '=', 'installed')])
        for move in self.move_lines:
            if int(move.quantity_done) > 0 and move.sale_line_id.mk_id:
                if mrp and self.env['mrp.bom']._bom_find(move.sale_line_id.product_id, bom_type='phantom'):
                    quantity = move.sale_line_id.product_uom_qty
                else:
                    quantity = move.quantity_done

                fulfilment_line = [line_item for line_item in shopify_order_dict.get('line_items') if line_item.get('id') == int(move.sale_line_id.mk_id)]
                if fulfilment_line:
                    fulfillment_order_id = fulfilment_line[0].get('fulfillment_order_id')
                    fulfillment_order_line_item_id = fulfilment_line[0].get('fulfillment_order_line_item_id')
                    if fulfillment_order_id:
                        existing_line_item = line_item_dict.get(fulfillment_order_id)
                        if existing_line_item:
                            existing_line_item.append({'id': fulfillment_order_line_item_id, 'quantity': int(quantity)})
                        else:
                            line_item_dict.update({fulfillment_order_id: [{'id': fulfillment_order_line_item_id, 'quantity': int(quantity)}]})
                    else:
                        line_item_dict.update({fulfillment_order_id: [{'id': fulfillment_order_line_item_id, 'quantity': int(quantity)}]})
        return line_item_dict

    def _send_confirmation_email(self):
        newself = self
        for stock_pick in self.filtered(lambda p: p.company_id.stock_move_email_validation and p.picking_type_id.code == 'outgoing'):
            if stock_pick.sale_id.marketplace == 'shopify' and stock_pick.sale_id.mk_instance_id.is_notify_customer:
                newself -= stock_pick
        return super(StockPicking, newself)._send_confirmation_email()
