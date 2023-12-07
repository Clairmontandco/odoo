from odoo import models, fields, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mk_instance_id = fields.Many2one('mk.instance', "Instance", ondelete='restrict', copy=False)
    marketplace = fields.Selection(related="mk_instance_id.marketplace", string='Marketplace')
    mk_id = fields.Char("Marketplace Identification", copy=False)
    mk_order_number = fields.Char("Order Number", copy=False)
    updated_in_marketplace = fields.Boolean("Updated in Marketplace?", copy=False)
    canceled_in_marketplace = fields.Boolean("Cancel in Marketplace", default=False, copy=False)

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.mk_instance_id:
            invoice_vals.update({'mk_instance_id': self.mk_instance_id.id})
        return invoice_vals

    def get_odoo_tax(self, mk_instance_id, tax_lines, taxes_included):
        tax_list, tax_obj = [], self.env['account.tax']
        mk_log_line_dict = self.env.context.get('mk_log_line_dict', {'error': [], 'success': []})
        queue_line_id = self.env.context.get('queue_line_id', False)
        company_id = mk_instance_id.company_id
        for tax_line in tax_lines:
            if mk_instance_id and mk_instance_id.tax_rounding:
                rate = round(tax_line['rate'], mk_instance_id.tax_rounding)
            else:
                rate = tax_line['rate']

            tax_title = "{} {} {}".format(tax_line['title'], rate, 'Included' if taxes_included else 'Excluded')

            tax_id = tax_obj.search([('name', '=', tax_title), ('amount', '=', rate), ('type_tax_use', '=', 'sale'), ('company_id', '=', company_id.id),
                                     ('price_include', '=', taxes_included), '|', ('active', '=', False), ('active', '=', True)])
            if not tax_id.active:
                tax_id.active = True
            if not tax_id:
                description = "{}% {}".format(rate, 'Included' if taxes_included else 'Excluded')
                tax_vals = {'name': tax_title, 'amount': rate, 'type_tax_use': 'sale', 'price_include': taxes_included, 'company_id': company_id.id,
                            'description': description}
                tax_id = tax_obj.create(tax_vals)
                if mk_instance_id.tax_account_id:
                    tax_repartition_lines = tax_id.invoice_repartition_line_ids.filtered(lambda x: x.repartition_type == 'tax')
                    if tax_repartition_lines:
                        tax_repartition_lines.account_id = mk_instance_id.tax_account_id.id
                if mk_instance_id.tax_refund_account_id:
                    refund_repartition_lines = tax_id.refund_repartition_line_ids.filtered(lambda x: x.repartition_type == 'tax')
                    if refund_repartition_lines:
                        refund_repartition_lines.account_id = mk_instance_id.tax_refund_account_id.id
                log_message = "Tax not found so created new Tax {} for Company {} with rate {}.".format(tax_title, company_id.name, rate)
                mk_log_line_dict['success'].append({'log_message': 'IMPORT ORDER: {}'.format(log_message), 'queue_job_line_id': queue_line_id and queue_line_id.id or False})
            tax_list.append(tax_id.id)

        return [(6, 0, tax_list)]

    def prepare_sales_order_vals_ts(self, vals, mk_instance_id):
        order_obj = self.env['sale.order']
        order_vals = {
            'partner_id': vals.get('partner_id'),
            'partner_invoice_id': vals.get('partner_invoice_id'),
            'partner_shipping_id': vals.get('partner_shipping_id'),
            'warehouse_id': vals.get('warehouse_id'),
            'company_id': vals.get('company_id', self.env.user.company_id.id),
        }
        order = order_obj.new(order_vals)
        order.onchange_partner_id()
        order_vals = order_obj._convert_to_write({name: order[name] for name in order._cache})

        order = order_obj.new(order_vals)
        order.onchange_partner_shipping_id()
        order_vals = order_obj._convert_to_write({name: order[name] for name in order._cache})

        fiscal_position_id = order_vals.get('fiscal_position_id', vals.get('fiscal_position_id', False))

        if vals.get('name', False):
            order_vals.update({'name': vals.get('name', '')})

        if mk_instance_id.analytic_account_id:
            order_vals.update({'analytic_account_id': mk_instance_id.analytic_account_id.id})

        order_vals.update({
            'state': 'draft',
            'date_order': vals.get('date_order', ''),
            'company_id': vals.get('company_id'),
            'picking_policy': vals.get('picking_policy'),
            'partner_invoice_id': vals.get('partner_invoice_id'),
            'partner_shipping_id': vals.get('partner_shipping_id'),
            'partner_id': vals.get('partner_id'),
            'client_order_ref': vals.get('client_order_ref', ''),
            'team_id': vals.get('team_id', ''),
            'carrier_id': vals.get('carrier_id', ''),
            'pricelist_id': vals.get('pricelist_id', ''),
            'fiscal_position_id': fiscal_position_id,
            'payment_term_id': vals.get('payment_term_id', ''),
        })
        return order_vals

    def get_mk_listing_item_for_mk_order(self, mk_id, mk_instance_id):
        return False if not mk_id else self.env['mk.listing.item'].search([('mk_instance_id', '=', mk_instance_id.id), ('mk_id', '=', mk_id)])

    def open_sale_order_in_marketplace(self):
        self.ensure_one()
        if hasattr(self, '%s_open_sale_order_in_marketplace' % self.marketplace):
            url = getattr(self, '%s_open_sale_order_in_marketplace' % self.marketplace)()
            if url:
                client_action = {
                    'type': 'ir.actions.act_url',
                    'name': "Marketplace URL",
                    'target': 'new',
                    'url': url,
                }
                return client_action

    def check_marketplace_order_date(self, order_create_date, mk_instance_id):
        if mk_instance_id.import_order_after_date and str(mk_instance_id.import_order_after_date) > order_create_date:
            return False
        return True

    def _check_invoice_policy_ordered(self):
        # If any of the order line has invoice policy delivery and ordered qty is not delivered the return False.
        order_lines = self.order_line.filtered(lambda x: x.product_id.invoice_policy == 'delivery')
        for order_line in order_lines:
            if not order_line.product_uom_qty == order_line.qty_delivered:
                return False
        return True

    def _action_cancel(self):
        res = super(SaleOrder, self)._action_cancel()
        # While we are cancel the order, we also need to revert the stock move.
        if self.stock_moves_count:
            return_wizard_vals = self.env['stock.return.picking'].with_context(active_model='sale.order', active_ids=self.ids).default_get([])
            return_wizard_id = self.env['stock.return.picking'].create(return_wizard_vals)
            return_wizard_id.with_context(skip_error=True).create_returns_ts()
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mk_id = fields.Char("Marketplace Identification", copy=False)
    is_discount = fields.Boolean("Is Marketplace Discount", copy=False)
    related_disc_sale_line_id = fields.Many2one("sale.order.line", copy=False)

    def prepare_sale_order_line_ts(self, vals):
        order_line = {
            'name': vals.get('description'),
            'order_id': vals.get('order_id'),
            'product_id': vals.get('product_id', ''),
            'product_uom': vals.get('product_uom'),
            'company_id': vals.get('company_id', '')
        }

        order_line = self.new(order_line)
        order_line.product_id_change()
        order_line = self._convert_to_write({name: order_line[name] for name in order_line._cache})

        order_line.update({
            'state': 'draft',
            'order_id': vals.get('order_id'),
            'product_uom_qty': vals.get('order_qty', 0.0),
            'price_unit': vals.get('price_unit', 0.0),
            'discount': vals.get('discount', 0.0),
        })
        return order_line
