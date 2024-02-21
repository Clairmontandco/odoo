from odoo import _, api, fields, models, tools

class CancelOrderWizard(models.TransientModel):
    _name = 'cancel.order.wizard'

    sale_id = fields.Many2one('sale.order','Order')
  
    def action_cancel_order(self):
        for rec in self:
            rec.sale_id.action_cancel()

    def action_cancel_backorder(self):
        for rec in self:
            rec.sale_id.action_cancel()
            for backorder in rec.sale_id.sale_backorder_ids:
                backorder.action_cancel()