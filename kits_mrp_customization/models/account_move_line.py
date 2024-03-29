from odoo import models,api,fields,_
from odoo.exceptions import UserError

class AccountMoveLine(models.Model):
    _inherit='account.move.line'

    kcash_product = fields.Boolean(string='Clairmont Cash Product',compute="_compute_kcash_product")   

    def reconcile(self):
        result = super(AccountMoveLine, self).reconcile()
        if 'full_reconcile' in result.keys():
            self.move_id.sale_order_id.payment_term_id = self.env['account.payment.term'].search([('kits_paid','=',True)],limit = 1).id
        return result

    @api.onchange('product_id')
    def _compute_kcash_product(self):
        for rec in self:
            if rec.product_id.is_kcash_rewards:
                rec.kcash_product = True
            else:
                rec.kcash_product = False

    def unlink(self):
        for rec in self:
            if rec.kcash_product:
                if rec.price_unit == 0:
                    return super(AccountMoveLine, rec).unlink()
                else:
                    raise UserError(_('Sorry you can not remove line with kcash reward.'))
        return super(AccountMoveLine, self).unlink()


class AccountMove(models.Model):
    _inherit='account.move'

    delivery_status = fields.Selection([('draft', 'Draft'),('waiting', 'Waiting Another Operation'),('confirmed', 'Waiting'),('assigned', 'Ready'),('done', 'Done'),('cancel', 'Cancelled')],compute='_compute_delivery_status',default=None)
    
    paid_date = fields.Date('Paid Date',compute='_compute_paid_date',store=True)

    date_done = fields.Date('Ship Date',compute='_compute_delivery_status',store=True)

    sale_order_id = fields.Many2one('sale.order',string="Sale order")

    book_date =  fields.Datetime('Book date',related = 'sale_order_id.book_date')

    @api.depends('amount_residual')
    def _compute_paid_date(self):
        for rec in self:
            payments = rec._get_reconciled_payments()
            latest_paid_date = max(payments, key=lambda x: x.create_date).create_date.date() if payments else None
            rec.paid_date = latest_paid_date

    def _compute_delivery_status(self):
        for rec in self:
            if rec.invoice_origin and rec.state != 'cancel':
                sale_order = self.env['sale.order'].search([('name','=',rec.invoice_origin)])
                picking_ids = sale_order.picking_ids.filtered(lambda x:x.state != 'cancel') if sale_order else None
                rec.delivery_status = max(picking_ids, key=lambda x: x.create_date).state if picking_ids else None
                rec.date_done = max(picking_ids, key=lambda x: x.create_date).date_done if picking_ids else None
            else:
                rec.delivery_status = None
                rec.date_done = None
