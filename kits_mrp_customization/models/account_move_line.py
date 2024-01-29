from odoo import models,api,fields,_
from odoo.exceptions import UserError, ValidationError
class AccountMoveLine(models.Model):
    _inherit='account.move.line'

    kcash_product = fields.Boolean(string='K-Cash Product',compute="_compute_kcash_product")   

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

    def _compute_delivery_status(self):
        for rec in self:
            rec.delivery_status = None
            if rec.invoice_origin and rec.state != 'cancel':
                sale_order = self.env['sale.order'].search([('name','=',rec.invoice_origin)])
                picking_ids = sale_order.picking_ids.filtered(lambda x:x.state != 'cancel') if sale_order else None
                rec.delivery_status = max(picking_ids, key=lambda x: x.create_date).state if picking_ids else None
