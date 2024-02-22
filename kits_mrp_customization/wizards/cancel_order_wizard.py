from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessError, UserError, ValidationError

class CancelOrderWizard(models.TransientModel):
    _name = 'cancel.order.wizard'

    sale_id = fields.Many2one('sale.order','Order')
  
    def action_cancel_order(self):
        for rec in self:
            return rec.sale_id.action_cancel()

    def action_cancel_backorder(self):
        for rec in self:
            if rec.sale_id.sale_backorder_ids.picking_ids.filtered(lambda x:x.state == 'done'):
                raise UserError('Some BackOrder products have already been delivered,So you can cancel only Original Order !')
            else:
                for backorder in rec.sale_id.sale_backorder_ids:
                    backorder.action_cancel()
                return rec.action_cancel_order()
                    
