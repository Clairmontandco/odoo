from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super(StockPicking, self)._action_done()
        for picking_id in self:
            if picking_id.sale_id.invoice_status == 'invoiced':
                continue
            marketplace_workflow_id = picking_id.sale_id.order_workflow_id
            delivery_lines = picking_id.move_line_ids.filtered(lambda l: l.product_id.invoice_policy == 'delivery')
            if delivery_lines and marketplace_workflow_id and marketplace_workflow_id.is_create_invoice and picking_id.picking_type_id.code == 'outgoing':
                picking_id.sale_id.with_context(manual_validate=True).process_invoice(marketplace_workflow_id)
        return res
