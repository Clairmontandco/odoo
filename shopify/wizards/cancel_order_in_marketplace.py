from .. import shopify
from datetime import datetime
from odoo import models, api, fields, _
from odoo.tools import float_compare
from odoo.exceptions import UserError

CANCEL_REASON = [('customer', 'Customer changed/canceled order'),
                 ('inventory', 'Item Unavailable'),
                 ('fraud', 'Fraudulent order'),
                 ('declined', 'Payment declined'),
                 ('other', 'Other')]

DISCREPANCY_REASON = [('restock', 'Restocking Fee'),
                      ('damage', 'Damaged Goods'),
                      ('customer', 'Customer Satisfaction'),
                      ('other', 'Other')]

RESTOCK_TYPE = [('no_restock', 'No Restock'),
                ('cancel', 'Cancel'),
                ('return', 'Return')]


class MKCancelOrder(models.TransientModel):
    _inherit = "mk.cancel.order"

    @api.depends('shopify_refund_payment_lines.price_subtotal', 'shopify_refund_payment_lines.refund_price_unit', 'shopify_shipping_amount')
    def _amount_all(self):
        for record in self:
            shopify_amount_subtotal_to_refund, shopify_tax_amount, order_id = 0.0, 0.0, False
            for line in record.shopify_refund_payment_lines:
                order_id = line.order_line_id.order_id
                shopify_tax_amount += _get_amount_tax(line)
                shopify_amount_subtotal_to_refund += line.refund_price_unit * line.to_refund_qty
            if order_id and self.shopify_shipping_amount > 0.0:
                shipping_line = order_id.order_line.filtered(lambda x: x.is_delivery)
                shipping_taxes = shipping_line.tax_id.compute_all(shipping_line.price_unit, order_id.currency_id, 1, product=shipping_line.product_id,
                                                                  partner=order_id.partner_shipping_id)
                shipping_taxes_total = sum(t.get('amount', 0.0) for t in shipping_taxes.get('taxes', []))
                shopify_tax_amount += min(shipping_taxes_total,record.shopify_remaining_shipping_tax_amount)
            shopify_amount_subtotal = round(shopify_amount_subtotal_to_refund, 2)
            shopify_tax_amount = round(shopify_tax_amount, 2)
            shopify_manual_refund_amount = min(shopify_amount_subtotal + shopify_tax_amount + record.shopify_shipping_amount, record.shopify_amount_total)
            record.update({
                'shopify_tax_amount': shopify_tax_amount,
                'shopify_amount_subtotal': shopify_amount_subtotal,
                'shopify_manual_refund_amount': 0.0 if shopify_manual_refund_amount < 0 else shopify_manual_refund_amount
            })

    shopify_cancel_reason = fields.Selection(CANCEL_REASON, "Cancel Reason", default="customer")
    shopify_is_notify_customer = fields.Boolean("Notify Customer?", default=False, help="Whether to send an email to the customer notifying them of the cancellation.")
    shopify_refund_payment_lines = fields.One2many("shopify.refund.payment.line", "wizard_id", string="Shopify Refund payments")
    shopify_amount_total = fields.Monetary(string='Total Available to refund')
    shopify_amount_subtotal = fields.Monetary(string='Subtotal', store=True, readonly=True, compute='_amount_all')
    shopify_remaining_shipping_amount = fields.Monetary(string='Remaining shipping amount to Refund')
    shopify_remaining_shipping_tax_amount = fields.Monetary(string='Remaining shipping tax amount to Refund')
    shopify_shipping_amount = fields.Monetary(string='Shipping')
    shopify_tax_amount = fields.Monetary(string="Tax", store=True, compute='_amount_all')
    shopify_manual_refund_amount = fields.Monetary(string='Refund Amount')
    shopify_txn_id = fields.Char("Transaction ID")
    shopify_gateway = fields.Char("Transaction Gateway")
    shopify_gift_card_amount = fields.Monetary(string='Gift Card Amount')
    duties_warning = fields.Boolean("Duties Warning", default=False)
    shopify_restock_type = fields.Selection(RESTOCK_TYPE, "Restock Type", default="no_restock", help="How this refund line item affects inventory levels. \n "
                                                                                                     "Valid values : \n"
                                                                                                     "no_restock : Refunding these items won't affect inventory. The number of fulfillable units for this line item will remain unchanged. For example, a refund payment can be issued but no items will be returned or made available for sale again. \n"
                                                                                                     "cancel : The items have not yet been fulfilled. The canceled quantity will be added back to the available count. The number of fulfillable units for this line item will decrease. \n"
                                                                                                     "return : The items were already delivered, and will be returned to the merchant. The returned quantity will be added back to the available count. The number of fulfillable units for this line item will remain unchanged.")

    @api.onchange('shopify_manual_refund_amount')
    def onchange_shopify_manual_refund_amount(self):
        if self.shopify_manual_refund_amount > self.shopify_amount_total:
            self.shopify_manual_refund_amount = self.shopify_amount_total
        return {}

    @api.onchange('shopify_shipping_amount')
    def onchange_shopify_shipping_amount(self):
        if not self.shopify_remaining_shipping_amount and self.shopify_shipping_amount:
            self.shopify_shipping_amount = False
        if self.shopify_shipping_amount > self.shopify_remaining_shipping_amount:
            self.shopify_shipping_amount = self.shopify_remaining_shipping_amount
        return {}

    def fetch_shopify_transactions_details(self, order_id):
        shopify_transactions = shopify.Transaction().find(order_id=order_id.mk_id)
        gateway, parent_id, gift_card_amount = '', '', 0.0
        for transaction in shopify_transactions:
            transaction_dict = transaction.to_dict()
            transaction_type = transaction_dict.get('transaction', {}).get('kind') or transaction_dict.get('kind')
            transaction_status = transaction_dict.get('transaction', {}).get('status', '') or transaction_dict.get('status', '')
            if transaction_type == 'sale' and transaction_status == 'success':
                if transaction_dict.get('gateway', '') == 'gift_card':
                    gift_card_amount += (float(transaction_dict.get('amount', 0.0)) * -1)
                    continue
                parent_id = transaction_dict.get('transaction', {}).get('id') or transaction_dict.get('id')
                gateway = transaction_dict.get('transaction', {}).get('gateway') or transaction_dict.get('gateway')
        return parent_id, gateway, gift_card_amount

    def shopify_refund_wizard_default_get(self, order_id):
        shopify_refund_payment_line_ids = self.env['shopify.refund.payment.line']
        order_id.mk_instance_id.connection_to_shopify()
        try:
            refunds = shopify.Refund.find(order_id=order_id.mk_id)
        except Exception as e:
            raise UserError(e)
        transaction_status = ''
        refund_dict_qty_wise = {}
        total_amount_refunded = 0.0
        total_shipping_refunded = 0.0
        total_shipping_tax_refunded = 0.0
        for refund in refunds:
            refund_dict = refund.to_dict()
            for transaction in refund_dict.get('transactions'):
                if transaction.get('status') == 'failure':
                    transaction_status = 'failure'
            if transaction_status == 'failure':
                break
            for refund_line in refund.refund_line_items:
                if refund_dict_qty_wise.get(refund_line.line_item_id, False):
                    refund_dict_qty_wise[refund_line.line_item_id] += refund_line.quantity
                else:
                    refund_dict_qty_wise.update({refund_line.line_item_id: refund_line.quantity})
            for adjustment in refund.order_adjustments:
                if adjustment.kind == 'shipping_refund':
                    if order_id.mk_instance_id.use_marketplace_currency:
                        total_shipping_refunded += float(adjustment.amount_set.presentment_money.amount)
                        total_shipping_tax_refunded += float(adjustment.tax_amount_set.presentment_money.amount)
                    else:
                        total_shipping_refunded += float(adjustment.amount_set.shop_money.amount)
                        total_shipping_tax_refunded += float(adjustment.tax_amount_set.shop_money.amount)
            for transaction in refund.transactions:
                if transaction.kind == 'refund':
                    total_amount_refunded += float(transaction.amount)

        remaining_shipping_to_refund, remaining_shipping_tax_to_refund, duties_warning = 0.0, 0.0, False
        for line in order_id.order_line:
            if line.price_subtotal <= 0:
                continue
            if line.product_id == order_id.mk_instance_id.duties_product_id:
                duties_warning = True
                continue
            if line.is_delivery:
                shipping_taxes = line.tax_id.compute_all(line.price_unit, order_id.currency_id, 1, product=line.product_id, partner=order_id.partner_shipping_id)
                shipping_taxes_total = sum(t.get('amount', 0.0) for t in shipping_taxes.get('taxes', []))
                remaining_shipping_tax_to_refund = shipping_taxes_total + total_shipping_tax_refunded
                if any(line.tax_id.mapped('price_include')):
                    remaining_shipping_to_refund = line.price_unit + total_shipping_refunded + line.related_disc_sale_line_id.price_unit + total_shipping_tax_refunded
                else:
                    remaining_shipping_to_refund = line.price_subtotal + total_shipping_refunded + line.related_disc_sale_line_id.price_subtotal
                continue
            if refund_dict_qty_wise.get(int(line.mk_id), False):
                available_qty = line.product_uom_qty - refund_dict_qty_wise.get(int(line.mk_id))
            else:
                available_qty = line.product_uom_qty
            if not available_qty:
                continue

            if any(line.tax_id.mapped('price_include')):
                price_unit = line.price_reduce_taxexcl - abs(line.related_disc_sale_line_id.price_reduce_taxexcl)
            else:
                price_unit = (line.price_subtotal / line.product_uom_qty) - abs((line.related_disc_sale_line_id.price_subtotal / line.product_uom_qty))
            shopify_refund_payment_line_ids |= self.env['shopify.refund.payment.line'].create({
                'product_id': line.product_id.id,
                'available_qty': available_qty,
                'to_refund_qty': available_qty,
                'price_unit': price_unit,
                'refund_price_unit': price_unit,
                'order_line_id': line.id,
            })

        parent_id, gateway, gift_card_amount = self.fetch_shopify_transactions_details(order_id)
        create_refund_option_visible = True if order_id.invoice_ids.filtered(lambda x: x.move_type == 'out_invoice' and x.payment_state in ['paid', 'in_payment']) else False
        return {'shopify_refund_payment_lines': [(6, 0, shopify_refund_payment_line_ids.ids)],
                'shopify_remaining_shipping_amount': remaining_shipping_to_refund,
                'shopify_remaining_shipping_tax_amount': remaining_shipping_tax_to_refund,
                'shopify_shipping_amount': remaining_shipping_to_refund,
                'shopify_amount_total': order_id.amount_total - total_amount_refunded + gift_card_amount,
                'shopify_txn_id': parent_id,
                'shopify_gateway': gateway,
                'duties_warning': duties_warning,
                'shopify_gift_card_amount': gift_card_amount,
                'currency_id': order_id.currency_id.id,
                'create_refund_option_visible': create_refund_option_visible}

    def do_cancel_in_shopify(self, order):
        mk_instance_id = order.mk_instance_id
        try:
            mk_instance_id.connection_to_shopify()
            order_id = shopify.Order.find(order.mk_id)
        except Exception as e:
            raise UserError(e)
        order_id.reason = self.shopify_cancel_reason
        order_id.email = self.shopify_is_notify_customer
        order_id.cancel()
        order.write({'canceled_in_marketplace': True})
        self._cr.commit()
        return True

    def do_refund_in_shopify(self):
        active_id = self._context.get('active_id')
        order_id = self.env['sale.order'].browse(active_id)
        if self.env.context.get('force_refund'):
            order_id.shopify_force_refund = True
            return True
        if not order_id:
            raise UserError(_("Can't find order to cancel. Please go back to order list, open order and try again!"))
        # if self.shopify_refund_payment_lines and float_compare((self.shopify_amount_subtotal + self.shopify_shipping_amount + self.shopify_tax_amount) - abs(self.shopify_gift_card_amount),
        #                                                        self.shopify_manual_refund_amount, 2) != 0:
        #     raise UserError(_("Subtotal + Shipping + Tax isn't matching with the Refund Amount. Please adjust refund unit price!"))
        mk_log_id = self.env['mk.log'].create_update_log(mk_instance_id=order_id.mk_instance_id, operation_type='export')
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        refund_item_list, restock_type = [], self.shopify_restock_type
        order_id.mk_instance_id.connection_to_shopify()
        for line in self.shopify_refund_payment_lines.filtered(lambda x: x.to_refund_qty):
            refund_item_dict = {'line_item_id': line.order_line_id.mk_id,
                                'quantity': int(line.to_refund_qty),
                                'restock_type': restock_type}
            if restock_type in ['cancel', 'return']:
                shopify_location_id = line.order_line_id.shopify_location_id
                if not shopify_location_id:
                    shopify_location_id = self.env['shopify.location.ts'].search([('is_default_location', '=', True), ('mk_instance_id', '=', order_id.mk_instance_id.id)])
                    if not shopify_location_id:
                        mk_log_line_dict['error'].append(
                            {'log_message': 'Default Shopify Location not found in Odoo while trying to Refund in Shopify. Order: {}'.format(order_id.name)})
                refund_item_dict.update({'location_id': shopify_location_id.shopify_location_id})
            refund_item_list.append(refund_item_dict)
        if not refund_item_list and not self.shopify_amount_total and not self.shopify_manual_refund_amount:
            return False
        shopify_transactions = shopify.Transaction().find(order_id=order_id.mk_id)
        for transaction in shopify_transactions:
            transaction_dict = transaction.to_dict()
            transaction_type = transaction_dict.get('transaction', {}).get('kind') or transaction_dict.get('kind')
            transaction_status = transaction_dict.get('transaction', {}).get('status', '') or transaction_dict.get('status', '')
            if transaction_type == 'sale' and transaction_status == 'success':
                break
        vals = {'notify': self.shopify_is_notify_customer,
                'note': self.refund_description or '',
                'order_id': order_id.mk_id,
                'refund_line_items': refund_item_list,
                'currency': order_id.currency_id.name,
                'transactions': [
                    {
                        'parent_id': int(self.shopify_txn_id),
                        'amount': self.shopify_manual_refund_amount,
                        'kind': 'refund',
                        'gateway': self.shopify_gateway,
                    }]}
        if self.shopify_shipping_amount:
            vals.update({'shipping': {'amount': self.shopify_shipping_amount}})
        try:
            response = shopify.Refund().create(vals)
        except Exception as e:
            raise UserError("Something went wrong while creating a refund in Shopify for order {} : {}".format(order_id.name, e))

        if response.errors and response.errors.errors:
            errors = response.errors.errors
            raise UserError("{}".format(errors))

        shopify_order = shopify.Order.find(order_id.mk_id)
        order_id.write({'shopify_financial_status': shopify_order.financial_status})
        body = _('This order is refunded in Shopify with amount <b>{}</b>'.format(self.shopify_manual_refund_amount))
        order_id.message_post(body=body)
        self.env['mk.log'].create_update_log(mk_instance_id=order_id.mk_instance_id, mk_log_id=mk_log_id, mk_log_line_dict=mk_log_line_dict)
        if not mk_log_id.log_line_ids and not self.env.context.get('log_id', False):
            mk_log_id.unlink()
        if self.is_create_refund:
            # self.create_shopify_refund_in_odoo(order_id)
            invoice_id = order_id.invoice_ids.filtered(lambda x: x.move_type == 'out_invoice')
            order_id.with_context(refund_journal_id=self.payment_journal_id.id, date=self.date_invoice)._create_shopify_credit_note_and_adjust_amount(shopify_order.to_dict(), response.to_dict(), invoice_id)
        return True

    def cancel_and_refund_in_shopify(self):
        active_id = self._context.get('active_id')
        order_id = self.env['sale.order'].browse(active_id)
        if not order_id:
            raise UserError("Can't find order to cancel. Please go back to order list, open order and try again!")
        if order_id.shopify_financial_status == 'paid' and order_id.fulfillment_status == 'fulfilled':
            raise UserError("Orders that are paid and have fulfillments can't be canceled in Shopify.")
        self.do_cancel_in_shopify(order_id)
        self.do_refund_in_shopify()
        return True

    # def create_shopify_refund_in_odoo(self, order_id):
    #     invoice_id = order_id.invoice_ids.filtered(lambda x: x.move_type == 'out_invoice' and x.payment_state in ['paid', 'in_payment'])
    #     if invoice_id:
    #         move_reversal = self.env['account.move.reversal'].with_context(active_model="account.move", active_ids=invoice_id.ids).create({
    #             'reason': self.refund_description or "Shopify Refund",
    #             'refund_method': 'refund',
    #             'date': self.date_invoice or datetime.now(),
    #             'journal_id': invoice_id.journal_id.id
    #         })
    #         reversal = move_reversal.reverse_moves()
    #         refund_invoice = self.env['account.move'].browse(reversal['res_id'])
    #         to_remove_lines = refund_invoice.invoice_line_ids
    #         for line in self.shopify_refund_payment_lines.filtered(lambda x: x.to_refund_qty):
    #             for inv_line in refund_invoice.invoice_line_ids.filtered(lambda x: x.product_id == line.order_line_id.product_id):
    #                 if line.refund_price_unit < line.order_line_id.price_subtotal:
    #                     price_unit = line.refund_price_unit
    #                 else:
    #                     price_unit = line.refund_price_unit
    #                 if any(line.order_line_id.tax_id.mapped('price_include')):
    #                     price_unit += (line.amount_tax / line.order_line_id.product_uom_qty)
    #                 inv_line.with_context(check_move_validity=False).write({'quantity': line.to_refund_qty, 'price_unit': price_unit})
    #                 to_remove_lines -= inv_line
    #         if self.shopify_shipping_amount:
    #             shipping_line = order_id.order_line.filtered(lambda x: x.is_delivery)
    #             shipping_product_id = shipping_line.mapped('product_id')
    #             for inv_line in refund_invoice.invoice_line_ids.filtered(lambda x: x.product_id == shipping_product_id):
    #                 shopify_shipping_amount = self.shopify_shipping_amount
    #                 if any(shipping_line.tax_id.mapped('price_include')):
    #                     shopify_shipping_amount += shipping_line.price_tax
    #                 inv_line.with_context(check_move_validity=False).write({'quantity': 1, 'price_unit': shopify_shipping_amount})
    #                 to_remove_lines -= inv_line
    #         if to_remove_lines:
    #             to_remove_lines.with_context(check_move_validity=False).unlink()
    #         refund_invoice.with_context(check_move_validity=False)._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
    #         refund_invoice._check_balanced()
    #         refund_invoice.action_post()
    #         register_payments = self.env['account.payment.register'].with_context(active_model='account.move', active_ids=refund_invoice.ids).create(
    #             {'journal_id': self.payment_journal_id.id})._create_payments()
    #         return reversal
    #     return True


