from odoo import models

class StockBackorderConfirmation(models.TransientModel):
    _inherit = 'stock.backorder.confirmation'

    def process(self):
        for line in self.backorder_confirmation_line_ids:
            if line.to_backorder:
                sale_order_lines = []
                for move in line.picking_id.move_ids_without_package:
                    qty_diff = move.product_uom_qty - move.quantity_done
                    if qty_diff:
                        sale_line_id = move.sale_line_id
                        sale_line_id.product_uom_qty = move.quantity_done
                        sale_line_id.backorder_qty = qty_diff
                        sale_order_line_vals = {
                            'product_id': sale_line_id.product_id.id,
                            'product_uom_qty': qty_diff,
                            'price_unit': sale_line_id.price_unit,
                            'order_line_id':sale_line_id.id
                        }
                        sale_order_lines.append((0, 0, sale_order_line_vals))
                if sale_order_lines:
                    sale_id = line.picking_id.sale_id
                    sale_order_vals = {
                    'partner_id': line.picking_id.partner_id.id,
                    'parent_order_id':sale_id.id,
                    'order_line': sale_order_lines,
                    'payment_term_id':sale_id.payment_term_id.id,
                    'validity_date':sale_id.validity_date
                    }
                    sale_order = self.env['sale.order'].create(sale_order_vals)
                    sale_order.name = sale_order.name.replace('SO','BO')
                    sale_order.action_confirm()
                    sale_order.picking_ids[0].backorder_id = line.picking_id
        return True
