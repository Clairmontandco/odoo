import logging
from odoo import models, fields, _
from odoo.tools.misc import format_date

_logger = logging.getLogger("Teqstars: Marketplace Automation")


class SaleOrder(models.Model):
    _inherit = "sale.order"

    order_workflow_id = fields.Many2one("order.workflow.config.ts", "Marketplace Workflow")
    stock_moves_count = fields.Integer(compute="_compute_stock_move_count", string="Stock Moves", store=False, help="Stock Move Count for Sale Order without Stock Picking.")

    def _compute_stock_move_count(self):
        # The work of this method is get the number of stock moves link with the order and count it.
        self.stock_moves_count = self.env["stock.move"].search_count([("sale_line_id", "in", self.order_line.ids), ("picking_id", "=", False)])

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.order_workflow_id:
            if self.order_workflow_id.sale_journal_id:
                invoice_vals.update({'journal_id': self.order_workflow_id.sale_journal_id.id})
            if self.order_workflow_id.force_invoice_date:
                invoice_vals.update({'invoice_date': self.date_order})
        return invoice_vals

    def _get_order_fulfillment_status(self):
        # Hook type method that will get fulfillment status according to marketplace type.
        fulfillment_status = self.env.context.get('is_fulfilled_order', False)
        if hasattr(self, '%s_get_order_fulfillment_status' % self.marketplace):
            fulfillment_status = getattr(self, '%s_get_order_fulfillment_status' % self.marketplace)()
        return fulfillment_status

    def process_order(self, order_workflow_id):
        try:
            if self.state not in ['sale', 'done']:
                fulfillment_status = self._get_order_fulfillment_status()
                if fulfillment_status:
                    self.process_fulfilled_order(fulfillment_status)
                    if fulfillment_status == 'partial':
                        self.action_confirm()
                else:
                    self.action_confirm()
            if self.env.context.get('create_date', False):
                self.write({'date_order': self.env.context.get('create_date')})
            if order_workflow_id.is_lock_order and self.state != 'done':
                self.action_done()
        except Exception as e:
            raise
        return True

    def _prepare_payment_vals(self, order_workflow_id, invoice_id, amount=0.0):
        payment_vals = {
            # 'move_id': invoice_id.id,
            'amount': amount or invoice_id.amount_residual,
            'date': invoice_id.date,
            'ref': invoice_id.payment_reference or invoice_id.ref or invoice_id.name,
            'partner_id': invoice_id.commercial_partner_id.id,
            'partner_type': 'customer',
            'currency_id': invoice_id.currency_id.id,
            'journal_id': order_workflow_id.journal_id.id,
            'payment_type': 'inbound',
        }
        order_workflow_id.payment_method_line_id and payment_vals.update({'payment_method_line_id': order_workflow_id.payment_method_line_id.id})
        return payment_vals

    def pay_and_reconcile(self, order_workflow_id, invoice_id):
        if not self.env.context.get('manual_validate', False) and hasattr(self, '%s_pay_and_reconcile' % self.mk_instance_id.marketplace):
            return getattr(self, '%s_pay_and_reconcile' % self.mk_instance_id.marketplace)(order_workflow_id, invoice_id)
        payment_vals = self._prepare_payment_vals(order_workflow_id, invoice_id)
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
        return True

    def process_invoice(self, order_workflow_id):
        try:
            if order_workflow_id.is_create_invoice:
                self._create_invoices()
            if order_workflow_id.is_validate_invoice:
                for invoice_id in self.invoice_ids.filtered(lambda i: i.payment_state == 'not_paid' and i.state in ['draft', 'posted']):
                    if invoice_id.state == 'draft':
                        invoice_id.action_post()
                    if order_workflow_id.is_register_payment:
                        self.pay_and_reconcile(order_workflow_id, invoice_id)
        except Exception as e:
            raise
        return True

    def _check_fiscalyear_lock_date(self):
        lock_date = self.company_id._get_user_fiscal_lock_date()
        if self.date_order.date() <= lock_date:
            mk_log_id = self.env.context.get('mk_log_id', False)
            log_message = "PROCESS ORDER: You cannot create invoice prior to and inclusive of the lock date {} for Marketplace Order {}.".format(format_date(self.env, lock_date), self.name)
            if mk_log_id:
                mk_log_id = self.env.context.get('mk_log_id', False)
                queue_line_id = self.env.context.get('queue_line_id', False)
                self.env['mk.log'].create_update_log(mk_log_id=mk_log_id,
                                                     mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
            _logger.error(_(log_message))
            return False
        return True

    def do_marketplace_workflow_process(self, marketplace_workflow_id=False, order_list=None):
        if order_list is None or not order_list:
            order_list = [self]
        if not order_list:
            return False
        for order_id in order_list:
            order_workflow_id = order_id.order_workflow_id
            if not order_workflow_id:
                order_workflow_id = marketplace_workflow_id
            if order_id.invoice_status and order_id.invoice_status == 'invoiced':
                continue

            # Process Sale Order
            if order_workflow_id.is_confirm_order:
                if not order_id.process_order(order_workflow_id):
                    continue

                order_line_ids = order_id.mapped('order_line').filtered(lambda x: x.product_id.invoice_policy == 'order')
                if not order_line_ids.filtered(lambda x: x.product_id.type == 'product') and len(order_id.order_line) != len(
                        order_line_ids.filtered(lambda y: y.product_id.type in ['service', 'consu'])):
                    continue

                if not order_id._check_fiscalyear_lock_date():
                    continue

                # Process Invoice
                if not order_id.invoice_ids:
                    if not order_id.process_invoice(order_workflow_id):
                        continue
        return True

    def process_fulfilled_order(self, fulfillment_status=True):
        # The work of this method is process the fulfilled or partial shipped orders.
        location_obj = self.env['stock.location']
        mrp = self.env['ir.module.module'].sudo().search([('name', '=', 'mrp'), ('state', '=', 'installed')])
        location_dest_id = location_obj.search(['|', ('company_id', '=', self.company_id.id), ('company_id', '=', False), ('usage', '=', 'customer')], limit=1)
        location_id = location_obj.search(['|', ('company_id', '=', self.company_id.id), ('company_id', '=', False), ('usage', '=', 'supplier')], limit=1)
        sale_lines = self.order_line.filtered(lambda l: l.product_id.type != 'service')
        fulfillment_dict = {line: line.product_uom_qty for line in sale_lines}

        # TODO: by passing fulfillment_status to `fulfilled` or `partial` we can partially fulfill the order using below hook type method.
        if fulfillment_status == 'partial':
            # Hook type method that will get product and its qty according fulfillment status.
            # fulfillment_dict: {object of sale.order.line: Quantity you want to done}
            if hasattr(self, '%s_prepare_partial_fulfillment_value' % self.marketplace):
                fulfillment_dict = getattr(self, '%s_prepare_partial_fulfillment_value' % self.marketplace)(sale_lines)

        for sale_line, quantity in fulfillment_dict.items():
            bom_lines = []
            if mrp:
                bom_lines = self.check_bom_product_ts(sale_line.product_id)
            for bom_line in bom_lines:
                self.create_stock_move_and_done_ts(sale_line, quantity, location_dest_id, bom_line=bom_line)
            if not bom_lines and self.check_product_dropship(sale_line.product_id):
                self.create_stock_move_and_done_ts(sale_line, quantity, location_dest_id, location_id=location_id)
            elif not bom_lines or not mrp:
                self.create_stock_move_and_done_ts(sale_line, quantity, location_dest_id)
        self.write({'state': 'sale', 'updated_in_marketplace': fulfillment_status})
        return True

    def create_stock_move_and_done_ts(self, sale_line, quantity, location_dest_id, location_id=False, bom_line=False):
        # The work of this method is creating stock moves and done it based on order line.
        if bom_line:
            product_id = bom_line[0].product_id
            quantity = bom_line[1].get('qty', 0) * quantity
            product_uom_id = bom_line[0].product_uom_id
        else:
            product_id = sale_line.product_id
            product_uom_id = sale_line.product_uom
        if product_id and quantity and product_uom_id:
            move_vals = self._get_move_raw_values_ts(product_id, quantity, product_uom_id, location_id, location_dest_id, sale_line, bom_line)
            move_id = self.env['stock.move'].create(move_vals)
            move_id._action_assign()
            move_id._set_quantity_done(quantity)
            move_id._action_done()
            return move_id

    def _get_move_raw_values_ts(self, product, quantity, product_uom, location_id, location_dest_id, order_line, bom_line):
        # The work of this method is prepare the values of stock move.
        vals = {
            'name': _('Auto Create move: %s') % product.display_name,
            'origin': self.name,
            'product_id': product.id if product else False,
            'product_uom_qty': quantity,
            'product_uom': product_uom.id if product_uom else False,
            'location_dest_id': location_dest_id.id,
            'location_id': location_id.id if location_id else self.warehouse_id.lot_stock_id.id,
            'company_id': self.company_id.id,
            'state': 'confirmed',
            'sale_line_id': order_line.id,
        }
        if bom_line:
            vals.update({'bom_line_id': bom_line[0].id})
        return vals

    def action_view_stock_moves_ts(self):
        # The work of this action is get the all stock moves which is link with the sale order.
        stock_move_obj = self.env['stock.move']
        move_ids = stock_move_obj.search([('picking_id', '=', False), ('sale_line_id', 'in', self.order_line.ids)]).ids
        action = {
            'name': 'Sale Order Stock Move',
            'res_model': 'stock.move',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', move_ids)],
        }
        return action

    def check_product_dropship(self, product_id):
        # The work of this method is check the product is drop ship or not.
        location_dest_ids = self.env['stock.location'].search(['|', ('company_id', '=', self.company_id.id), ('company_id', '=', False), ('usage', '=', 'customer')])
        route_ids = product_id.route_ids or product_id.categ_id.route_ids
        stock_rule = self.env['stock.rule'].search([('company_id', '=', self.env.company.id), ('action', '=', 'buy'), ('location_id', 'in', location_dest_ids.ids), ('route_id', 'in', route_ids.ids)])
        if stock_rule:
            return True
        return False

    def check_bom_product_ts(self, product_id):
        # The work of this method is check the bom product and return its components.
        try:
            bom = self.env['mrp.bom'].sudo()._bom_find(product_id, company_id=self.company_id.id, bom_type='phantom')[product_id]
            if bom:
                factor = product_id.uom_id._compute_quantity(1, bom.product_uom_id) / bom.product_qty
                boms, lines = bom.sudo().explode(product_id, factor, picking_type=bom.picking_type_id)
                return lines
        except Exception as e:
            _logger.info("Error when trying to find BOM product components for Order {}. ERROR: {}".format(self.name, e))
        return {}
