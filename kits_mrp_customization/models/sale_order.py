from odoo import models,fields,api,_
from odoo.tools import is_html_empty
import json
from odoo.tools.misc import formatLang, format_date, get_lang, groupby
from odoo.exceptions import UserError, ValidationError

INVOICE_PAYMENT = [('to_invoice','To Invoice'),('not_paid','Not Paid'),('partially_paid','Partially paid'),('in_payment','In Payment'),('paid','Paid')]

class sale_order(models.Model):
    _inherit = 'sale.order'

    mo_ids = fields.Many2many('mrp.production','manufacturing_sale_order_rel','sale_id','manufacturing_id','Manufacturings',copy=False)
    kits_mo_count = fields.Integer('#Manufacturings',compute="_compute_mo_count",copy=False)

    invoice_payment_status = fields.Selection(selection=INVOICE_PAYMENT,compute="_compute_invoice_payment_status",store=True,compute_sudo=True)
    delivery_status = fields.Selection([('draft', 'Draft'),('waiting', 'Waiting Another Operation'),('confirmed', 'Waiting'),('assigned', 'Ready'),('done', 'Done'),('cancel', 'Cancelled')],compute='_compute_delivery_status',default=None)

    kcash = fields.Integer('K-cash')
    kcash_id = fields.Many2one('kcash.bonus')
    kcash_history_ids = fields.One2many('kcash.history', 'order_id')

    paid_date = fields.Date('Paid Date',compute='_compute_paid_date',store=True)

    parent_order_id = fields.Many2one('sale.order','Original Order')
    sale_backorder_ids = fields.One2many('sale.order','parent_order_id','Back Orders')
    backorder_count = fields.Integer('Back Orders Count',compute='_compute_backorder_count')

    def action_create_backorder(self):
        for rec in self:
            wizard = self.env['create.backorder.wizard'].create({'order_id':rec.id})
            for line in rec.order_line:
                onhand_qty = line.product_id.qty_available
                if onhand_qty < line.product_uom_qty:
                    reorder_qty = line.product_uom_qty - onhand_qty
                    backorder_line = self.env['create.backorder.line'].create({
                        'wiz_id':wizard.id,
                        'order_line_id':line.id,
                        'product_id':line.product_id.id,
                        'product_uom_qty':reorder_qty
                    })
        return {
                'name': 'Create Backorder',
                'view_mode': 'form',
                'target': 'new',
                'res_model': 'create.backorder.wizard',
                'type': 'ir.actions.act_window',
                'res_id':wizard.id
                }
    
    def action_cancel_order(self):
        if not self.sale_backorder_ids:
            return self.action_cancel()
        else:
            return {
                    'name': 'Cancel Order',
                    'view_mode': 'form',
                    'target': 'new',
                    'res_model': 'cancel.order.wizard',
                    'context':{'default_sale_id': self.id},
                    'type': 'ir.actions.act_window',
                    }

    @api.depends('sale_backorder_ids')
    def _compute_backorder_count(self):
        for rec in self:
            rec.backorder_count = len(rec.sale_backorder_ids)

    @api.depends('invoice_ids','invoice_ids.amount_residual')
    def _compute_paid_date(self):
        for rec in self:
            invoice_id = rec.invoice_ids.filtered(lambda x:x.state != 'cancel')
            payments = invoice_id._get_reconciled_payments() if invoice_id else None
            latest_paid_date = max(payments, key=lambda x: x.create_date).create_date.date() if payments else None
            rec.paid_date = latest_paid_date

    @api.depends('picking_ids.state')
    def _compute_delivery_status(self):
        for rec in self:
            rec.delivery_status = None
            picking_ids = rec.picking_ids.filtered(lambda x:x.state != 'cancel') if rec.picking_ids else None
            if picking_ids:
                rec.delivery_status = max(picking_ids, key=lambda x: x.create_date).state if picking_ids else None

    #OverRide for set tax_totals when order have "Hide From Order" products.
    @api.depends('order_line.tax_id', 'order_line.price_unit', 'amount_total', 'amount_untaxed')
    def _compute_tax_totals_json(self):
        def compute_taxes(order_line):
            price = order_line.price_unit * (1 - (order_line.discount or 0.0) / 100.0)
            order = order_line.order_id
            return order_line.tax_id._origin.compute_all(price, order.currency_id, order_line.product_uom_qty, product=order_line.product_id, partner=order.partner_shipping_id)
        account_move = self.env['account.move']
        for order in self:
            tax_lines_data = account_move._prepare_tax_lines_data_for_totals_from_object(order.order_line, compute_taxes)
            tax_totals = account_move._get_tax_totals(order.partner_id, tax_lines_data, order.amount_total, order.amount_untaxed, order.currency_id)
            if self._context.get('report') == True:
                order_line = order.order_line.filtered(lambda x:x.product_id.product_tmpl_id.hide_from_order == False)
                tax_totals['formatted_amount_total'] = formatLang(self.env, sum(order_line.mapped('price_subtotal')) + sum(order_line.mapped('price_tax')), currency_obj=self.currency_id)
                tax_totals['formatted_amount_untaxed'] = formatLang(self.env, sum(order_line.mapped('price_subtotal')), currency_obj=self.currency_id)
            order.tax_totals_json = json.dumps(tax_totals)

    @api.depends('invoice_status','invoice_ids','invoice_ids.payment_state')
    def _compute_invoice_payment_status(self):
        for record in self:
            state = 'to_invoice'
            invoice_ids = record.invoice_ids.filtered(lambda x: x.state not in ('draft','cancel'))
            if invoice_ids:
                state = 'not_paid'
                payment_states = invoice_ids.mapped('payment_state')
                if any(ps == 'partial' for ps in payment_states):
                    state = 'partially_paid'
                elif any(ps == 'in_payment' for ps in payment_states):
                    state = 'in_payment'
                elif all(ps == 'paid' for ps in payment_states):
                    state = 'paid'
            record.invoice_payment_status = state

    @api.depends('mo_ids')
    def _compute_mo_count(self):
        mo_obj = self.env['mrp.production']
        kcash=0
        kcash_id = 0
        for record in self:
            mo_ids = mo_obj
            for line in record.order_line:
                lines = self.env['report.stock.report_product_product_replenishment']._get_report_lines(False,[line.product_id.id],[line.warehouse_id.lot_stock_id.id])
                for line in lines:
                    if line['document_out'] and line['document_out'] == record:
                        if isinstance(line['document_in'],mo_obj.__class__):
                            mo_ids |= line['document_in']
            # record.kits_mo_count = len(mo_ids)
            # record.mo_ids = mo_ids
            kcash += sum(record.partner_id.kcash_bonus_ids.search([('partner_id','=',record.partner_id.id),('sale_id','!=',record.id),('expiry_date','>=',fields.Date.today())]).mapped('credit'))
            kcash -= sum(record.partner_id.kcash_bonus_ids.search([('partner_id','=',record.partner_id.id),('sale_id','!=',record.id),('expiry_date','>=',fields.Date.today())]).mapped('debit'))
            record.write({
                'kits_mo_count':len(mo_ids),
                'mo_ids':mo_ids.ids,
                'kcash':kcash
            })

    def action_kcash(self):
        pass 

    def action_view_sale_backorder(self):
        self.ensure_one()
        action =  {
            'name':_('Back Orders'),
            'type':'ir.actions.act_window',
            'res_model':"sale.order",
            'target':'current',
        }
        if len(self.sale_backorder_ids) == 1:
            action.update({
                'res_id':self.sale_backorder_ids.ids[0],
                'view_mode':'form',
            })
        else:
            action.update({
                'view_mode':'tree,form',
                'domain':[('id','in',self.sale_backorder_ids.ids)],
                })
        return action

    def action_view_manufacturings(self):
        self.ensure_one()
        action =  {
            'name':_('Manufacturing Orders'),
            'type':'ir.actions.act_window',
            'res_model':"mrp.production",
            'target':'current',
        }
        if len(self.mo_ids) == 1:
            action.update({
                'res_id':self.mo_ids.ids[0],
                'view_mode':'form',
            })
        else:
            action.update({
                'view_mode':'tree,form',
                'domain':[('id','in',self.mo_ids.ids)],
                })
        return action

    @api.onchange('commitment_date', 'expected_date')
    def _onchange_commitment_date(self):
        self.validity_date = self.commitment_date.date() if self.commitment_date else self.expected_date
        return super(sale_order,self)._onchange_commitment_date()

    # Replaced to stop updating validity_date field.
    @api.onchange('sale_order_template_id')
    def onchange_sale_order_template_id(self):

        if not self.sale_order_template_id:
            self.require_signature = self._get_default_require_signature()
            self.require_payment = self._get_default_require_payment()
            return

        template = self.sale_order_template_id.with_context(lang=self.partner_id.lang)

        # --- first, process the list of products from the template
        order_lines = [(5, 0, 0)]
        for line in template.sale_order_template_line_ids:
            data = self._compute_line_data_for_template_change(line)

            if line.product_id:
                price = line.product_id.lst_price
                discount = 0

                if self.pricelist_id:
                    pricelist_price = self.pricelist_id.with_context(uom=line.product_uom_id.id).get_product_price(line.product_id, 1, False)

                    if self.pricelist_id.discount_policy == 'without_discount' and price:
                        discount = max(0, (price - pricelist_price) * 100 / price)
                    else:
                        price = pricelist_price

                data.update({
                    'price_unit': price,
                    'discount': discount,
                    'product_uom_qty': line.product_uom_qty,
                    'product_id': line.product_id.id,
                    'product_uom': line.product_uom_id.id,
                    'customer_lead': self._get_customer_lead(line.product_id.product_tmpl_id),
                })

            order_lines.append((0, 0, data))

        self.order_line = order_lines
        self.order_line._compute_tax_id()

        # then, process the list of optional products from the template
        option_lines = [(5, 0, 0)]
        for option in template.sale_order_template_option_ids:
            data = self._compute_option_data_for_template_change(option)
            option_lines.append((0, 0, data))

        self.sale_order_option_ids = option_lines

        # @FENIL--Removed to stop updating Expiration Field
        # if template.number_of_days > 0:
        #     self.validity_date = fields.Date.context_today(self) + timedelta(template.number_of_days)

        self.require_signature = template.require_signature
        self.require_payment = template.require_payment

        if not is_html_empty(template.note):
            self.note = template.note

    def _action_cancel(self):
        res = super()._action_cancel()
        for rec in self.kcash_history_ids:
            rec.kcash_id.debit -= rec.amount
            rec.kcash_id.reward_fullfill = False
            rec.unlink()
        k_cash_line = self.order_line.filtered(lambda ol: ol.product_id.is_kcash_rewards)
        k_cash_line.price_unit = 0
        k_cash_line.unlink()
        return res

    @api.model
    def create(self,vals):
        res = super(sale_order,self).create(vals)
        if not res.validity_date and bool(res.commitment_date or res.expected_date):
            res.validity_date = res.commitment_date or res.expected_date
        return res

    def action_kcash_wizard(self):
        line_kcash = self.kcash + abs(self.order_line.filtered(lambda ol: ol.product_id.is_kcash_rewards).price_unit)
        return {
                    'name': 'Apply Clairmont Cash',
                    'view_mode': 'form',
                    'target': 'new',
                    'res_model': 'k.cash.wizard',
                    'context':{'default_sale_id': self.id,
                               'default_available_kcash': line_kcash,
                               'default_remain_kcash':line_kcash},
                    'type': 'ir.actions.act_window',
                }

    def action_add_kcash_wizard(self):
        return {
                'name': 'Add Clairmont Cash Reward',
                'view_mode': 'form',
                'target': 'new',
                'res_model': 'add.kcash.reward.wizard',
                'context':{'default_sale_id': self.id,
                            'default_partner_id': self.partner_id.id},
                'type': 'ir.actions.act_window',
                }