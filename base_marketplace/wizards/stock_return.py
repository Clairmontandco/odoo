# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'
    _description = 'Return Picking'

    sale_order_id = fields.Many2one('sale.order', string='Sales Order')

    @api.model
    def default_get(self, fields):
        res = super(ReturnPicking, self).default_get(fields)
        if self.env.context.get('active_id') and self.env.context.get('active_model') == 'sale.order':
            if len(self.env.context.get('active_ids', list())) > 1:
                raise UserError(_("You may only return one sale order at a time."))
            order_id = self.env['sale.order'].browse(self.env.context.get('active_id'))
            if order_id.exists():
                res.update({'sale_order_id': order_id.id})
                product_return_moves = [(5,)]
                product_return_moves_data_tmpl = {}
                stock_move_ids = self.env["stock.move"].search([("sale_line_id", "in", order_id.order_line.ids), ("picking_id", "=", False), ('to_refund', '=', False)])
                for move in stock_move_ids:
                    if move.state == 'cancel':
                        continue
                    if move.scrapped:
                        continue
                    product_return_moves_data = dict(product_return_moves_data_tmpl)
                    product_return_moves_data.update(self._prepare_stock_return_picking_line_vals_from_move(move))
                    product_return_moves.append((0, 0, product_return_moves_data))
                    res.update({'product_return_moves': product_return_moves})
        return res

    def create_returns_ts(self):
        returned_lines = 0
        for return_line in self.product_return_moves:
            if not return_line.move_id:
                raise UserError(_("You have manually created product lines, please delete them to proceed."))
            if return_line.quantity:
                returned_lines += 1
                vals = self._prepare_move_default_values(return_line, self.env['stock.picking'])
                vals.update({'to_refund': True})
                r = return_line.move_id.copy(vals)
                vals = {}
                move_orig_to_link = return_line.move_id.move_dest_ids.mapped('returned_move_ids')
                # link to original move
                move_orig_to_link |= return_line.move_id
                # link to siblings of original move, if any
                move_orig_to_link |= return_line.move_id.mapped('move_dest_ids').filtered(lambda m: m.state not in ('cancel')).mapped('move_orig_ids').filtered(lambda m: m.state not in ('cancel'))
                move_dest_to_link = return_line.move_id.move_orig_ids.mapped('returned_move_ids')
                move_dest_to_link |= return_line.move_id.move_orig_ids.mapped('returned_move_ids').mapped('move_orig_ids').filtered(lambda m: m.state not in ('cancel')).mapped('move_dest_ids').filtered(lambda m: m.state not in ('cancel'))
                vals['move_orig_ids'] = [(4, m.id) for m in move_orig_to_link]
                vals['move_dest_ids'] = [(4, m.id) for m in move_dest_to_link]
                r.write(vals)
                r._action_assign()
                r._set_quantity_done(return_line.quantity)
                r._action_done()
        if not returned_lines and not self.env.context.get('skip_error', False):
            raise UserError(_("Please specify at least one non-zero quantity."))
        return True
