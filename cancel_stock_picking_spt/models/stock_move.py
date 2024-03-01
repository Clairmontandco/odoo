# -*- coding: utf-8 -*-
# Part of Keypress IT Services. See LICENSE file for full copyright and licensing details.##
##################################################################################
from odoo import models


class stock_move(models.Model):
    _inherit = 'stock.move'

    def stock_quant_update_spt(self):
        context={}
        for move in self:
        # Reset On Hand Qauntities of Perticular Products
            if move.state == "done" and move.product_id.type == "product":
                for line in move.move_line_ids:
                    qty = line.product_uom_id._compute_quantity(line.qty_done, line.product_id.uom_id)
                    self.env['stock.quant']._update_available_quantity(line.product_id, line.location_id, qty, lot_id = line.lot_id or None)
                    partner_quants = self.env['stock.quant'].sudo().search([('product_id','=',move.product_id.id),('location_id','=',line.location_dest_id.id),('lot_id','=',line.lot_id.id)],limit=1)
                    if partner_quants:
                        partner_quants.quantity -= qty
            context.update(self._context)
            context.update({'stock_quant_update_spt':True})
            move.with_context(context)._action_cancel()
        
    def _action_cancel(self):
        for move in self:
            #Cancel Stock Move
            if move.state == 'cancel':
                continue
            move.state_change_spt()
            state_ids = (move.move_dest_ids.mapped('move_orig_ids') - move).mapped('state')
            if move.propagate_cancel:
                for state in state_ids:
                    if state == 'cancel':
                        move.move_dest_ids._action_cancel()
            else:
                if all(state in ('done', 'cancel') for state in state_ids):
                    move.move_dest_ids.write({'procure_method': 'make_to_stock'})
                    move.move_dest_ids.write({'move_orig_ids': [(3, move.id, 0)]})
            move.write({
                'state': 'cancel', 
                'move_orig_ids': [(5, 0, 0)],
                'procure_method': 'make_to_stock',
                })
            #Remove Inventory Valuation line
            account_move = self.env['account.move'].search([('stock_move_id', '=', move.id)])
            if account_move:
                account_move.button_cancel()
                account_move.unlink()

    def state_change_spt(self) :
        for move in self:
            #Changing States
            if move.procure_method == 'make_to_order' and not move.move_orig_ids:
                move.state = 'waiting'
            elif move.move_orig_ids and not all(orig.state in ('done', 'cancel') for orig in move.move_orig_ids):
                move.state = 'waiting'
            else:
                move.state = 'confirmed'
            move.move_line_ids.unlink()
