from odoo import models,fields,api,_
from odoo.tools import is_html_empty

INVOICE_PAYMENT = [('to_invoice','To Invoice'),('not_paid','Not Paid'),('partially_paid','Partially paid'),('in_payment','In Payment'),('paid','Paid')]

class sale_order(models.Model):
    _inherit = 'sale.order'

    mo_ids = fields.Many2many('mrp.production','manufacturing_sale_order_rel','sale_id','manufacturing_id','Manufacturings',copy=False)
    kits_mo_count = fields.Integer('#Manufacturings',compute="_compute_mo_count",copy=False)

    invoice_payment_status = fields.Selection(selection=INVOICE_PAYMENT,compute="_compute_invoice_payment_status",store=True,compute_sudo=True)

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
            record.write({
                'kits_mo_count':len(mo_ids),
                'mo_ids':mo_ids.ids,
            })

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

    @api.model
    def create(self,vals):
        res = super(sale_order,self).create(vals)
        if not res.validity_date and bool(res.commitment_date or res.expected_date):
            res.validity_date = res.commitment_date or res.expected_date
        return res