def _get_amount_tax(line):
    taxes = line.order_line_id.tax_id.compute_all(line.order_line_id.price_unit, line.order_line_id.order_id.currency_id, line.to_refund_qty, product=line.product_id,
                                                  partner=line.order_line_id.order_id.partner_shipping_id)
    amount_tax = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
    related_disc_sale_line_id = line.order_line_id.related_disc_sale_line_id
    if related_disc_sale_line_id:
        taxes = related_disc_sale_line_id.tax_id.compute_all(related_disc_sale_line_id.price_unit, related_disc_sale_line_id.order_id.currency_id, line.to_refund_qty,
                                                             product=related_disc_sale_line_id.product_id, partner=related_disc_sale_line_id.order_id.partner_shipping_id)
        amount_tax += sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
    return amount_tax


class ShopifyRefundPaymentLines(models.TransientModel):
    _name = "shopify.refund.payment.line"
    _description = "Shopify Refund Line"

    @api.depends('to_refund_qty', 'refund_price_unit')
    def _compute_amount(self):
        for line in self:
            price_subtotal = line.refund_price_unit * line.to_refund_qty
            amount_tax = _get_amount_tax(line)
            line.update({'price_subtotal': price_subtotal,
                         'amount_tax': amount_tax})

    product_id = fields.Many2one('product.product', string='Product', ondelete='cascade', required=True)
    order_line_id = fields.Many2one('sale.order.line', string="Order Line", ondelete='cascade')
    available_qty = fields.Float(string='Available Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    to_refund_qty = fields.Float(string='To Refund Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    price_unit = fields.Float('Original Unit Price', required=True, digits='Product Price', default=0.0)
    refund_price_unit = fields.Float('Refund Unit Price', required=True, digits='Product Price', default=0.0)
    price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', store=True, compute_sudo=True)
    amount_tax = fields.Monetary(compute='_compute_amount', string='Total Tax', compute_sudo=True)
    wizard_id = fields.Many2one('mk.cancel.order', 'Wizard')
    currency_id = fields.Many2one('res.currency', 'Currency', readonly=True, related='wizard_id.currency_id', store=True)

    @api.onchange('to_refund_qty')
    def onchange_refund_qty(self):
        res = {}
        if not self.available_qty and self.to_refund_qty:
            self.to_refund_qty = False
        if self.to_refund_qty > self.available_qty:
            self.to_refund_qty = self.available_qty
        return res

    @api.onchange('refund_price_unit')
    def onchange_refund_price_unit(self):
        res = {}
        if self.refund_price_unit > self.price_unit:
            self.refund_price_unit = self.price_unit
        return res
